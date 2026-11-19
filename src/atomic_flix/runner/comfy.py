"""A small HTTP client for one local ComfyUI server, standard library only.

It can upload an input, queue a graph, read a graph's history, read the queue, fetch a saved file and read the
server's GPU. On purpose it has no way to interrupt a graph, free models, or clear the queue or history: the runner
never stops or restarts ComfyUI and never touches entries it did not submit.

A host is `host:port` and nothing else; only this machine (127.0.0.1, localhost, ::1) unless `allow_remote` is set
(`--allow-remote` on the command lines), since the client uploads the film's pictures and voice to it. An answer is
read up to a limit (JSON_LIMIT for JSON, DOWNLOAD_LIMIT for a saved file) and refused past it. An upload name with a
quote or a line break is refused rather than written into the form's header.
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ERROR_TEXT_LIMIT = 2000
JSON_LIMIT = 8 * 2 ** 20
DOWNLOAD_LIMIT = 512 * 2 ** 20
HISTORY_LOOKBACK = 2000
LOCAL_HOSTS = frozenset({"127.0.0.1", "localhost", "[::1]"})
HOST_PORT = re.compile(r"(?P<name>[A-Za-z0-9](?:[A-Za-z0-9.-]{0,251}[A-Za-z0-9])?|\[[0-9A-Fa-f:]+\]):(?P<port>[0-9]{1,5})")
UNSAFE_NAME = re.compile(r"[\"'\r\n\x00]")


def check_host(host: str, *, allow_remote: bool = False) -> str:
    """HOST if it is `host:port` (and on this machine unless ALLOW_REMOTE); ValueError otherwise."""
    found = HOST_PORT.fullmatch(host or "")
    if not found or not 0 < int(found.group("port")) < 65536:
        raise ValueError(f"not a ComfyUI host: {host!r} (write host:port, such as 127.0.0.1:8188)")
    if found.group("name").lower() not in LOCAL_HOSTS and not allow_remote:
        raise ValueError(f"{host} is not on this machine; the runner sends it the film's pictures and voice, so a "
                         "remote host needs --allow-remote")
    return host


def check_upload_name(name: str) -> str:
    """NAME if it can stand in a form header: no quotes, line breaks or NUL, no folder parts; ValueError otherwise."""
    if not name or UNSAFE_NAME.search(name) or "/" in name or "\\" in name:
        raise ValueError(f"not a usable upload name: {name!r} (no quotes, line breaks or folder parts)")
    return name


class ComfyError(RuntimeError):
    """ComfyUI could not be reached (`status` None) or answered with an HTTP error (`status` its code)."""

    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


@dataclass(frozen=True)
class Outcome:
    """What a graph's history entry says. `state` is "done", "errored" or "pending"."""

    state: str
    file: dict | None = None
    error: str | None = None
    start_ms: float | None = None
    end_ms: float | None = None


CACHED_MESSAGE = ("ComfyUI finished the graph and saved nothing: it served a cached result for a graph it had "
                  "already run unchanged (the graph needs $seed and $save_as, set fresh for every job)")


