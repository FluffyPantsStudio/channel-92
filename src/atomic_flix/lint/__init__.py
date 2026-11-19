"""vet and preflight: our first film's lessons as checks on prompts, plans and first-frame stills."""

from . import rules_plan, rules_process, rules_prompt, rules_still  # noqa: F401  (registers the checks)
from .book import Book, book_from_case, book_from_plan, load_book
from .engine import after_batch_questions, preflight, review_items, vet
from .findings import Finding, ReviewItem, Verdict
from .registry import RULE_DATA, RULE_INDEX, check_rule, rule_ids, run_rules
from .report import board_html, report_markdown

__all__ = ["Book", "Finding", "RULE_DATA", "RULE_INDEX", "ReviewItem", "Verdict", "after_batch_questions",
           "board_html", "book_from_case", "book_from_plan", "check_rule", "load_book", "preflight", "report_markdown",
           "review_items", "rule_ids", "run_rules", "vet"]
