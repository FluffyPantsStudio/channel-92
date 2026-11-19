"""Take a song's lyric from the site's catalog (src/data/songs.ts) and write it as a lyric file.

    python tools/lyric_from_site.py SONGS_TS SLUG OUT.txt

The catalog holds the lyric as published, one string with \\n line breaks and blank lines between verses. That is a
starting point only: `time` needs the lyric as SUNG (every repeat written out, backing parts in parentheses), so
check it against the vocal stem before timing. A header comment says so in the file.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ENTRY = re.compile(r'slug:\s*"(?P<slug>[^"]+)"(?P<body>.*?)(?=\n  \{\n\s*slug:|\n\];)', re.S)
LYRICS = re.compile(r'\blyrics:\s*(?P<text>"(?:[^"\\]|\\.)*")')


def lyric_of(provenance: str, slug: str) -> str:
    """The lyric string of the catalog entry SLUG, decoded."""
    for entry in ENTRY.finditer(provenance):
        if entry.group("slug") == slug:
            found = LYRICS.search(entry.group("body"))
            if not found:
                raise ValueError(f"{slug} has no lyrics field")
            return json.loads(found.group("text"))
    raise ValueError(f"no song with slug {slug!r} in the catalog")


def lyric_file(text: str, slug: str) -> str:
    head = (f"# {slug}: the lyric as published in the site catalog, not yet checked against the sung take.\n"
            "# Write out every repeat as sung, add [Section] lines, put backing parts in (parentheses).\n")
    return head + text.strip() + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("songs_ts", type=Path)
    parser.add_argument("slug")
    parser.add_argument("out", type=Path)
    args = parser.parse_args(argv)
    text = lyric_of(args.songs_ts.read_text(encoding="utf-8"), args.slug)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(lyric_file(text, args.slug), encoding="utf-8", newline="\n")
    print(f"wrote {args.out}: {len([line for line in text.splitlines() if line.strip()])} lines")
    return 0


if __name__ == "__main__":
    sys.exit(main())
