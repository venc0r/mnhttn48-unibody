#!/usr/bin/env python3
"""
Schematic generator for the mnhTTn48 unibody.

    tools/gen_schematic.py

Writes board/mnhttn48-unibody.kicad_sch (root), board/switch.kicad_sch (one sub-sheet per key,
from the mnhTTn48 template) and board/mnhttn48-unibody.kicad_pro (from the mnhTTn48 project).

Electrical matrix, ZMK col2row with the register as the driven side:
  COL_0..COL_7  74HC595 outputs QA..QH, COL_c = physical key row c on the left half (c 0..3,
                top to bottom) and the right half (c 4..7). The thumb keys use COL_0/1 (left)
                and COL_4/5 (right), outer thumb first.
  ROW_0..ROW_5  XIAO inputs, ROW_i = finger column i (0 pinky .. 4 inner), ROW_5 = thumbs.
                ROW_i sits on D(5-i) (ROW_5 on D0, ROW_0 on D5) for the board routing.
Current flows register -> switch -> diode -> XIAO input, the switch sheet is unchanged from the
mnhTTn48 (COL on the switch, ROW on the diode cathode).

All connections are local labels on 2.54 mm stubs. UUIDs are uuid5 of the element name, so a
regeneration changes nothing that did not change. Switch references stay SW_L_4_n / D_L_4_n so
board/layout.json and the footprints keep matching.
"""

import json
import re
import uuid
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SYMBOLS_DIR = REPO / "tools" / "sch_symbols"
KEYS_PATH = REPO / "tools" / "keys-mnhttn48.json"
LAYOUT_PATH = REPO / "board" / "layout.json"
BOARD_DIR = REPO / "board"
PROJECT = "mnhttn48-unibody"
NAMESPACE = uuid.UUID("5d1f0c2e-6b7a-4f3e-9c1d-2a8b4e6f0a11")
FONT = "(effects (font (size 1.27 1.27)))"
STUB = 2.54
SHEET_SIZE = 12.7
GRID_X0, GRID_Y0, GRID_DX, GRID_DY, HALF_GAP = 25.4, 25.4, 27.94, 27.94, 12.7


def uid(name):
    return str(uuid.uuid5(NAMESPACE, name))


ROOT_UUID = uid("root")

# ---------------------------------------------------------------- matrix assignment


def finger_columns(keys):
    finger_keys = sorted((key for key in keys if key["rot"] == 0), key=lambda key: key["x"])
    columns = []
    for key in finger_keys:
        if columns and abs(columns[-1][0]["x"] - key["x"]) < 1.0:
            columns[-1].append(key)
        else:
            columns.append([key])
    return columns


def matrix_positions(keys, dropped):
    """ref -> (col, row) in the electrical matrix for both halves."""
    positions = {}
    for side, half in enumerate(("left", "right")):
        half_keys = [key for key in keys if key["half"] == half and key["ref"] not in dropped]
        columns = finger_columns(half_keys)
        if half == "right":
            columns.reverse()
        for row_input, column in enumerate(columns):
            for key_row, key in enumerate(sorted(column, key=lambda key: key["y"])):
                positions[key["ref"]] = (4 * side + key_row, row_input)
        thumbs = sorted((key for key in half_keys if key["rot"] != 0), key=lambda key: key["x"], reverse=half == "right")
        for index, key in enumerate(thumbs):
            positions[key["ref"]] = (4 * side + index, 5)
    return positions


# ---------------------------------------------------------------- symbol library handling


def load_symbol(lib_id):
    path = SYMBOLS_DIR / (lib_id.replace(":", "_") + ".kicad_sym")
    return path.read_text().rstrip("\n")


def symbol_pins(text):
    """[(number, x, y, angle)] in library coordinates (y up)."""
    pins = []
    for match in re.finditer(r"\(pin\s+\w+\s+\w+\s*\n\s*\(at\s+([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)\)", text):
        number = re.search(r'\(number\s+"([^"]+)"', text[match.end():]).group(1)
        pins.append((number, float(match.group(1)), float(match.group(2)), float(match.group(3))))
    return pins


def outward(angle):
    """Unit vector pointing away from the symbol body at a pin, in schematic coordinates (y down)."""
    return {0: (-1, 0), 180: (1, 0), 90: (0, 1), 270: (0, -1)}[int(angle) % 360]