class ComfyClient:
    def __init__(self, host: str, timeout_s: float = 60.0, *, allow_remote: bool = False,
                 json_limit: int = JSON_LIMIT, download_limit: int = DOWNLOAD_LIMIT) -> None:
        self.host = check_host(host, allow_remote=allow_remote)
        self.timeout_s = timeout_s
        self.json_limit = json_limit
        self.download_limit = download_limit

    def _call(self, path: str, data: bytes | None = None, headers: dict | None = None,
              timeout_s: float | None = None, limit: int | None = None) -> bytes:
        request = Request(f"http://{self.host}{path}", data=data, headers=headers or {})
        cap = self.json_limit if limit is None else limit
        try:
            with urlopen(request, timeout=timeout_s or self.timeout_s) as answer:
                body = answer.read(cap + 1)
                if len(body) > cap:
                    raise ComfyError(f"{self.host}{path}: the answer is over the limit of {cap} bytes; not read", 413)
                return body
        except HTTPError as err:
            body = err.read().decode("utf-8", errors="replace")[:ERROR_TEXT_LIMIT]
            raise ComfyError(f"{self.host}{path}: HTTP {err.code}: {body}", err.code) from err
        except (URLError, OSError) as err:
            raise ComfyError(f"{self.host}{path}: {err} (is ComfyUI running there?)") from err

    def _json(self, path: str, data: bytes | None = None, headers: dict | None = None,
              timeout_s: float | None = None) -> Any:
        raw = self._call(path, data, headers, timeout_s)
        try:
            return json.loads(raw.decode("utf-8"))
        except ValueError as err:
            raise ComfyError(f"{self.host}{path}: not JSON: {raw[:200]!r}") from err

    def system_stats(self, timeout_s: float | None = None) -> dict:
        return self._json("/system_stats", timeout_s=timeout_s)

    def gpu(self, timeout_s: float | None = None) -> tuple[str, float]:
        """The first device's name and total VRAM in GB."""
        devices = self.system_stats(timeout_s).get("devices") or [{}]
        first = devices[0]
        return str(first.get("name", "?")), float(first.get("vram_total", 0)) / 2 ** 30

    def send_file(self, path: str | Path, name: str) -> str:
        """Put a local file into ComfyUI's input folder under `name`; returns the name to use in a graph."""
        check_upload_name(name)
        boundary = uuid.uuid4().hex
        content = Path(path).read_bytes()

        def field(key: str, value: str) -> bytes:
            return f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n'.encode()

        body = (field("type", "input") + field("overwrite", "true")
                + (f'--{boundary}\r\nContent-Disposition: form-data; name="image"; filename="{name}"\r\n'
                   "Content-Type: application/octet-stream\r\n\r\n").encode("utf-8")
                + content + f"\r\n--{boundary}--\r\n".encode())
        answer = self._json("/upload/image", body, {"Content-Type": f"multipart/form-data; boundary={boundary}"})
        stored = answer.get("name")
        if not stored:
            raise ComfyError(f"{self.host}: upload of {name} returned no name: {answer}")
        return f"{answer['subfolder']}/{stored}" if answer.get("subfolder") else stored

    def enqueue(self, graph: dict, client_id: str) -> str:
        payload = json.dumps({"prompt": graph, "client_id": client_id}).encode("utf-8")
        answer = self._json("/prompt", payload, {"Content-Type": "application/json"})
        prompt_id = answer.get("prompt_id")
        if not prompt_id:   # ComfyUI answered and did not queue it: a refusal, not a lost answer
            raise ComfyError(f"{self.host}: the graph was not queued: {json.dumps(answer)[:ERROR_TEXT_LIMIT]}", 422)
        return str(prompt_id)

    def history(self, prompt_id: str) -> dict | None:
        """The history entry of one graph, or None while ComfyUI has none."""
        return self._json(f"/history/{prompt_id}").get(prompt_id)

    def queued_ids(self) -> set[str]:
        """Ids of graphs running or waiting on this server."""
        answer = self._json("/queue")
        logged = (answer.get("queue_running") or []) + (answer.get("queue_pending") or [])
        return {str(entry[1]) for entry in logged if isinstance(entry, list) and len(entry) > 1}

    def find_client(self, client_id: str) -> str | None:
        """The prompt id of the graph queued with CLIENT_ID, from the queue, then the history; None when the host
        has no record of it. Used before sending again a graph whose queueing was never confirmed."""
        answer = self._json("/queue")
        for entry in (answer.get("queue_running") or []) + (answer.get("queue_pending") or []):
            if _client_of(entry) == client_id:
                return str(entry[1])
        history = self._json(f"/history?{urlencode({'max_items': HISTORY_LOOKBACK})}")
        for prompt_id, item in (history or {}).items():
            if isinstance(item, dict) and _client_of(item.get("prompt")) == client_id:
                return str(prompt_id)
        return None

    def download(self, file: dict, timeout_s: float = 600.0) -> bytes:
        query = urlencode({"filename": file["filename"], "subfolder": file.get("subfolder", ""),
                           "type": file.get("type", "output")})
        return self._call(f"/view?{query}", timeout_s=timeout_s, limit=self.download_limit)


def _client_of(entry: Any) -> str | None:
    """The client id of a queue or history `prompt` entry: [number, prompt_id, graph, extra_data, ...]."""
    if isinstance(entry, list) and len(entry) > 3 and isinstance(entry[3], dict):
        return entry[3].get("client_id")
    return None


def _timestamps(entry: dict) -> dict[str, float]:
    stamps: dict[str, float] = {}
    for message in (entry.get("status") or {}).get("messages") or []:
        if isinstance(message, list) and len(message) == 2 and isinstance(message[1], dict):
            stamp = message[1].get("timestamp")
            if stamp is not None:
                stamps[message[0]] = float(stamp)
    return stamps


def _error_text(entry: dict) -> str:
    for message in reversed((entry.get("status") or {}).get("messages") or []):
        if isinstance(message, list) and len(message) == 2 and message[0] == "execution_error":
            detail = message[1]
            return f"{detail.get('node_type', '?')}: {detail.get('exception_message', '').strip()}"
    return "the graph errored (no error message in its history)"


def read_outcome(entry: dict | None, extension: str) -> Outcome:
    """Turn a history entry into an Outcome; the file is the last saved one of `extension`, outputs first."""
    if not entry:
        return Outcome("awaiting")
    status = entry.get("status") or {}
    stamps = _timestamps(entry)
    start = stamps.get("execution_start")
    end = stamps.get("execution_success") or stamps.get("execution_error")
    if status.get("status_str") == "error":
        return Outcome("errored", error=_error_text(entry), start_ms=start, end_ms=end)
    files = [item for node in (entry.get("outputs") or {}).values() for value in node.values()
             if isinstance(value, list) for item in value
             if isinstance(item, dict) and str(item.get("filename", "")).lower().endswith(extension)]
    preferred = [item for item in files if item.get("type") == "output"] or files
    if preferred:
        return Outcome("done", file=preferred[-1], start_ms=start, end_ms=end)
    if status.get("completed") or entry.get("outputs") is not None and status.get("status_str") == "success":
        saved_other = any(isinstance(v, list) for node in (entry.get("outputs") or {}).values() for v in node.values())
        if saved_other:
            return Outcome("errored", error=f"the graph saved no {extension} file: its save node must write one",
                           start_ms=start, end_ms=end)
        return Outcome("errored", error=CACHED_MESSAGE, start_ms=start, end_ms=end)
    return Outcome("awaiting")
