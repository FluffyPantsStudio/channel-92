"""Command line for the runner.

  python -m atomic_flix.runner ping   [--hosts H1,H2] [--allow-remote]
  python -m atomic_flix.runner plan   PROJECT BATCH.json        write job files (checks everything first)
  python -m atomic_flix.runner budget PROJECT [--log FILE]       hours for the planned jobs, from past renders
  python -m atomic_flix.runner shoot  FILM [KEYS...] [--max-hours H] [--min-headroom GB] [--allow-remote]
  python -m atomic_flix.runner progress PROJECT

`shoot` takes the same road as `atomic-flix shoot` (cli/shoot_steps.clear_to_shoot): FILM must be a film folder
whose gate 5 holds the person's yes, every planned job planned under that yes, and lint clear. `plan` into a film
folder draws its takes on that yes too. A heavy job never starts while commit headroom is under the floor (default:
the heaviest job's commit_gb plus 5 GB; `--min-headroom 0` turns it off).

BATCH.json: {"silent_ok": false, "requests": [{"key": "S02", "graph": "graphs/sung-pinned.json", "wording": "...",
"inputs": {"opening_still": "stills/S02.png", "audio": "plan/S02.voice-soft.wav"}, "seconds": 9, "vocal": true}]}
Paths are read from the project folder and must stay inside it (a graph may also be one of the kit's own). A request
may carry "seed" (a whole number) to re-render with a known seed; "extra", "kind", "fps", "width" and "height" as in
`Request`.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from pathlib import Path

from .budget import estimate, gate_text
from .check import check_hosts
from .jobs import RUNNING, UNKNOWN, WAITING, JobStore
from .ledger import read_rows
from .sched import LoadGate, headroom_floor
from .shoot import Request, Runner, plan_batch
from .template import TemplateError
from ..cli.common import Film, StepError
from ..cli.shoot_steps import clear_to_shoot      # the film verb's own checks: one road to GPU time
from ..project import FilmFolder, ProjectError, draw_batch

DEFAULT_HOSTS = "127.0.0.1:8188,127.0.0.1:8189"


def _hosts(text: str) -> list[str]:
    return [h.strip() for h in text.split(",") if h.strip()]


def _waiting(film_dir: Path, keys: list[str] | None = None) -> list[dict]:
    return [j for j in JobStore(film_dir).load_all() if j["state"] in (WAITING, RUNNING, UNKNOWN)
            and (not keys or j["key"] in keys)]


def _estimate(film_dir: Path, log: Path, hosts: list[str], keys: list[str] | None = None):
    jobs = _waiting(film_dir, keys)
    heaviest = max((j.get("commit_gb", 0) for j in jobs), default=0)
    parallel = heaviest <= 0 or LoadGate().fits_alongside(heaviest)
    return estimate(jobs, read_rows(log), hosts=len(hosts), parallel=parallel)


def _plan(film_dir: Path, batch_file: str) -> int:
    batch = json.loads(Path(batch_file).read_text(encoding="utf-8"))
    is_film = FilmFolder(film_dir).film.is_file()
    try:
        requests = [Request(**item) for item in batch["requests"]]
        extra = {"approval": draw_batch(film_dir, len(requests), check_only=True)} if is_film else None
        jobs = plan_batch(film_dir, requests, silent_ok=bool(batch.get("silent_ok", False)), extra_fields=extra)
        if is_film:
            draw_batch(film_dir, len(jobs))
    except (TemplateError, ProjectError, TypeError, KeyError, ValueError) as err:
        print(f"refused: {err}", file=sys.stderr)
        return 1
    for job in jobs:
        print(f"{job['key']} r{job['n']:03d}: planned, {job['frames']} frames, seed {job['seed']}")
    return 0


def _clear(film_dir: Path, keys: list[str] | None) -> str | None:
    """None when the film may shoot; else why not."""
    try:
        clear_to_shoot(Film.open(film_dir), keys)
    except StepError as problem:
        return str(problem)
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m atomic_flix.runner", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("verb", choices=["ping", "plan", "budget", "shoot", "progress"])
    parser.add_argument("film_dir", nargs="?")
    parser.add_argument("rest", nargs="*", help="plan: the batch file; shoot: shot keys")
    parser.add_argument("--hosts", default=os.environ.get("ATOMIC_FLIX_HOSTS", DEFAULT_HOSTS))
    parser.add_argument("--allow-remote", action="store_true", help="accept hosts that are not on this machine")
    parser.add_argument("--log", default="log/jobs.jsonl", help="the job ledger (JSON lines)")
    parser.add_argument("--timeout", type=float, default=3600.0, help="seconds to wait for one job")
    parser.add_argument("--max-hours", type=float, help="shoot: refuse when the estimate is over this many GPU hours")
    parser.add_argument("--min-headroom", type=float, metavar="GB",
                        help="shoot: the commit-headroom floor for heavy jobs (default: heaviest commit_gb + 5; "
                             "0 turns it off)")
    args = parser.parse_args(argv)
    hosts = _hosts(args.hosts)

    if args.verb == "ping":
        account = check_hosts(hosts, allow_remote=args.allow_remote)
        print("\n".join(account.lines))
        return 0 if account.ok else 1
    if not args.film_dir:
        parser.error(f"{args.verb} needs a PROJECT folder")
    film_dir = Path(args.film_dir)
    log = Path(args.log)

    if args.verb == "plan":
        if len(args.rest) != 1:
            parser.error("plan PROJECT BATCH.json")
        return _plan(film_dir, args.rest[0])
    if args.verb == "progress":
        counts = Counter((j["key"], j["state"]) for j in JobStore(film_dir).load_all())
        for (key, state), n in sorted(counts.items()):
            print(f"{key}: {n} {state}")
        return 0
    keys = args.rest or None
    if args.verb == "shoot":
        refusal = _clear(film_dir, keys)
        if refusal:
            print(f"refused: {refusal}", file=sys.stderr)
            return 2
    if not _waiting(film_dir, keys):
        print("nothing waiting: every job here is done or errored (plan new ones with `plan`)")
        return 0
    est = _estimate(film_dir, log, hosts, keys)
    print(gate_text(est))
    if args.verb == "budget":
        return 0
    if args.max_hours is not None and (est.gpu_hours is None or est.gpu_hours > args.max_hours):
        print(f"refused: the estimate is over --max-hours {args.max_hours}", file=sys.stderr)
        return 1
    floor = headroom_floor(_waiting(film_dir, keys), args.min_headroom)
    try:
        runner = Runner(film_dir, hosts, machine_log_path=log, timeout_s=args.timeout, min_headroom_gb=floor,
                        allow_remote=args.allow_remote)
    except ValueError as problem:
        print(f"refused: {problem}", file=sys.stderr)
        return 1
    summary = runner.run(keys)
    per = summary["gpu_s_per_video_s"]
    print(f"{summary['made']} renders, {summary['errored']} errored, {summary['gpu_hours']:.2f} GPU hours"
          + (f", {per:.1f} GPU s per video s" if per else "")
          + f"; {summary['still_running']} still running, {summary['not_started']} not started"
          + (f", {summary['unknown']} unknown" if summary.get("unknown") else ""))
    if summary["refused"]:
        print(f"refused: commit headroom fell under the floor of {floor:g} GB; what was not started stays planned",
              file=sys.stderr)
    return 0 if summary["errored"] == 0 and not summary["refused"] else 1


if __name__ == "__main__":
    sys.exit(main())