def label_orientation(direction):
    return {(-1, 0): (180, "right bottom"), (1, 0): (0, "left bottom"), (0, -1): (90, "left bottom"), (0, 1): (270, "right bottom")}[direction]


# ---------------------------------------------------------------- s-expression writers


def fmt(value):
    return f"{value:.4f}".rstrip("0").rstrip(".") if isinstance(value, float) else str(value)


def wire(name, x1, y1, x2, y2):
    return (f"\t(wire\n\t\t(pts\n\t\t\t(xy {fmt(x1)} {fmt(y1)}) (xy {fmt(x2)} {fmt(y2)})\n\t\t)\n"
            f"\t\t(stroke\n\t\t\t(width 0)\n\t\t\t(type default)\n\t\t)\n\t\t(uuid \"{uid(name)}\")\n\t)")


def label(name, text, x, y, angle, justify):
    return (f"\t(label \"{text}\"\n\t\t(at {fmt(x)} {fmt(y)} {angle})\n"
            f"\t\t(effects\n\t\t\t(font\n\t\t\t\t(size 1.27 1.27)\n\t\t\t)\n\t\t\t(justify {justify})\n\t\t)\n"
            f"\t\t(uuid \"{uid(name)}\")\n\t)")


def no_connect(name, x, y):
    return f"\t(no_connect\n\t\t(at {fmt(x)} {fmt(y)})\n\t\t(uuid \"{uid(name)}\")\n\t)"


def stub_with_label(name, x, y, direction, net):
    """Short wire from a pin end outward, with a net label on its far end."""
    x2, y2 = x + direction[0] * STUB, y + direction[1] * STUB
    angle, justify = label_orientation(direction)
    return [wire(name + ":wire", x, y, x2, y2), label(name + ":label", net, x2, y2, angle, justify)]


def prop(name, value, x, y, hide=False, justify=None):
    effects = "(effects (font (size 1.27 1.27))" + (f" (justify {justify})" if justify else "") + (" (hide yes)" if hide else "") + ")"
    return f"\t\t(property \"{name}\" \"{value}\"\n\t\t\t(at {fmt(x)} {fmt(y)} 0)\n\t\t\t{effects}\n\t\t)"


def symbol_instance(ref, lib_id, value, footprint, x, y, pins):
    lines = [
        "\t(symbol",
        f"\t\t(lib_id \"{lib_id}\")",
        f"\t\t(at {fmt(x)} {fmt(y)} 0)",
        "\t\t(unit 1)",
        "\t\t(exclude_from_sim no)",
        "\t\t(in_bom yes)",
        "\t\t(on_board yes)",
        "\t\t(dnp no)",
        f"\t\t(uuid \"{uid('symbol:' + ref)}\")",
        prop("Reference", ref, x + 2.54, y - 25.4, justify="left"),
        prop("Value", value, x + 2.54, y - 22.86, justify="left"),
        prop("Footprint", footprint, x, y, hide=True),
        prop("Datasheet", "", x, y, hide=True),
        prop("Description", "", x, y, hide=True),
    ]
    for number, *_ in pins:
        lines.append(f"\t\t(pin \"{number}\"\n\t\t\t(uuid \"{uid(f'pin:{ref}:{number}')}\")\n\t\t)")
    lines.append(f"\t\t(instances\n\t\t\t(project \"{PROJECT}\"\n\t\t\t\t(path \"/{ROOT_UUID}\"\n"
                 f"\t\t\t\t\t(reference \"{ref}\")\n\t\t\t\t\t(unit 1)\n\t\t\t\t)\n\t\t\t)\n\t\t)")
    lines.append("\t)")
    return "\n".join(lines)


def place_symbol(ref, lib_id, value, footprint, x, y, connections):
    """Symbol plus a stub and label (or no-connect) on every pin. connections: pin number -> net or None."""
    text = load_symbol(lib_id)
    pins = symbol_pins(text)
    parts = [symbol_instance(ref, lib_id, value, footprint, x, y, pins)]
    for number, px, py, angle in pins:
        end_x, end_y = x + px, y - py
        net = connections.get(number, "nc")
        if net is None or net == "nc":
            parts.append(no_connect(f"nc:{ref}:{number}", end_x, end_y))
        else:
            parts.extend(stub_with_label(f"{ref}:{number}", end_x, end_y, outward(angle), net))
    return parts


