"""Ledger checks: the process record (standing.json, the job files, the judges' records) says the required events
happened, in order, by the right kind of party.

The raw record is read as well as the gate machine's own load, so that a record the machine would refuse (a
reviewer used twice, an answer signed by a model) still yields one row per rule naming what is wrong. A rule with
nothing on record to judge (no answers yet, a time that is not a time) never passes: it is unchecked or fails.
"""

from __future__ import annotations

from collections import Counter

from ..gates import PERSON_DIRECT, RELAYED, GateRefused, ReviewLoop, parse_time, reads_as_machine
from ..project.standing import ProjectError, Standing
from .context import Context, read_json_part, shot_list
from .rows import FAIL, PASS, UNCHECKED, Row, make
from .rulesmap import entries

SPEND = "spend"
ANSWER_RULES = ("LG-PERSON", "LG-ARRIVAL", "LG-REUSE")


def shape_problem(standing: dict) -> str | None:
    """Why the gate part of standing.json cannot be read as gates, answers and review rounds (None when it can)."""
    gates = standing.get("gates")
    if not isinstance(gates, dict) or not isinstance(gates.get("gates"), list):
        return "standing.json gates are not a list of gate records"
    if not all(isinstance(r, dict) and isinstance(r.get("answers") or [], list) for r in gates["gates"]):
        return "standing.json holds a gate record that is not a record with a list of answers"
    loops = [gates.get("review") or {}] + list(gates.get("past_reviews") or [])
    if not isinstance(gates.get("past_reviews") or [], list) or not all(
            isinstance(loop, dict) and isinstance(loop.get("rounds") or [], list)
            and all(isinstance(r, dict) for r in loop.get("rounds") or []) for loop in loops):
        return "standing.json review rounds are not lists of round records"
    return None


def _records(standing: dict) -> list[dict]:
    return list(standing["gates"]["gates"])


def _answers(record: dict) -> list[dict]:
    return [a for a in record.get("answers") or [] if isinstance(a, dict)]


def _all_answers(standing: dict) -> list[tuple[str, dict]]:
    return [(str(record.get("gate")), answer) for record in _records(standing) for answer in _answers(record)]


def _verdict(entry: dict, problems: list[str], fine: str, unit: str = "film") -> Row:
    return make(entry, unit, FAIL, "; ".join(problems)) if problems else make(entry, unit, PASS, fine)


def _load(entry, standing):
    try:
        Standing.from_dict(standing)
    except (ProjectError, GateRefused, ValueError, TypeError, KeyError, AttributeError) as problem:
        return make(entry, "film", FAIL, f"the gate machine refuses standing.json: {problem}")
    return make(entry, "film", PASS, "standing.json loads under the gate machine")


def _when(text: object, where: str, problems: list[str]) -> float | None:
    """TEXT as a moment; a text that is no time is added to PROBLEMS, never skipped."""
    try:
        return parse_time(text).timestamp()
    except ValueError:
        problems.append(f"{where}: {text!r} is not a time")
        return None


def _order(entry, standing):
    records = _records(standing)
    problems: list[str] = []
    states = [r.get("state") for r in records]
    for index, record in enumerate(records[1:], start=1):
        gate, before = record.get("gate"), records[index - 1]
        if states[index] == "passed" and states[index - 1] != "passed":
            problems.append(f"{gate} passed while {before.get('gate')} is {states[index - 1]}")
        if not record.get("asked_at"):
            continue
        asked = _when(record["asked_at"], f"{gate} asked_at", problems)
        yeses = [_when(a.get("at"), f"{before.get('gate')} answer", problems)
                 for a in _answers(before) if a.get("approves")]
        if asked is not None and not any(t is not None and t <= asked for t in yeses):
            problems.append(f"{gate} was asked before {before.get('gate')} had a yes")
    return _verdict(entry, problems, f"{states.count('passed')} gate(s) passed, in order")


def _person(entry, answers):
    problems = []
    for gate, answer in answers:
        who = str(answer.get("by") or "")
        if not who.strip() or reads_as_machine(who):
            problems.append(f"{gate} answered by {who!r}, not a person")
        if not str(answer.get("words") or "").strip():
            problems.append(f"{gate} answer at {answer.get('at')} holds no words")
    return _verdict(entry, problems, f"{len(answers)} answer(s), each naming a person and holding words")


def _arrival(entry, answers):
    problems = [f"{gate} answer at {answer.get('at')}: arrival {answer.get('provenance')!r}"
                for gate, answer in answers if answer.get("provenance") not in (PERSON_DIRECT, RELAYED)]
    return _verdict(entry, problems, f"{len(answers)} answer(s), each typed by the person or relayed")


def _reuse(entry, answers):
    seen: dict[tuple, str] = {}
    problems = []
    for gate, answer in answers:
        key = (str(answer.get("words") or "").strip().lower(), answer.get("at"))
        other = seen.setdefault(key, gate)
        if other != gate:
            problems.append(f"{gate} reuses the answer of {other} ({answer.get('at')})")
    return _verdict(entry, problems, f"{len(answers)} answer(s), none recorded at two gates")


def _spend_yeses(standing: dict) -> set[str]:
    records = {r.get("gate"): r for r in _records(standing)}
    return {a["at"] for a in _answers(records.get(SPEND) or {})
            if a.get("approves") is True and isinstance(a.get("at"), str)}


