"""What is compared between a film and the first one, and the target for each.

Every metric is lower-is-better: the kit's aim (KIT-ROADMAP) is a film better and cheaper than the first. Where
our own documents set a number, that is the target; elsewhere the target is to come in under the first film.
"""

from __future__ import annotations

from dataclasses import dataclass

BELOW_FIRST = "below"     # target: under the first film's value
AT_MOST = "at_most"       # target: value <= limit
UNDER = "under"           # target: value < limit
UNDER_SHARE = "share"     # target: value < limit x the first film's value


@dataclass(frozen=True)
class Aim:
    rule: str
    limit: float | None = None
    why: str = ""

    def describe(self, first: float | None) -> str:
        if self.rule == BELOW_FIRST:
            return "below the first film"
        if self.rule == AT_MOST:
            return f"at most {self.limit:g}"
        if self.rule == UNDER:
            return f"under {self.limit:,g}"
        if first is None:
            return f"under {self.limit:g} of the first film"
        return f"under {self.limit * first:,.0f} ({self.limit:g} of the first film)"


@dataclass(frozen=True)
class Metric:
    key: str
    label: str
    digits: int
    aim: Aim


TARGETS_FROM = {
    "gpu_hours_total": "KIT-ROADMAP, Totals: budget the first film's 20 to 35 GPU hours for the next film",
    "cost_usd": "OPERATING, what to record: the trial worked if the cost is under half the first film's",
    "driver_median_tokens": "OPERATING, rule 2: the driver's median call under 150,000 tokens",
}

METRICS: tuple[Metric, ...] = (
    Metric("gpu_hours_total", "GPU hours, all logged jobs", 1, Aim(AT_MOST, 35.0, TARGETS_FROM["gpu_hours_total"])),
    Metric("gpu_hours_vocal", "GPU hours, vocal renders", 1, Aim(BELOW_FIRST)),
    Metric("gpu_hours_cutaway", "GPU hours, cutaway and mute renders", 1, Aim(BELOW_FIRST)),
    Metric("gpu_hours_still", "GPU hours, stills and edits", 2, Aim(BELOW_FIRST)),
    Metric("gpu_hours_test", "GPU hours, model tests", 2, Aim(BELOW_FIRST)),
    Metric("renders_per_finished_second", "Renders per finished second", 2, Aim(BELOW_FIRST)),
    Metric("vocal_renders_per_shot", "Renders per vocal shot", 1, Aim(BELOW_FIRST)),
    Metric("cutaway_renders_per_shot", "Renders per cutaway or mute shot", 1, Aim(BELOW_FIRST)),
    Metric("reshoot_passes", "Passes re-rendering every vocal shot", 0, Aim(BELOW_FIRST)),
    Metric("builds", "Numbered builds (cuts)", 0, Aim(BELOW_FIRST)),
    Metric("days_to_acceptance", "Calendar days to the person's acceptance", 0, Aim(BELOW_FIRST)),
    Metric("rendered_to_finished", "Rendered seconds per finished second", 1, Aim(BELOW_FIRST)),
    Metric("driver_calls", "Model calls", 0, Aim(BELOW_FIRST)),
    Metric("cost_usd", "Model cost, USD at list prices", 0, Aim(UNDER_SHARE, 0.5, TARGETS_FROM["cost_usd"])),
    Metric("driver_median_tokens", "Driver's median tokens per call", 0,
           Aim(UNDER, 150_000.0, TARGETS_FROM["driver_median_tokens"])),
)