def sheet_instance(ref, sheet_name, page, x, y, col_net, row_net):
    sheet_uuid = uid(f"sheet:{ref}")
    col_x, col_y = x + SHEET_SIZE, y + SHEET_SIZE / 2
    row_x, row_y = x + 5.08, y + SHEET_SIZE
    parts = [
        "\t(sheet",
        f"\t\t(at {fmt(x)} {fmt(y)})",
        f"\t\t(size {SHEET_SIZE} {SHEET_SIZE})",
        "\t\t(stroke\n\t\t\t(width 0.1524)\n\t\t\t(type solid)\n\t\t)",
        "\t\t(fill\n\t\t\t(color 0 0 0 0.0000)\n\t\t)",
        f"\t\t(uuid \"{sheet_uuid}\")",
        f"\t\t(property \"Sheetname\" \"{sheet_name}\"\n\t\t\t(at {fmt(x)} {fmt(y - 0.7116)} 0)\n"
        f"\t\t\t(effects (font (size 1.27 1.27)) (justify left bottom))\n\t\t)",
        f"\t\t(property \"Sheetfile\" \"switch.kicad_sch\"\n\t\t\t(at {fmt(x)} {fmt(y + SHEET_SIZE + 0.5846)} 0)\n"
        f"\t\t\t(effects (font (size 1.27 1.27)) (justify left top) (hide yes))\n\t\t)",
        f"\t\t(pin \"COL\" input\n\t\t\t(at {fmt(col_x)} {fmt(col_y)} 0)\n\t\t\t(effects (font (size 1.27 1.27)) (justify right))\n"
        f"\t\t\t(uuid \"{uid(f'sheetpin:{ref}:COL')}\")\n\t\t)",
        f"\t\t(pin \"ROW\" input\n\t\t\t(at {fmt(row_x)} {fmt(row_y)} 270)\n\t\t\t(effects (font (size 1.27 1.27)) (justify left))\n"
        f"\t\t\t(uuid \"{uid(f'sheetpin:{ref}:ROW')}\")\n\t\t)",
        f"\t\t(instances\n\t\t\t(project \"{PROJECT}\"\n\t\t\t\t(path \"/{ROOT_UUID}\"\n\t\t\t\t\t(page \"{page}\")\n\t\t\t\t)\n\t\t\t)\n\t\t)",
        "\t)",
    ]
    parts = ["\n".join(parts)]
    parts.extend(stub_with_label(f"{ref}:COL", col_x, col_y, (1, 0), col_net))
    parts.extend(stub_with_label(f"{ref}:ROW", row_x, row_y, (0, 1), row_net))
    return parts, sheet_uuid


# ---------------------------------------------------------------- the circuit

# ROW_5 on D0 .. ROW_0 on D5: lets the top strip buses and the drops into the XIAO nest without crossing
XIAO_CONNECTIONS = {
    "1": "ROW_0", "2": "ROW_1", "3": "ROW_2", "4": "ROW_3", "5": "ROW_4", "6": "ROW_5",
    "9": "SCK", "10": "CS", "11": "MOSI", "12": "3V3", "13": "GND", "17": "RST", "18": "GND",
    "19": "+BATT", "20": "GND",
}
SHIFT_REGISTER_CONNECTIONS = {
    "15": "COL_0", "1": "COL_1", "2": "COL_2", "3": "COL_3", "4": "COL_4", "5": "COL_5", "6": "COL_6", "7": "COL_7",
    "14": "MOSI", "11": "SCK", "12": "CS", "10": "3V3", "13": "GND", "16": "3V3", "8": "GND",
}