def _batch(entry, standing, ctx):
    if not ctx.jobs.ok:
        return make(entry, "film", UNCHECKED, ctx.jobs.problem)
    jobs = list(ctx.jobs.value)
    if not jobs:
        return make(entry, "film", UNCHECKED, "no job files: nothing was planned or shot yet")
    yeses = _spend_yeses(standing)
    problems = [f"{job['key']} r{job['n']:03d} was planned under {job.get('approval')!r}, not a gate-5 yes"
                for job in jobs if not isinstance(job.get("approval"), str) or job["approval"] not in yeses]
    batch = standing.get("batch") or {}
    under = Counter(job.get("approval") for job in jobs)
    if isinstance(batch, dict) and isinstance(batch.get("at"), str) and batch["at"] in under:
        takes = batch.get("takes")
        if not isinstance(takes, int) or isinstance(takes, bool):
            problems.append(f"gate 5's batch has no whole number of takes: {takes!r}")
        elif under[batch["at"]] > takes:
            problems.append(f"{under[batch['at']]} jobs under the yes of {batch['at']}, which covers {takes}")
    return _verdict(entry, problems, f"{len(jobs)} job(s), each under a gate-5 yes, within its count")


def _loops(standing: dict) -> list[list[dict]]:
    gates = standing["gates"]
    past = [list(loop.get("rounds") or []) for loop in gates.get("past_reviews") or []]
    return past + [list((gates.get("review") or {}).get("rounds") or [])]


def _rounds(entry, standing):
    loops = _loops(standing)
    problems = []
    for number, rounds in enumerate(loops, start=1):
        if not rounds:
            if number == len(loops):
                problems.append("no cold review round on the way to v1 yet")
            continue
        try:
            loop = ReviewLoop.from_dict({"rounds": rounds})
        except (GateRefused, TypeError, KeyError) as problem:
            problems.append(f"review loop {number} cannot be read: {problem}")
            continue
        if not loop.is_clean and loop.stalled is None:
            problems.append(f"review loop {number} ends on a round naming {len(loop.open_errors)} error(s) "
                            f"({rounds[-1].get('reviewer')} on {rounds[-1].get('cut')})")
    return _verdict(entry, problems, f"{sum(map(len, loops))} round(s); every loop ends clean or stalled")


def _fresh(entry, standing):
    names = [str(r.get("reviewer")) for rounds in _loops(standing) for r in rounds]
    twice = sorted(name for name, count in Counter(names).items() if count > 1)
    if not names:
        return make(entry, "film", UNCHECKED, "no review round on record yet")
    return _verdict(entry, [f"reviewer {name} reviewed this film more than once" for name in twice],
                    f"{len(names)} round(s), each by a reviewer new to the film")


def _sent_times(ctx: Context) -> tuple[dict[str, float], dict[str, list[str]]]:
    """The first numeric send time per shot, and per shot the sent jobs that carry no time."""
    first: dict[str, float] = {}
    untimed: dict[str, list[str]] = {}
    for job in ctx.sent_jobs:
        when = job.get("submitted_at")
        if isinstance(when, (int, float)) and not isinstance(when, bool):
            first[job["key"]] = min(first.get(job["key"], when), when)
        else:
            untimed.setdefault(job["key"], []).append(f"r{job['n']:03d}")
    return first, untimed


def _judge_row(entry: dict, ctx: Context, key: str, sent_at: float) -> Row:
    unit, name = f"shot:{key}", f"stills/{key}.json"
    record = read_json_part(ctx.path(name), name)
    judge = (record.value or {}).get("judge") if record.ok else None
    if not isinstance(judge, dict) or not judge.get("at"):
        return make(entry, unit, FAIL, f"{record.problem or name + ' has no judge.at'}, so no look before the "
                                       "batch is on record")
    problems: list[str] = []
    judged = _when(judge["at"], f"{name} judge.at", problems)
    if judged is None:
        return make(entry, unit, FAIL, "; ".join(problems))
    if judged > sent_at:
        return make(entry, unit, FAIL, "the judge looked after the first render was sent")
    return make(entry, unit, PASS, "judged before the first render was sent")


def _judge_rows(entry: dict, ctx: Context) -> list[Row]:
    if not ctx.jobs.ok:
        return [make(entry, "film", UNCHECKED, ctx.jobs.problem)]
    first, untimed = _sent_times(ctx)
    rows = []
    for shot in shot_list(ctx):
        unit = f"shot:{shot.key}"
        if shot.key in untimed:
            rows.append(make(entry, unit, FAIL, f"{', '.join(untimed[shot.key])} sent without a recorded time"))
        elif shot.key not in first:
            rows.append(make(entry, unit, PASS, "no render sent for this shot"))
        else:
            rows.append(_judge_row(entry, ctx, shot.key, first[shot.key]))
    return rows


def _standing_row(entry: dict, ctx: Context) -> Row:
    standing = ctx.standing.value
    rule = entry["id"]
    if rule == "LG-LOAD":
        return _load(entry, standing)
    problem = shape_problem(standing)
    if problem:
        return make(entry, "film", UNCHECKED, problem)
    if rule in ANSWER_RULES:
        answers = _all_answers(standing)
        if not answers:
            return make(entry, "film", UNCHECKED, "no gate answer on record yet")
        return {"LG-PERSON": _person, "LG-ARRIVAL": _arrival, "LG-REUSE": _reuse}[rule](entry, answers)
    if rule == "LG-BATCH":
        return _batch(entry, standing, ctx)
    check = {"LG-ORDER": _order, "LG-ROUNDS": _rounds, "LG-FRESH": _fresh}.get(rule)
    if check is None:
        return make(entry, "film", UNCHECKED, "the ledger has no check written for this rule: a fault of the eval")
    return check(entry, standing)


def ledger_rows(ctx: Context) -> list[Row]:
    rows = []
    for entry in entries("ledger"):
        if entry["id"] == "LG-JUDGE":
            rows += _judge_rows(entry, ctx)
        elif not ctx.standing.ok:
            rows.append(make(entry, "film", UNCHECKED, ctx.standing.problem))
        else:
            rows.append(_standing_row(entry, ctx))
    return rows
