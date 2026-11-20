"""The director's desk: gate packets for a phone, and the director's typed replies read and recorded.

The director decides from the Claude app on a phone while the session runs on this machine. `packet` prepares the
files the gate session sends into that chat (in order, each under a size cap, with a short card); `desk` reads the
director's typed reply and records it at the gate, with any item marks for the main session. Nothing is uploaded or
served from here (docs/desk.md).
"""

from .ledger import DIRECTOR, FIXLIST, VIA, desk_line, mark_lines, open_marks, read_director
from .packet import DEFAULT_MAX_MB, Packet, build_packet, card_text
from .pictures import tile_boxes, timeline_strip
from .reply import YES, DeskError, Mark, Reply, parse_reply, read_marks
from .sink import PacketFile
from .take import take_reply

__all__ = ["DEFAULT_MAX_MB", "DIRECTOR", "FIXLIST", "VIA", "YES", "DeskError", "Mark", "Packet", "PacketFile",
           "Reply", "build_packet", "card_text", "desk_line", "mark_lines", "open_marks", "parse_reply",
           "read_director", "read_marks", "take_reply", "tile_boxes", "timeline_strip"]
