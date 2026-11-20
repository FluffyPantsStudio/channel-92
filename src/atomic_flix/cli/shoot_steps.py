"""Film steps before and during the GPU time: `lint` (preflight), `budget` (the gate-5 report) and `shoot`.

Lint's process checks read the person's answers through `gate_facts`: the approved song's fingerprint, the bar's
one heard at gate 2, the look's words at gate 3 and the hours approved at gate 5, all from standing.json, so
film.json never has to repeat them. A `gates` block a person writes into film.json still wins.

`clear_to_shoot` is the one road to GPU time, taken by this `shoot` and by `python -m atomic_flix.runner shoot`
alike: gate 5 must hold the person's yes, every planned job must have been planned under that yes, and lint must be
clear. New takes are drawn on the batch the yes approved (its takes, frame size and hours), so a plan that differs
or a second batch needs the gate reopened and a new answer.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Sequence

from ..eval.hook import eval_refusal
from ..gates import GateRefused
from ..lint import load_book, preflight, vet
from ..lint.report import write_reports
from ..lint.rules_process import batch_of
from ..project import ProjectError, draw_batch, load_standing, require_gate
from ..runner import JobStore, Request, Runner, estimate, gate_text, load_meta, plan_batch, read_rows
from ..runner.jobs import RUNNING, UNKNOWN, WAITING
from ..runner.sched import headroom_floor
from ..runner.template import TemplateError
from .common import Film, StepError, film_argument, parser, read_json, write_json
from .setup_steps import require_aspect

BUDGET = "plan/budget.json"
DEFAULT_HOSTS = "127.0.0.1:8188,127.0.0.1:8189"


def default_log(film: Film) -> Path:
    """The machine's job log, `log/jobs.jsonl` beside the film folders (shared by every film on this machine)."""
    return film.root.parent / "log" / "jobs.jsonl"


def gate_facts(film: Film) -> dict:
    """What lint needs to know of the gates, from standing.json (film.json's own `gates` block wins)."""
    facts: dict[str, dict] = {}
    try:
        book = load_standing(film.folder)
    except ProjectError:
        book = None
    if book is not None:
        gates = book.gates
        if gates.passed("song") and book.song is not None:
            facts["song"] = {"sha256": book.song.sha256, "file": book.song.file}
            facts["bars"] = {"by_ear": True, "words": gates.record("song").latest.words}
        if gates.passed("looks"):
            facts["look"] = {"words": gates.record("looks").latest.words}
        if gates.passed("spend") and book.batch is not None:
            facts["spend"] = {"budget_s": book.batch.busy_s}    # the hours approved, not the file as it is now
    for name, written in (film.data.get("gates") or {}).items():
        facts[name] = {**facts.get(name, {}), **written}
    return facts


def load_checked_book(film: Film):
    try:
        book = load_book(film.root)
    except (FileNotFoundError, KeyError, ValueError) as problem:
        raise StepError(f"lint cannot read the film: {problem}") from None
    book.film = {**book.film, "gates": gate_facts(film)}
    return book


def _lint(argv: Sequence[str]) -> int:
    p = parser("lint", "Preflight before any GPU time: every rule learned on the first film, every question a judge\n"
                       "or the person must answer about a first frame, and the batch's GPU hours. Writes\n"
                       "plan/report.md (gate 5) and plan/board.html (gate 4). Exit code 1 when anything blocks.")
    film_argument(p)
    p.add_argument("--vet", action="store_true", help="the rules only: no picture questions, no report")
    args = p.parse_args(argv)
    film = Film.open(args.film)
    book = load_checked_book(film)
    if args.vet:
        findings = vet(book)
        for finding in findings:
            print(finding.line())
        return 1 if any(f.level == "block" for f in findings) else 0
    verdict = preflight(book)
    for finding in verdict.findings:
        print(finding.line())
    for item in verdict.open_review:
        print(f"REVIEW {item.key:<6} {item.id}: {'unanswered' if item.awaiting else item.answer}")
    account, board = write_reports(book, verdict, film.path("plan"))
    if verdict.batch is not None:
        print(f"{verdict.batch.takes} takes, about {verdict.batch.gpu_hours:.2f} GPU h")
    print(f"{'BLOCKED' if verdict.blocked else 'clear'}: {film.folder.relative(account)} and "
          f"{film.folder.relative(board)}")
    return 1 if verdict.blocked else 0


def _pseudo_jobs(film: Film, tasks: dict, takes: dict[str, int], graphs: dict[str, str]) -> list[dict]:
    width, height = film.frame
    jobs = []
    for key, task in tasks.items():
        graph = graphs["vocal" if task.get("type") == "vocal" else "other"]
        for _ in range(takes[key]):
            jobs.append({"graph": graph, "width": width, "height": height, "fps": film.fps,
                         "frames": int(task["seconds"]) * film.fps + 1})
    return jobs


