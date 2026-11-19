"""What the person sees: the gate-5 report (takes, size, GPU hours, what still blocks) and the gate-4 board (every
shot's first frame, window and lines on one page)."""

from __future__ import annotations

import html
from pathlib import Path

from ..plan.words import sung_words
from .book import Book
from .engine import after_batch_questions
from .findings import Verdict


def _hours(seconds: float) -> str:
    return f"{seconds / 3600:.2f} h"


def report_markdown(book: Book, verdict: Verdict) -> str:
    """Gate 5: how many takes, at what size, and the hours they will hold the cards; then what blocks."""
    name = book.film.get("name", "the film")
    lines = [f"# {name}: before the batch", ""]
    batch = verdict.batch
    if batch is not None:
        width, height = batch.size
        budget = book.gate("spend").get("budget_s")
        lines += [
            f"**{batch.takes} takes at {width}x{height}, about {batch.gpu_hours:.2f} GPU hours "
            f"({batch.wall_hours:.2f} h on {batch.cards} card{'s' if batch.cards != 1 else ''}).**",
            f"Approved budget: {_hours(budget) if budget is not None else 'none yet'}.",
            "Rates are GPU seconds per video second measured on our first film; a new log replaces them.", "",
            "| Shot | Kind | Pin | Seconds | Takes | Rate | GPU minutes |",
            "|---|---|---|---|---|---|---|",
        ]
        for row in batch.rows.values():
            task = book.tasks.get(row.key) or {}
            lines.append(f"| {row.key} | {task.get('role', row.kind)} | {task.get('pin', '')} | {row.seconds} | "
                         f"{row.takes} | {row.rate:g} | {row.busy_s / 60:.1f} |")
        lines.append("")
    state = "BLOCKED: nothing will be queued." if verdict.blocked else "Clear to queue once the person says yes."
    lines += [f"## {state}", ""]
    for title, level in (("Blocks", "block"), ("Warnings", "warn"), ("Notes", "note")):
        found = verdict.of_level(level)
        if not found:
            continue
        lines += [f"### {title} ({len(found)})", ""]
        for finding in found:
            lessons = f" ({', '.join(finding.lessons)})" if finding.lessons else ""
            reason = f" Reason given: {finding.reason}" if finding.reason else ""
            lines.append(f"- **{finding.rule}** {finding.key or 'film'}: {finding.message}{lessons}. "
                         f"Fix: {finding.hint}{reason}")
        lines.append("")
    open_items = verdict.open_review
    if open_items:
        lines += [f"### Questions for the judge or the person ({len(open_items)})", ""]
        for item in open_items:
            state_word = "unanswered" if item.awaiting else f"answered {item.answer}"
            lines.append(f"- {item.key} `{item.id}` ({state_word}): {item.question}")
        lines.append("")
    lines += ["### After the batch, for the cold reviewer", ""]
    lines += [f"- `{item['id']}`: {item['question']}" for item in after_batch_questions()]
    return "\n".join(lines) + "\n"


def _lines_of(book: Book, shot) -> str:
    keys = [key for key in shot.sings if key in book.lines]
    if not keys:
        return ""
    return sung_words(keys, book.lines)


def board_html(book: Book) -> str:
    """Gate 4: one card per shot with its first frame, window and lines. Paths are relative to the film folder."""
    esc = html.escape
    cards = []
    for index, shot in enumerate(book.shots, start=1):
        task = book.tasks.get(shot.key) or {}
        still = task.get("still") or shot.still_path
        on = task.get("shown_at") or ["?", "?"]
        span = (f"render {task.get('slice_start', '?')} s + {task.get('seconds', '?')} s; on screen {on[0]} to {on[1]}"
                  if task else "not planned")
        words = _lines_of(book, shot)
        what = words and f"&ldquo;{esc(words)}&rdquo;" or esc("; ".join(shot.beats) or shot.goal or "")
        cards.append(
            f'<figure class="shot"><img src="{esc(still)}" alt="first frame of {esc(shot.key)}" width="320" '
            f'height="176" loading="lazy"><figcaption><b>{index:02d} {esc(shot.key)}</b> '
            f'<span class="kind">{esc(task.get("role", shot.kind))}</span><br>{esc(span)}<br>{what}'
            f'</figcaption></figure>')
    title = esc(f"{book.film.get('name', 'Film')} board")
    style = ("body{font:14px/1.4 system-ui,sans-serif;margin:16px;background:#f4f1ea;color:#1d1b18}"
             ".grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:12px}"
             ".shot{margin:0;background:#fff;padding:8px;border:1px solid #d8d2c4}"
             ".shot img{width:100%;height:auto;display:block;background:#ccc}.kind{color:#7a6f5c}")
    return (f"<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" "
            f"content=\"width=device-width,initial-scale=1\"><title>{title}</title><style>{style}</style></head>"
            f"<body><h1>{title}</h1><p>Every shot's first frame, render window and lines. Open each still at full "
            f"size before saying yes.</p><div class=\"grid\">{''.join(cards)}</div></body></html>\n")


def write_reports(book: Book, verdict: Verdict, folder: Path) -> tuple[Path, Path]:
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    account = folder / "report.md"
    board = folder / "board.html"
    account.write_text(report_markdown(book, verdict), encoding="utf-8")
    board.write_text(board_html(book), encoding="utf-8")
    return account, board