def root_schematic(keys, positions):
    lib_ids = ["mcu:xiao-ble", "74xx:74HC595", "Device:C", "Switch:SW_Push", "Switch:SW_SPDT", "Mechanical:MountingHole_Pad"]
    parts = [
        "(kicad_sch",
        "\t(version 20231120)",
        "\t(generator \"eeschema\")",
        "\t(generator_version \"8.0\")",
        f"\t(uuid \"{ROOT_UUID}\")",
        "\t(paper \"A3\")",
        "\t(lib_symbols",
        *[load_symbol(lib_id) for lib_id in lib_ids],
        "\t)",
    ]
    sheet_uuids = {}
    page = 2
    for ref in sorted(positions, key=lambda ref: positions[ref]):
        col, row = positions[ref]
        x = GRID_X0 + col * GRID_DX + (HALF_GAP if col >= 4 else 0)
        y = GRID_Y0 + row * GRID_DY
        sheet_parts, sheet_uuid = sheet_instance(ref, "Key " + ref.replace("SW_L_4_", ""), page, x, y, f"COL_{col}", f"ROW_{row}")
        parts.extend(sheet_parts)
        sheet_uuids[ref] = sheet_uuid
        page += 1

    parts.extend(place_symbol("U1", "mcu:xiao-ble", "xiao-ble", "mnhttn:xiao-ble-smd-cutout", 330.2, 63.5, XIAO_CONNECTIONS))
    parts.extend(place_symbol("U2", "74xx:74HC595", "74HC595", "mnhttn:SOIC-16_3.9x9.9mm_P1.27mm", 330.2, 139.7, SHIFT_REGISTER_CONNECTIONS))
    parts.extend(place_symbol("C1", "Device:C", "100n", "mnhttn:C_0603_1608Metric", 368.3, 139.7, {"1": "3V3", "2": "GND"}))
    parts.extend(place_symbol("SW1", "Switch:SW_Push", "RESET", "mnhttn:PushSwitch", 304.8, 193.04, {"1": "GND", "2": "RST"}))
    parts.extend(place_symbol("SW2", "Switch:SW_SPDT", "POWER", "mnhttn:MSK12C02", 335.28, 193.04, {"2": "BAT_SW", "3": "+BATT"}))
    parts.extend(place_symbol("BAT+1", "Mechanical:MountingHole_Pad", "BAT+", "mnhttn:BatteryPad", 365.76, 193.04, {"1": "BAT_SW"}))
    parts.extend(place_symbol("BAT-1", "Mechanical:MountingHole_Pad", "BAT-", "mnhttn:BatteryPad", 378.46, 193.04, {"1": "GND"}))

    parts.append("\t(sheet_instances\n\t\t(path \"/\"\n\t\t\t(page \"1\")\n\t\t)\n\t)")
    parts.append(")")
    return "\n".join(parts) + "\n", sheet_uuids


def switch_sheet(sheet_uuids):
    template = (SYMBOLS_DIR / "switch_sheet.template.kicad_sch").read_text()

    def instances(prefix):
        paths = "".join(
            f"\t\t\t\t(path \"/{ROOT_UUID}/{sheet_uuid}\"\n\t\t\t\t\t(reference \"{ref.replace('SW_L_4_', prefix)}\")\n\t\t\t\t\t(unit 1)\n\t\t\t\t)\n"
            for ref, sheet_uuid in sorted(sheet_uuids.items())
        )
        return f"\t\t(instances\n\t\t\t(project \"{PROJECT}\"\n{paths}\t\t\t)\n\t\t)"

    return (template.replace("@@SHEET_UUID@@", uid("switch-sheet-file"))
            .replace("\t\t@@INSTANCES_D@@", instances("D_L_4_"))
            .replace("\t\t@@INSTANCES_SW@@", instances("SW_L_4_")))


def project_file():
    project = json.loads((SYMBOLS_DIR / "project.template.kicad_pro").read_text())
    project["meta"]["filename"] = f"{PROJECT}.kicad_pro"
    project.pop("sheets", None)
    project["boards"] = []
    return json.dumps(project, indent=2) + "\n"


def main():
    keys = json.loads(KEYS_PATH.read_text())
    dropped = set(json.loads(LAYOUT_PATH.read_text())["dropped"])
    positions = matrix_positions(keys, dropped)

    root, sheet_uuids = root_schematic(keys, positions)
    (BOARD_DIR / f"{PROJECT}.kicad_sch").write_text(root)
    (BOARD_DIR / "switch.kicad_sch").write_text(switch_sheet(sheet_uuids))
    (BOARD_DIR / f"{PROJECT}.kicad_pro").write_text(project_file())

    (REPO / "tools" / "matrix.json").write_text(json.dumps(
        {ref: {"col": col, "row": row} for ref, (col, row) in sorted(positions.items())}, indent=2) + "\n")
    print(f"{len(positions)} keys -> {BOARD_DIR / (PROJECT + '.kicad_sch')}")
    for col in range(8):
        members = sorted(ref.replace("SW_L_4_", "") for ref, (c, _) in positions.items() if c == col)
        print(f"  COL_{col}: {' '.join(members)}")


if __name__ == "__main__":
    main()
