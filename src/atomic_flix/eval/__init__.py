"""The eval: proof, per film, that the kit's rules were honored, kept as part of the process.

`atomic-flix eval FILM` runs every rule of the rules map (`data/rules-map.json`) on the film's own files and its
process record and writes `FILM/eval/report.json` and `report.md`. Gates 5 and 6 are not asked while the report says
BLOCKED for that gate or is stale (`hook.require_eval`). See docs/eval.md.

Only the light parts are imported here: the gate actions read saved reports through `hook`, and the eval itself
(`run.evaluate`, `report.write_report`) reads the lint book through the cli package, which imports the eval verb.
"""

from .hook import eval_refusal, require_eval
from .rows import BLOCKED, CLEAN, WARN, Row
from .saved import REPORT_JSON, REPORT_MD, ReportError, read_report, stale_inputs

__all__ = ["BLOCKED", "CLEAN", "REPORT_JSON", "REPORT_MD", "ReportError", "Row", "WARN", "eval_refusal",
           "read_report", "require_eval", "stale_inputs"]
