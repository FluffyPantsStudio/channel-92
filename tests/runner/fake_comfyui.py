"""A small stand-in for a ComfyUI server, for the runner's tests.

It speaks the handful of routes the runner uses (upload, prompt, history, queue, view, system_stats), keeps every
request it saw, and lets a test decide how each submitted graph ends: it finishes after a number of history polls,
fails, completes with nothing saved, or never finishes. Routes the runner must never call (interrupt, free, clearing
the queue or history) are recorded as forbidden.
"""

from __future__ import annotations

import json
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

FINISH = "finish"
ERROR = "error"
EMPTY = "empty"
HANG = "hang"


class Concurrency:
    """Counts graphs that are running at once across several fake servers."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.now = 0
        self.peak = 0

    def started(self) -> None:
        with self._lock:
            self.now += 1
            self.peak = max(self.peak, self.now)

    def ended(self) -> None:
        with self._lock:
            self.now -= 1


class FakeComfy:
    def __init__(self, gpu_name: str = "Fake RTX 3090", mode: str = FINISH, polls_to_finish: int = 1,
                 gpu_ms: int = 80_000, tracker: Concurrency | None = None, renderer=None) -> None:
        """`renderer(graph, files)`, when given, makes the bytes of each finished graph's saved video from the
        submitted graph and the uploaded files (name -> content); without it the output is a short marker."""
        self.renderer = renderer
        self.files: dict[str, bytes] = {}
        self.outputs: dict[str, bytes] = {}
        self.gpu_name = gpu_name
        self.mode = mode
        self.polls_to_finish = polls_to_finish
        self.gpu_ms = gpu_ms
        self.tracker = tracker
        self.lock = threading.Lock()
        self.requests: list[tuple[str, str]] = []
        self.forbidden: list[tuple[str, str]] = []
        self.uploads: dict[str, bytes] = {}
        self.prompts: dict[str, dict] = {}
        self.submitted: list[str] = []
        self.down = False
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), self._handler())
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    # lifecycle -------------------------------------------------------------------------------------------------
    @property
    def host(self) -> str:
        return f"127.0.0.1:{self._server.server_address[1]}"

    def start(self) -> "FakeComfy":
        self._thread.start()
        return self

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()

    # test controls ---------------------------------------------------------------------------------------------
    def finish_all(self) -> None:
        with self.lock:
            self.mode = FINISH
            for entry in self.prompts.values():
                entry["mode"] = FINISH
                entry["polls_left"] = 0

    def forget(self) -> None:
        """Lose every record, as a ComfyUI restarted by someone else would."""
        with self.lock:
            for entry in self.prompts.values():
                if entry["running"] and self.tracker:
                    self.tracker.ended()
            self.prompts.clear()

    def history_polls(self) -> int:
        return sum(1 for method, path in self.requests if method == "GET" and path.startswith("/history/"))

    # behaviour -------------------------------------------------------------------------------------------------
    def _new_prompt(self, body: dict) -> dict:
        prompt_id = uuid.uuid4().hex
        graph = body.get("prompt") or {}
        save_as = "out"
        for node in graph.values():
            value = node.get("inputs", {}).get("filename_prefix")
            if isinstance(value, str):
                save_as = value
        with self.lock:
            entry = {"graph": graph, "mode": self.mode, "polls_left": self.polls_to_finish, "save_as": save_as,
                     "number": len(self.submitted), "submitted_ms": int(time.time() * 1000), "running": True,
                     "client_id": body.get("client_id")}
            self.prompts[prompt_id] = entry
            self.submitted.append(prompt_id)
        if self.tracker:
            self.tracker.started()
        return {"prompt_id": prompt_id, "number": entry["number"], "node_errors": {}}

    def _settle(self, prompt_id: str) -> dict | None:
        """Advance one poll; return the history entry once the graph has ended."""
        with self.lock:
            entry = self.prompts.get(prompt_id)
            if entry is None:
                return None
            if entry["mode"] == HANG:
                return None
            if entry["polls_left"] > 0:
                entry["polls_left"] -= 1
                return None
            if entry["running"]:
                entry["running"] = False
                if self.tracker:
                    self.tracker.ended()
            return self._history_entry(prompt_id, entry)

    def _history_entry(self, prompt_id: str, entry: dict) -> dict:
        start = entry["submitted_ms"] + 1500
        end = start + self.gpu_ms
        name = entry["save_as"].split("/")[-1]
        if entry["mode"] == ERROR:
            return {"outputs": {}, "status": {"status_str": "error", "completed": False, "messages": [
                ["execution_start", {"prompt_id": prompt_id, "timestamp": start}],
                ["execution_error", {"prompt_id": prompt_id, "timestamp": end, "node_type": "KSampler",
                                     "exception_message": "CUDA out of memory"}]]}}
        if entry["mode"] == EMPTY:
            return {"outputs": {}, "status": {"status_str": "success", "completed": True, "messages": [
                ["execution_start", {"prompt_id": prompt_id, "timestamp": start}],
                ["execution_cached", {"prompt_id": prompt_id, "timestamp": start, "nodes": ["1", "2"]}],
                ["execution_success", {"prompt_id": prompt_id, "timestamp": start + 5}]]}}
        saved = f"{name}_00001_.mp4"
        if self.renderer is not None and saved not in self.outputs:
            self.outputs[saved] = self.renderer(entry["graph"], dict(self.files))
        outputs = {
            "50": {"images": [{"filename": f"{name}_preview.png", "subfolder": "", "type": "temp"}]},
            "51": {"gifs": [{"filename": f"{name}_preview.mp4", "subfolder": "", "type": "temp"}]},
            "52": {"images": [{"filename": f"{name}_00001_.mp4", "subfolder": "flix", "type": "output"}],
                   "animated": [True]},
        }
        return {"outputs": outputs, "status": {"status_str": "success", "completed": True, "messages": [
            ["execution_start", {"prompt_id": prompt_id, "timestamp": start}],
            ["execution_success", {"prompt_id": prompt_id, "timestamp": end}]]}}

    def _queue(self) -> dict:
        with self.lock:
            running = [[e["number"], pid, {}, {"client_id": e["client_id"]}, []]
                       for pid, e in self.prompts.items() if e["running"]]
        return {"queue_running": running[:1], "queue_pending": running[1:]}

    def _all_history(self) -> dict:
        """GET /history: every graph that has ended, with its prompt entry (client id in extra_data)."""
        with self.lock:
            ended = {pid: e for pid, e in self.prompts.items() if not e["running"]}
            return {pid: {**self._history_entry(pid, e), "prompt": [e["number"], pid, {}, {"client_id": e["client_id"]},
                                                                    []]} for pid, e in ended.items()}

    # HTTP ------------------------------------------------------------------------------------------------------
    def _handler(self):
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args) -> None:  # keep test output quiet
                return

            def _send(self, payload, status: int = 200, raw: bool = False) -> None:
                body = payload if raw else json.dumps(payload).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/octet-stream" if raw else "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _gate(self, method: str) -> bool:
                with fake.lock:
                    fake.requests.append((method, self.path))
                if fake.down:
                    self._send({"error": "down"}, 503)
                    return False
                return True

            def do_GET(self) -> None:
                if not self._gate("GET"):
                    return
                url = urlparse(self.path)
                if url.path == "/system_stats":
                    self._send({"system": {"python_version": "3.12"}, "devices": [
                        {"name": fake.gpu_name, "type": "cuda", "vram_total": 24 * 2 ** 30, "vram_free": 20 * 2 ** 30}]})
                elif url.path.startswith("/history/"):
                    prompt_id = url.path.rsplit("/", 1)[-1]
                    entry = fake._settle(prompt_id)
                    self._send({prompt_id: entry} if entry else {})
                elif url.path == "/queue":
                    self._send(fake._queue())
                elif url.path == "/history":
                    self._send(fake._all_history())
                elif url.path == "/view":
                    query = parse_qs(url.query)
                    name = query.get("filename", [""])[0]
                    kind = query.get("type", [""])[0]
                    made = fake.outputs.get(name) if kind == "output" else None
                    self._send(made if made is not None else f"VIDEO:{kind}:{name}".encode("utf-8"), raw=True)
                else:
                    self._send({"error": "not found"}, 404)

            def do_POST(self) -> None:
                if not self._gate("POST"):
                    return
                extent = int(self.headers.get("Content-Length") or 0)
                body = self.rfile.read(extent)
                url = urlparse(self.path)
                if url.path == "/prompt":
                    self._send(fake._new_prompt(json.loads(body.decode("utf-8"))))
                elif url.path == "/upload/image":
                    name = _form_filename(body)
                    with fake.lock:
                        fake.uploads[name] = body
                        fake.files[name] = _form_content(body)
                    self._send({"name": name, "subfolder": "", "type": "input"})
                elif url.path in ("/interrupt", "/free", "/queue", "/history"):
                    with fake.lock:
                        fake.forbidden.append(("POST", self.path))
                    self._send({})
                else:
                    self._send({"error": "not found"}, 404)

        return Handler


def _form_content(body: bytes) -> bytes:
    """The bytes of the first file part of a multipart form body."""
    marker = b'filename="'
    start = body.find(marker)
    if start < 0:
        return b""
    boundary = body[:body.find(b"\r\n")]
    head_end = body.find(b"\r\n\r\n", start) + 4
    stop = body.find(b"\r\n" + boundary, head_end)
    return body[head_end:stop if stop >= 0 else len(body)]


def _form_filename(body: bytes) -> str:
    marker = b'filename="'
    start = body.find(marker)
    if start < 0:
        return "unnamed"
    start += len(marker)
    return body[start:body.find(b'"', start)].decode("utf-8")
