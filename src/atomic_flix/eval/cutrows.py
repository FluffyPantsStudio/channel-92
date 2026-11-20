"""The cut's own checks read into eval rows, never measured again: the newest cut's audit (`cuts/vNN.audit.json`,
with the song's loudness in its `audio`), the grade's account (`cuts/vNN-toned.tone.json`) and the flash check on
the graded film (`cuts/vNN-toned-strobe.json`). The newest cut is the highest vNN among the cut films and audits, so a
newer film without its audit leaves the rows unchecked. A result file that is missing, or a value of the wrong
shape, leaves its row unchecked."""

from __future__ import annotations

import re
from numbers import Real

from ..cut.loudness import PEAK_CEILING_DB, QUIET_WARNING_LUFS
from .context import Context, Part
from .rows import FAIL, PASS, UNCHECKED, Row, make
from .rulesmap import entries

CUT_FILE = re.compile(r"v(\d{2,})(?:-toned)?\.(?:mp4|audit\.json)")
ROUNDING_DB = 0.05          # the audit's numbers are rounded to two places
SPREAD_SLACK = 0.004        # about one 8-bit code value: a wider spread than this is the grade's doing


def newest_cut(ctx: Context) -> str | None:
    """`cuts/vNN` of the newest cut (a film or an audit), or None when there is no cut."""
    numbers = [int(m.group(1)) for path in ctx.path("cuts").glob("v*") if (m := CUT_FILE.fullmatch(path.name))]
    return f"cuts/v{max(numbers):02d}" if numbers else None


def _list(value: object) -> list[str] | None:
    return [str(item) for item in value] if isinstance(value, list) else None


def _number(value: object) -> bool:
    return isinstance(value, Real) and not isinstance(value, bool)


def _audit(entry, stem, audit: Part, tone: Part, strobe: Part) -> Row:
    if not audit.ok:
        return make(entry, "film", UNCHECKED, audit.problem)
    errors = _list(audit.value.get("errors"))
    if errors is None:
        return make(entry, "film", UNCHECKED, f"{stem}.audit.json has no list of errors")
    return make(entry, "film", FAIL, f"{stem}.audit.json: " + "; ".join(errors)) if errors else \
        make(entry, "film", PASS, f"{stem}.audit.json: no errors")


def _audit_warnings(entry, stem, audit, tone, strobe) -> Row:
    if not audit.ok:
        return make(entry, "film", UNCHECKED, audit.problem)
    warnings = _list(audit.value.get("warnings"))
    if warnings is None:
        return make(entry, "film", UNCHECKED, f"{stem}.audit.json has no list of warnings")
    return make(entry, "film", FAIL, f"{stem}.audit.json: " + "; ".join(warnings)) if warnings else \
        make(entry, "film", PASS, f"{stem}.audit.json: no warnings")


def _loud(entry, stem, audit, tone, strobe) -> Row:
    if not audit.ok:
        return make(entry, "film", UNCHECKED, audit.problem)
    audio = audit.value.get("audio")
    if not isinstance(audio, dict) or not (_number(audio.get("peak_after_db")) and _number(audio.get("lufs_after"))):
        return make(entry, "film", UNCHECKED, f"{stem}.audit.json has no song loudness in numbers")
    problems = []
    if audio["peak_after_db"] > PEAK_CEILING_DB + ROUNDING_DB:
        problems.append(f"peak {audio['peak_after_db']} dBFS over {PEAK_CEILING_DB}")
    if audio["lufs_after"] < QUIET_WARNING_LUFS:
        problems.append(f"{audio['lufs_after']} LUFS, under {QUIET_WARNING_LUFS}")
    fine = f"{audio['lufs_after']} LUFS, peak {audio['peak_after_db']} dBFS"
    return make(entry, "film", FAIL, "; ".join(problems)) if problems else make(entry, "film", PASS, fine)


def _graded(entry, stem, audit, tone, strobe) -> Row:
    if tone.ok:
        return make(entry, "film", PASS, f"{stem}-toned.tone.json is there")
    return make(entry, "film", FAIL, f"{stem} has no graded version ({tone.problem}); run `atomic-flix grade`")


def _spread(entry, stem, audit, tone, strobe) -> Row:
    if not tone.ok:
        return make(entry, "film", UNCHECKED, tone.problem)
    before, after = tone.value.get("spread_before"), tone.value.get("spread_after")
    if not isinstance(before, dict) or not isinstance(after, dict) or not after:
        return make(entry, "film", UNCHECKED, f"{stem}-toned.tone.json has no spread before and after the grade")
    odd = [name for name in after if not _number(after[name]) or not _number(before.get(name))]
    if odd:
        return make(entry, "film", UNCHECKED, f"{stem}-toned.tone.json: no numbers for {', '.join(odd)}")
    wider = [f"{name} {before[name]:.4f} -> {value:.4f}" for name, value in after.items()
             if value > before[name] + SPREAD_SLACK]
    return make(entry, "film", FAIL, "the grade widened: " + ", ".join(wider)) if wider else \
        make(entry, "film", PASS, "the spread did not widen")


def _grain(entry, stem, audit, tone, strobe) -> Row:
    if not tone.ok:
        return make(entry, "film", UNCHECKED, tone.problem)
    if "grain" not in tone.value:
        return make(entry, "film", UNCHECKED, f"{stem}-toned.tone.json does not say whether grain was laid")
    grain = tone.value["grain"]
    return make(entry, "film", FAIL, f"grain in the grade: {grain!r}") if grain is not None else \
        make(entry, "film", PASS, "no grain in the grade")


def _spans(value: object) -> str:
    if not isinstance(value, list):
        return ""
    return ", ".join(f"{span[0]}-{span[1]} s" for span in value if isinstance(span, list) and len(span) == 2)


def _flash(entry, stem, audit, tone, strobe) -> Row:
    if not strobe.ok:
        return make(entry, "film", UNCHECKED, strobe.problem)
    passed = strobe.value.get("passed")
    if passed is True:
        return make(entry, "film", PASS, f"{strobe.value.get('flash_count', '?')} flash(es), under the limit")
    if passed is not False:
        return make(entry, "film", UNCHECKED, f"{stem}-toned-strobe.json does not say passed or failed")
    return make(entry, "film", FAIL, f"the flash check failed: {_spans(strobe.value.get('failing')) or 'no spans'}")

CHECKS = {"CT-AUDIT": _audit, "CT-AUDIT-W": _audit_warnings, "CT-LOUD": _loud, "CT-GRADE": _graded,
          "CT-SPREAD": _spread, "CT-GRAIN": _grain, "CT-FLASH": _flash}


def cut_rows(ctx: Context) -> list[Row]:
    mapped = entries("cut")
    stem = newest_cut(ctx)
    if stem is None:
        return [make(entry, "film", UNCHECKED, "no cut in cuts/ yet") for entry in mapped]
    parts = (ctx.read_json(f"{stem}.audit.json"), ctx.read_json(f"{stem}-toned.tone.json"),
             ctx.read_json(f"{stem}-toned-strobe.json"))
    return [CHECKS[entry["id"]](entry, stem, *parts) for entry in mapped if entry["id"] in CHECKS]