def _budget(argv: Sequence[str]) -> int:
    p = parser("budget", "The gate-5 report: how many takes, at what size, and the GPU hours they will hold the\n"
                         "cards. Hours come from this machine's job log when it has measured renders of the same\n"
                         "graph, else from the rates measured on the first film. Writes plan/budget.json, the\n"
                         "hours the person is asked to approve. Takes per shot: film.json batch.takes, else the\n"
                         "shot list's `takes:`, else 4.")
    film_argument(p)
    p.add_argument("--log", type=Path, help="the machine's job log (default: log/jobs.jsonl beside the film)")
    p.add_argument("--sung-graph", default="sung.json", help="graph name of vocal renders, to find them in the log")
    p.add_argument("--plate-graph", default="plate.json", help="graph name of other renders, to find them in the log")
    p.add_argument("--hosts", type=int, default=2, help="GPU hosts that will share the batch")
    args = p.parse_args(argv)
    film = Film.open(args.film)
    tasks = film.tasks()
    book = load_checked_book(film)
    batch = batch_of(book)
    takes = {key: row.takes for key, row in batch.rows.items()}
    rows = read_rows(args.log or default_log(film))
    graphs = {"vocal": Path(args.sung_graph).name, "other": Path(args.plate_graph).name}
    measured = estimate(_pseudo_jobs(film, tasks, takes, graphs), rows, hosts=args.hosts, parallel=False)
    use_log = measured.gpu_hours is not None
    busy_s = measured.gpu_hours * 3600 if use_log else batch.busy_s
    record = {"takes": batch.takes, "size": list(film.frame), "busy_s": round(busy_s, 1),
              "gpu_hours": round(busy_s / 3600, 3), "basis": measured.basis if use_log else
              "rates measured on the first film (no renders of these graphs in this machine's log)",
              "per_shot": {key: {"takes": row.takes, "seconds": row.seconds, "rate": row.rate,
                                 "busy_s": round(row.busy_s, 1)} for key, row in batch.rows.items()}}
    write_json(film.path(BUDGET), record, "budget")
    print(gate_text(measured) if use_log else
          f"{batch.takes} takes at {film.frame[0]}x{film.frame[1]}: about {batch.gpu_hours:.2f} GPU hours at the "
          f"first film's rates ({batch.wall_hours:.2f} h on {batch.cards} card).")
    print(f"wrote {BUDGET}. Ask the person: \"May this batch run for these hours?\" "
          "(atomic-flix gate FILM ask spend, then answer)")
    return 0


def _requests(film: Film, tasks: dict, takes: dict[str, int], graphs: dict[str, str | None]) -> list[Request]:
    width, height = film.frame
    requests = []
    for key, task in tasks.items():
        vocal = task.get("type") == "vocal"
        graph = graphs["vocal" if vocal else "other"]
        if graph is None:
            raise StepError(f"{key} needs a {'--sung-graph' if vocal else '--plate-graph'}")
        prompt_path = film.path(f"plan/{key}.prompt.txt")
        if not prompt_path.is_file():
            raise StepError(f"{key} has no prompt (plan/{key}.prompt.txt); run `atomic-flix plan`")
        inputs = {"opening_still": task["still"]}
        if vocal:
            inputs["audio"] = task["audio"]
        if task.get("closing_still") and "closing_still" in load_meta(graph).needs:
            inputs["closing_still"] = task["closing_still"]
        for _ in range(takes[key]):
            requests.append(Request(key=key, graph=graph, wording=prompt_path.read_text(encoding="utf-8").strip(),
                                    inputs=inputs, seconds=int(task["seconds"]), vocal=vocal, fps=film.fps,
                                    width=width, height=height, kind=task.get("type")))
    return requests


OPEN_STATES = (WAITING, RUNNING, UNKNOWN)


def pending_jobs(film_root: Path, keys: Sequence[str] | None = None) -> list[dict]:
    """Jobs not yet done or errored (planned, running, or unknown), for KEYS or all."""
    try:
        jobs = JobStore(film_root).load_all()
    except ValueError as problem:
        raise StepError(str(problem)) from None
    return [job for job in jobs if job["state"] in OPEN_STATES and (not keys or job["key"] in keys)]


def clear_to_shoot(film: Film, keys: Sequence[str] | None = None):
    """Refuse (StepError) unless gate 5 holds the person's yes, the director has chosen the aspect, every planned job was planned under that yes, the eval
    report is fresh and not BLOCKED for gate 5 (only gate 5's own ask, answer and batch may have changed since), and
    lint is clear; return the checked lint book. Both `shoot` command lines call this first."""
    try:
        require_gate(film.folder, "spend")
        standing = load_standing(film.folder)
    except (GateRefused, ProjectError) as problem:
        raise StepError(str(problem)) from None
    require_aspect(film)
    approved = standing.batch.at if standing.batch is not None else None
    strays = [f"{job['key']} r{job['n']:03d}" for job in pending_jobs(film.root, keys)
              if job["state"] == WAITING and job.get("approval") != approved]
    if strays:
        raise StepError(f"{', '.join(strays)} were planned outside gate 5's latest yes (an earlier answer, or none); "
                        "the person's yes covers only takes planned under it")
    refusal = eval_refusal(film.root, "spend", answering=True)
    if refusal:
        raise StepError(f"{refusal} (the yes at gate 5 covers the film as it was evaluated)")
    book = load_checked_book(film)
    if preflight(book).blocked:
        raise StepError("lint blocks this batch; run `atomic-flix lint` and fix what it lists")
    return book


