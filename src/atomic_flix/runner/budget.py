"""The hours a batch will take, estimated before it is queued, from what past renders cost (gate 5).

For each planned job the rate is the median GPU seconds per video second of past ledger rows, chosen in order:
the same graph at the same size; the same graph at another size, scaled by pixel count; any graph at the same size.
Without any of those there is no estimate, and the text says so rather than guessing.

Wall hours: with both GPUs free to run at once the work splits over the hosts; under the one-heavy-load rule the
GPUs take turns, so the batch holds both of them for the whole sum.
"""

from __future__ import annotations

import statistics
from collections import Counter
from dataclasses import dataclass
from pathlib import PurePath


@dataclass(frozen=True)
class Estimate:
    takes: int
    sizes: tuple[str, ...]
    video_s: float
    gpu_s_per_video_s: float | None
    gpu_hours: float | None
    wall_hours: float | None
    gpu_hours_mean: float | None
    hosts: int
    parallel: bool
    basis: str
    rows_used: int


def _graph_name(value: str | None) -> str:
    return PurePath(value or "").name


def _row_graph(row: dict) -> str:
    """A row's graph name; rows from our earlier runner call it "workflow"."""
    return _graph_name(row.get("graph") or row.get("workflow"))


def _rates(job: dict, rows: list[dict]) -> tuple[list[float], str]:
    """Past GPU seconds per video second that apply to `job`, and where they came from."""
    graph = _graph_name(job.get("graph"))
    pixels = job["width"] * job["height"]

    def per_video_s(row: dict) -> float:
        return row["busy_s"] / row["video_s"]

    same = [r for r in rows if _row_graph(r) == graph and r.get("width") == job["width"]
            and r.get("height") == job["height"]]
    if same:
        return [per_video_s(r) for r in same], "same graph and size"
    other_size = [r for r in rows if _row_graph(r) == graph and r.get("width") and r.get("height")]
    if other_size:
        return ([per_video_s(r) * pixels / (r["width"] * r["height"]) for r in other_size],
                "same graph, other size scaled by pixels")
    any_graph = [r for r in rows if r.get("width") == job["width"] and r.get("height") == job["height"]]
    if any_graph:
        return [per_video_s(r) for r in any_graph], "other graphs at this size"
    return [], "no measured renders"


def estimate(jobs: list[dict], rows: list[dict], hosts: int = 2, parallel: bool = True) -> Estimate:
    """Estimate GPU and wall hours for `jobs` (job records: graph, width, height, frames, fps).

    The estimate uses the median rate; `gpu_hours_mean` uses the mean, which carries the slow tail (a degraded
    card, two loads fighting for memory) and is the figure to plan the worst case on."""
    measured = [r for r in rows if r.get("ok") and (r.get("busy_s") or 0) > 0 and (r.get("video_s") or 0) > 0]
    total_video = 0.0
    total_median = 0.0
    total_mean = 0.0
    known = bool(jobs)
    bases: Counter[str] = Counter()
    used = 0
    for job in jobs:
        video_s = job["frames"] / job["fps"]
        total_video += video_s
        rates, basis = _rates(job, measured)
        bases[basis] += 1
        used = max(used, len(rates))
        if not rates:
            known = False
            continue
        total_median += statistics.median(rates) * video_s
        total_mean += statistics.fmean(rates) * video_s
    sizes = tuple(sorted({f"{j['width']}x{j['height']}" for j in jobs}))
    gpu_hours = total_median / 3600 if known else None
    lanes = max(1, hosts) if parallel else 1
    return Estimate(
        takes=len(jobs), sizes=sizes, video_s=total_video,
        gpu_s_per_video_s=total_median / total_video if known and total_video else None,
        gpu_hours=gpu_hours, wall_hours=gpu_hours / lanes if gpu_hours is not None else None,
        gpu_hours_mean=total_mean / 3600 if known else None,
        hosts=hosts, parallel=parallel,
        basis="; ".join(f"{name} ({n} job{'s' if n != 1 else ''})" for name, n in bases.most_common()),
        rows_used=used,
    )


def gate_text(est: Estimate) -> str:
    """The question for gate 5, in one paragraph."""
    size = ", ".join(est.sizes) or "no size"
    each = est.video_s / est.takes if est.takes else 0.0
    head = f"{est.takes} takes at {size}, about {each:.1f} s of video each ({est.video_s:.0f} s in all)"
    if est.gpu_hours is None:
        return f"{head}: no measured renders to estimate from ({est.basis}). Run one test take first."
    n_cards = "both GPUs" if est.hosts == 2 else f"{est.hosts} GPUs"
    turns = "running side by side" if est.parallel else "taking turns (one heavy load at a time)"
    lanes = est.gpu_hours / est.wall_hours if est.wall_hours else 1.0
    worst = est.gpu_hours_mean / lanes
    return (f"{head}: about {est.gpu_hours:.2f} GPU hours at {est.gpu_s_per_video_s:.1f} GPU s per video s "
            f"(median; {est.gpu_hours_mean:.2f} at the mean rate); {n_cards} held about {est.wall_hours:.2f} h, "
            f"up to {worst:.2f} h, {turns}. From {est.basis}, {est.rows_used} past renders.")
