"""Synthetic code trees for the similarity tests. All of it is invented for the tests."""

import re
from pathlib import Path

PANTRY_PY = '''\
"""Keep track of jars on pantry shelves and print a tally for the cook."""

import argparse
import json
from pathlib import Path


SHELF_LIMIT = 24


class PantryShelf:
    """One shelf that holds labelled jars until it is full."""

    def __init__(self, shelf_label, jar_slots):
        self.shelf_label = shelf_label
        self.jar_slots = jar_slots
        self.jar_names = []

    def place_jar(self, jar_title):
        # A full shelf refuses the jar so the cook notices early.
        if len(self.jar_names) >= self.jar_slots:
            raise ValueError("shelf is full, move a jar to the cellar first")
        self.jar_names.append(jar_title)
        return len(self.jar_names)


def load_pantry(pantry_file):
    """Read the pantry inventory from a json file written by the restock step."""
    raw_pantry = json.loads(Path(pantry_file).read_text(encoding="utf-8"))
    shelf_rows = []
    for shelf_entry in raw_pantry["shelves"]:
        fresh_shelf = PantryShelf(shelf_entry["shelf_label"], shelf_entry["jar_slots"])
        for jar_title in shelf_entry["jar_names"]:
            fresh_shelf.place_jar(jar_title)
        shelf_rows.append(fresh_shelf)
    return shelf_rows


def tally_jars(shelf_rows):
    """Count the jars on every shelf and the spare slots left over."""
    jar_total = 0
    spare_total = 0
    for fresh_shelf in shelf_rows:
        jar_total += len(fresh_shelf.jar_names)
        spare_total += fresh_shelf.jar_slots - len(fresh_shelf.jar_names)
    # Spare slots over the limit mean a shelf was mislabelled.
    if spare_total > SHELF_LIMIT:
        print("warning: more spare slots than the pantry should have")
    tally_card = {"jar_total": jar_total, "spare_total": spare_total}
    return tally_card


def restock_shelf(fresh_shelf, jar_titles):
    """Place each new jar on the shelf, stopping quietly when it is full."""
    placed_count = 0
    for jar_title in jar_titles:
        if len(fresh_shelf.jar_names) >= fresh_shelf.jar_slots:
            break
        fresh_shelf.place_jar(jar_title)
        placed_count += 1
    return placed_count


def main(argv=None):
    parser = argparse.ArgumentParser(description="Tally the jars in a pantry file.")
    sub = parser.add_subparsers(dest="verb", required=True)
    stock_cmd = sub.add_parser("stock", help="place jars on a shelf")
    stock_cmd.add_argument("pantry_file")
    tally_cmd = sub.add_parser("tally", help="print the jar tally")
    tally_cmd.add_argument("pantry_file")
    tally_cmd.add_argument("--shelf-filter", default=None)
    args = parser.parse_args(argv)
    shelf_rows = load_pantry(args.pantry_file)
    tally_card = tally_jars(shelf_rows)
    print(json.dumps(tally_card))
    return 0
'''

PANTRY_JSON = '{"shelves": [{"shelf_label": "top", "jar_slots": 3, "jar_names": ["plum jam"]}]}\n'

PANTRY_README = """\
# Pantry

Keep track of jars on pantry shelves and print a tally for the cook.

A full shelf refuses the jar so the cook notices early. Spare slots over the limit
mean a shelf was mislabelled.
"""

RENAMES = {
    "PantryShelf": "Rack",
    "SHELF_LIMIT": "MAX_FREE",
    "shelf_label": "tag",
    "jar_slots": "room",
    "jar_names": "held",
    "place_jar": "put",
    "jar_title": "thing",
    "load_pantry": "read_store",
    "pantry_file": "src_file",
    "raw_pantry": "blob",
    "shelf_rows": "racks",
    "shelf_entry": "row",
    "fresh_shelf": "rack",
    "tally_jars": "sum_up",
    "jar_total": "held_n",
    "spare_total": "free_n",
    "tally_card": "summary",
    "restock_shelf": "refill",
    "jar_titles": "things",
    "placed_count": "put_n",
    "stock_cmd": "cmd_a",
    "tally_cmd": "cmd_b",
    "sub": "group",
}

KITE_PY = '''\
"""Log the wind on a beach and say when a kite can fly."""

import math
import sys

GUST_FACTOR = 1.3


def wind_reading(speed_knots, bearing_deg):
    """Turn one anemometer sample into east and north parts."""
    radians_now = math.radians(bearing_deg)
    return speed_knots * math.sin(radians_now), speed_knots * math.cos(radians_now)


def can_launch(samples_knots):
    # Too calm or too gusty both keep the kite on the sand.
    if not samples_knots:
        return False
    calmest = min(samples_knots)
    wildest = max(samples_knots)
    return calmest >= 6 and wildest <= calmest * GUST_FACTOR + 8


if __name__ == "__main__":
    print(can_launch([float(v) for v in sys.argv[1:]]))
'''

KITE_JSON = '{"beach": "north cove", "wind_speed": [7.5, 9.0]}\n'

KITE_README = "# Kite log\n\nA beach notebook that decides if the wind will carry a kite today.\n"


def _rename(text):
    for old, new in sorted(RENAMES.items(), key=lambda kv: -len(kv[0])):
        text = re.sub(rf"\b{old}\b", new, text)
    return text


def write_tree(root: Path, kind: str) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    if kind == "old" or kind == "copy":
        files = {"pantry/core.py": PANTRY_PY, "pantry/sample.json": PANTRY_JSON, "README.md": PANTRY_README}
    elif kind == "renamed":
        files = {"store/main.py": _rename(PANTRY_PY), "README.md": "# Store\n\nNothing shared here.\n"}
    elif kind == "unrelated":
        files = {"kite/log.py": KITE_PY, "kite/beach.json": KITE_JSON, "README.md": KITE_README}
    else:
        raise ValueError(kind)
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return root