def _plan_new_takes(film: Film, book, tasks: dict, args) -> list[dict]:
    """Plan the takes of TASKS, drawn on gate 5's approved batch; refused before anything is written when the plan
    differs from the approved one or would pass its count."""
    batch = batch_of(book)
    if not film.path(BUDGET).is_file():
        raise StepError(f"no {BUDGET}; run `atomic-flix budget` and ask gate 5")
    plan = (batch.takes, tuple(film.frame), float(read_json(film.path(BUDGET))["busy_s"]))
    takes = {key: row.takes for key, row in batch.rows.items()}
    graphs = {"vocal": str(args.sung_graph.resolve()) if args.sung_graph else None,
              "other": str(args.plate_graph.resolve()) if args.plate_graph else None}
    requests = _requests(film, tasks, takes, graphs)
    try:
        stamp = draw_batch(film.folder, len(requests), plan=plan, check_only=True)
        jobs = plan_batch(film.root, requests, film=film.root.name, extra_fields={"approval": stamp})
        draw_batch(film.folder, len(jobs), plan=plan)
    except ProjectError as problem:
        raise StepError(f"refused: {problem}") from None
    except TemplateError as problem:
        raise StepError(f"refused before anything was queued: {problem}") from None
    return jobs


def _shoot(argv: Sequence[str]) -> int:
    p = parser("shoot", "Render the planned shots on the ComfyUI hosts. Refuses unless gate 5 holds the person's yes\n"
                        "and lint is clear. Jobs left planned, running or unknown by an earlier run are picked up\n"
                        "first; new takes are planned only when none are waiting, and only as many as gate 5's yes\n"
                        "covers (the same plan: takes, size and hours). Writes renders/<key>/rNNN.mp4, the job\n"
                        "files and the film's ledger. A heavy job never starts while commit headroom is under the\n"
                        "floor: by default the heaviest graph's commit_gb plus 5 GB.")
    film_argument(p)
    p.add_argument("keys", nargs="*", help="only these shots")
    p.add_argument("--sung-graph", type=Path, help="the ComfyUI API graph for vocal shots (in the film folder)")
    p.add_argument("--plate-graph", type=Path, help="the graph for mute shots and cutaways (in the film folder)")
    p.add_argument("--hosts", default=os.environ.get("ATOMIC_FLIX_HOSTS", DEFAULT_HOSTS))
    p.add_argument("--allow-remote", action="store_true", help="accept hosts that are not on this machine")
    p.add_argument("--log", type=Path, help="the machine's job log (default: log/jobs.jsonl beside the film)")
    p.add_argument("--timeout", type=float, default=3600.0, help="seconds to wait for one render")
    p.add_argument("--poll", type=float, default=3.0, help="seconds between looks at a host's history")
    p.add_argument("--min-headroom", type=float, metavar="GB",
                   help="the commit-headroom floor for heavy jobs (default: heaviest commit_gb + 5; 0 turns it off)")
    args = p.parse_args(argv)
    film = Film.open(args.film)
    book = clear_to_shoot(film, args.keys)
    tasks = {key: task for key, task in film.tasks().items() if not args.keys or key in args.keys}
    if not pending_jobs(film.root, list(tasks)):
        print(f"planned {len(_plan_new_takes(film, book, tasks, args))} render(s)")
    floor = headroom_floor(pending_jobs(film.root, list(tasks)), args.min_headroom)
    hosts = [host.strip() for host in args.hosts.split(",") if host.strip()]
    try:
        runner = Runner(film.root, hosts, machine_log_path=args.log or default_log(film), timeout_s=args.timeout,
                        poll_s=args.poll, min_headroom_gb=floor, allow_remote=args.allow_remote)
    except ValueError as problem:
        raise StepError(str(problem)) from None
    summary = runner.run(list(tasks))
    print(f"{summary['made']} renders, {summary['errored']} errored, {summary['gpu_hours']:.2f} GPU hours; "
          f"{summary['still_running']} still running, {summary['not_started']} not started"
          + (f", {summary['unknown']} unknown" if summary.get("unknown") else ""))
    if summary["refused"]:
        print(f"refused: commit headroom fell under the floor of {floor:g} GB; what was not started stays planned")
    return 0 if summary["errored"] == 0 and not summary["refused"] else 1


COMMANDS = {
    "lint": ("preflight: every rule and picture question; plan/report.md and plan/board.html", _lint),
    "budget": ("the gate-5 hours for the planned batch (plan/budget.json)", _budget),
    "shoot": ("render the plan on the ComfyUI hosts once gate 5 says yes and lint is clear", _shoot),
}
