#!/usr/bin/env python3
"""
Extract the switch positions of the mnhTTn48 board into keys-mnhttn48.json.

    tools/extract_keys.py path/to/mnhttn.kicad_pcb

Coordinates are KiCad board coordinates (mm, y down), rotation is the KiCad footprint
rotation (degrees, counter-clockwise positive). Keys left of the panel bridge are "left".
"""

import json
import re
import sys
from pathlib import Path

SWITCH_FOOTPRINT = '(footprint "mnhttn:Cherry_MX_ULP_Human"'
PANEL_BRIDGE_X = 150.0

AT_PATTERN = re.compile(r"\(at\s+([-\d.]+)\s+([-\d.]+)(?:\s+([-\d.]+))?\)")
REFERENCE_PATTERN = re.compile(r'\(property "Reference" "([^"]+)"')


def footprint_blocks(board_text):
    start = board_text.find(SWITCH_FOOTPRINT)
    while start != -1:
        next_footprint = board_text.find("\n\t(footprint ", start + 1)
        end = len(board_text) if next_footprint == -1 else next_footprint
        yield board_text[start:end]
        start = board_text.find(SWITCH_FOOTPRINT, end)


def parse_switch(block):
    at = AT_PATTERN.search(block)
    reference = REFERENCE_PATTERN.search(block)
    x, y = float(at.group(1)), float(at.group(2))
    rotation = float(at.group(3)) if at.group(3) else 0.0
    return {
        "ref": reference.group(1),
        "x": x,
        "y": y,
        "rot": rotation,
        "half": "left" if x < PANEL_BRIDGE_X else "right",
    }


def main():
    board_path = Path(sys.argv[1])
    keys = [parse_switch(block) for block in footprint_blocks(board_path.read_text())]
    keys.sort(key=lambda key: (key["half"], key["x"], key["y"]))
    out_path = Path(__file__).parent / "keys-mnhttn48.json"
    out_path.write_text(json.dumps(keys, indent=2) + "\n")
    left = sum(1 for key in keys if key["half"] == "left")
    print(f"{len(keys)} keys ({left} left, {len(keys) - left} right) -> {out_path}")


if __name__ == "__main__":
    main()
