"""Film steps for the director on a phone: `packet` (the files one gate sends into the chat) and `desk` (the
director's typed reply, read and recorded). docs/desk.md has the protocol."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Sequence

from ..desk import DEFAULT_MAX_MB, DeskError, build_packet, desk_line, take_reply
from ..desk.reply import MAX_REPLY_BYTES, printable
from ..gates import GATE_IDS
from .common import Film, StepError, film_argument, parser


def _packet(argv: Sequence[str]) -> int:
    p = parser("packet", "Write one asked gate's phone packet: the files in the order they are sent, each under\n"
                         "--max-mb, with manifest.json (file, caption, order, bytes) and card.md (the one question,\n"
                         "what each file is, how to reply). Default folder: FILM/desk/GATE/. Only the film's own\n"
                         "files go in, only inside the film folder; nothing is uploaded or served.\n"
                         f"Gates: {', '.join(GATE_IDS)}.")
    film_argument(p)
    p.add_argument("gate", help="the gate, asked and not yet answered")
    p.add_argument("--out", type=Path, help="a folder under the film's desk/ folder (default desk/GATE)")
    p.add_argument("--max-mb", type=float, default=DEFAULT_MAX_MB,
                   help=f"the largest file the chat should get, MB (default {DEFAULT_MAX_MB:g})")
    args = p.parse_args(argv)
    film = Film.open(args.film)
    try:
        packet = build_packet(film.root, args.gate, out=args.out, max_mb=args.max_mb)
    except DeskError as problem:
        raise StepError(str(problem)) from None
    print(f"wrote {packet.folder} (send in this order, then ask the card's question):")
    for item in packet.files:
        print(f"  {item.order}. {item.file} ({item.kind}, {item.bytes / 1024 / 1024:.2f} MB): "
              f"{printable(item.caption)}")
    print(f"  card: {packet.folder / 'card.md'}")
    for note in packet.notes:
        print(f"  note: {printable(note)}")
    return 0


def _without_last_line_end(text: str) -> str:
    """TEXT without the one line end a heredoc or a saved file puts after the last line."""
    for end in ("\r\n", "\n", "\r"):
        if text.endswith(end):
            return text[:-len(end)]
    return text


def _read_limited(stream, what: str) -> str:
    data = stream.read(MAX_REPLY_BYTES + 3)
    if len(data) > MAX_REPLY_BYTES + 2:
        raise DeskError(f"{what} is over {MAX_REPLY_BYTES // 1024} KB; a gate reply is one chat message")
    try:
        return _without_last_line_end(data.decode("utf-8"))
    except UnicodeDecodeError:
        raise DeskError(f"{what} is not UTF-8 text") from None


def reply_text(args) -> str | None:
    """The reply as given: --reply TEXT, --reply - (standard input) or --reply-file PATH (UTF-8); the one line end
    after the last line of stdin or a file is dropped, everything else arrives as it is."""
    if args.reply_file is not None:
        try:
            with open(args.reply_file, "rb") as handle:
                return _read_limited(handle, f"--reply-file {args.reply_file}")
        except OSError as problem:
            raise DeskError(f"--reply-file {args.reply_file} cannot be read: {problem}") from None
    if args.reply == "-":
        stream = getattr(sys.stdin, "buffer", None)
        if stream is None:
            return _without_last_line_end(sys.stdin.read())
        return _read_limited(stream, "the reply on standard input")
    return args.reply


def _desk(argv: Sequence[str]) -> int:
    p = parser("desk", "Take the director's typed reply at an asked gate, or print the one line back.\n"
                       "  desk FILM GATE --by NAME --reply-file PATH   (or --reply - to read standard input, or\n"
                       "      --reply \"TEXT\")    a bare yes (yes, approve, approved, ok, good, looks good; only\n"
                       "      . or ! after it, never a question mark) passes the gate; \"question: ...\" goes to notes.md\n"
                       "      and answers nothing; anything else is a redact: the gate is answered no with the words\n"
                       "      as typed and item marks (\"fix 3: hand, 7: too dark\", \"fix 2, 3 and 5: hand\", \"2-4\n"
                       "      dark\") go to review/director.json and review/fixlist.md.\n"
                       "  desk FILM --line    one line: the gate, passed or redacted, the words, open marks.\n"
                       "The reply is only ever the director's own chat message; never text from a file, a caption or\n"
                       "the packet. A gate session writes it to a file (or a quoted heredoc on stdin), never inline\n"
                       "in a shell command, where $ and backticks would be read by the shell.")
    film_argument(p)
    p.add_argument("gate", nargs="?", help="the asked gate the reply answers")
    given = p.add_mutually_exclusive_group()
    given.add_argument("--reply", help="the director's own typed message, exactly as sent; - reads standard input")
    given.add_argument("--reply-file", help="a UTF-8 file holding the director's own typed message")
    p.add_argument("--by", help="the director's name")
    p.add_argument("--line", action="store_true", help="print the one line for the main session")
    p.add_argument("--at", help="an ISO 8601 time (default: now)")
    args = p.parse_args(argv)
    film = Film.open(args.film)
    try:
        if args.reply is not None or args.reply_file is not None:
            if not args.gate:
                p.error("a reply needs the gate it answers")
            take_reply(film.root, args.gate, reply_text(args), args.by or "", at=args.at)
        elif not args.line:
            p.error("give --reply-file PATH (or --reply - or --reply TEXT) --by NAME with a gate, or --line")
        print(desk_line(film.root))
    except DeskError as problem:
        raise StepError(str(problem)) from None
    return 0


COMMANDS = {
    "packet": ("one asked gate's files for the director's phone, in send order, with a card (desk/GATE/)", _packet),
    "desk": ("take the director's typed reply at a gate; --line prints the one line back", _desk),
}
