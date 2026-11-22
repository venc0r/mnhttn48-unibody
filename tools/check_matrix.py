#!/usr/bin/env python3
"""
Checks the key matrix in the schematic netlist against tools/matrix.json.

    tools/check_matrix.py [matrix.json]     # exit code 1 on any mismatch

Follows every key through the netlist: switch pad 2 must sit on a COL net that reaches a 74HC595
output (QA..QH = COL 0..7), switch pad 1 on its diode's anode, the diode's cathode on a ROW net that
reaches XIAO pin D0..D5 (ROW 0..5). The (col, row) found that way has to match tools/matrix.json,
and no two keys may share one. Prints the matrix as seen from the firmware: COL driven by the
shift register, ROW read by the XIAO, diodes pointing from COL to ROW (ZMK col2row).
"""

import json
import subprocess
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCHEMATIC = REPO / "board" / "mnhttn48-unibody.kicad_sch"
NETLIST = REPO / "board" / "mnhttn48-unibody.net.xml"
MATRIX = REPO / "tools" / "matrix.json"
REGISTER, CONTROLLER = "U2", "U1"
XIAO_D_PINS = {str(pin): pin - 1 for pin in range(1, 7)}   # footprint pads 1..6 are D0..D5


def load_netlist():
    subprocess.run(["kicad-cli", "sch", "export", "netlist", "--format", "kicadxml", "--output", str(NETLIST),
                    str(SCHEMATIC)], check=True, capture_output=True)
    pins = {}                     # (ref, pin) -> (net, pinfunction)
    members = defaultdict(list)   # net -> [(ref, pin, pinfunction)]
    for net in ET.parse(NETLIST).getroot().find("nets"):
        for node in net.findall("node"):
            entry = (node.get("ref"), node.get("pin"), node.get("pinfunction") or "")
            pins[entry[:2]] = (net.get("name"), entry[2])
            members[net.get("name")].append(entry)
    return pins, members


def register_column(members, net):
    """COL index of a net from the 74HC595 output it reaches (QA = 0 .. QH = 7), None if none."""
    for ref, _, function in members[net]:
        if ref == REGISTER and function[:2] in {f"Q{letter}" for letter in "ABCDEFGH"} and function[2] == "_":
            return "ABCDEFGH".index(function[1])
    return None


def controller_row(members, net):
    """ROW index of a net from the XIAO pad it reaches (D0..D5), None if none."""
    for ref, pin, _ in members[net]:
        if ref == CONTROLLER and pin in XIAO_D_PINS:
            return XIAO_D_PINS[pin]
    return None


def check(matrix, pins, members):
    errors, found = [], {}
    for sw, expected in sorted(matrix.items()):
        diode = sw.replace("SW_L_4_", "D_L_4_")
        col_net, _ = pins[(sw, "2")]
        anode_net, anode_function = pins[(diode, "2")]
        cathode_net, cathode_function = pins[(diode, "1")]
        if not anode_function.startswith("A") or not cathode_function.startswith("K"):
            errors.append(f"{diode}: pin 2/1 are {anode_function}/{cathode_function}, expected anode/cathode")
        if pins[(sw, "1")][0] != anode_net:
            errors.append(f"{sw}: pad 1 on {pins[(sw, '1')][0]}, not on {diode}'s anode")
        col, row = register_column(members, col_net), controller_row(members, cathode_net)
        if col is None or row is None:
            errors.append(f"{sw}: COL net {col_net} or ROW net {cathode_net} reaches no register output / XIAO pin")
            continue
        if (col, row) != (expected["col"], expected["row"]):
            errors.append(f"{sw}: wired as col {col} row {row}, matrix.json says col {expected['col']} row {expected['row']}")
        found[sw] = (col, row)
    by_position = defaultdict(list)
    for sw, position in found.items():
        by_position[position].append(sw)
    errors += [f"col {c} row {r} used by {', '.join(refs)}" for (c, r), refs in by_position.items() if len(refs) > 1]
    return errors, found


def print_grid(found):
    position = {pos: sw.replace("SW_L_4_", "") for sw, pos in found.items()}
    print("        " + "".join(f"COL_{c:<3}" for c in range(8)))
    for row in range(6):
        cells = "".join(f"{position.get((col, row), '.'):<7}" for col in range(8))
        print(f"ROW_{row}   {cells}")


def main():
    matrix = json.loads(Path(sys.argv[1] if len(sys.argv) > 1 else MATRIX).read_text())
    pins, members = load_netlist()
    errors, found = check(matrix, pins, members)
    print_grid(found)
    print(f"{len(found)} keys, {len(set(found.values()))} matrix positions, {len(errors)} errors")
    for error in errors:
        print(f"  {error}")
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
