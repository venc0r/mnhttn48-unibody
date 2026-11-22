#!/usr/bin/env python3
"""
Unibody layout generator.

    tools/layout.py [--splay 20] [--gap auto|mm] [--column-splay 11,-7,-4] [--thumb-shift 8,1]
                    [--notebook mbp14] [--drop SW_L_4_26,SW_L_4_45,SW_L_4_31,SW_L_4_46] [--y-offset 0]

Reads tools/keys-mnhttn48.json (from extract_keys.py), drops the keys in --drop, fans the finger
columns of each half like ergogen does for the re-gret, moves the thumb keys by --thumb-shift,
rotates each half inward by the splay angle around its inner top corner, places the two corners
`gap` mm apart (auto: the widest gap without fit problems, 0.5 mm steps), centres the result in
the usable envelope of the notebook from tools/notebooks.json and writes
  docs/images/layout.svg   1:1 drawing for the paper fit test (mm units) with the notebook keep-outs
  docs/images/layout.pdf   the same as A4 PDF to print at 100 % (tools/svg_to_pdf.py)
  board/layout.json        key centres and rotations for placing footprints on the board
Output coordinates are board coordinates (mm, y down) with the origin at the top left corner of
the keyboard well, rotations follow the KiCad footprint convention (degrees, counter-clockwise
positive). Key cells (18 x 17 mm) outside the well or inside a keep-out are reported.

Column splay follows ergogen: the values are per column from pinky to inner, each relative to
the previous column, so 11,-7,-4 ends up as pinky 11 deg, ring 4 deg, middle and inner 0 deg.
Column i is rotated by the splay of every column up to i, in order, each around the flat
(unsplayed) pivot of its column: the bottom key centre for the first column, the bottom outer
corner of the bottom key for the others (re-gret's origin [-kx/2, -ky/2]). The thumb keys move
with the inner column.
"""

import argparse
import json
import math
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
KEYS_PATH = REPO / "tools" / "keys-mnhttn48.json"
NOTEBOOKS_PATH = REPO / "tools" / "notebooks.json"
SVG_PATH = REPO / "docs" / "images" / "layout.svg"
PDF_PATH = REPO / "docs" / "images" / "layout.pdf"
JSON_PATH = REPO / "board" / "layout.json"

KEY_PITCH_X = 18.0
KEY_PITCH_Y = 17.0
SWITCH_W = 13.6
SWITCH_H = 13.08
# Inner top corner of a half, relative to the inner column's top key centre.
CORNER_DX = KEY_PITCH_X / 2
CORNER_DY = KEY_PITCH_Y / 2
DEFAULT_COLUMN_SPLAY = "11,-7,-4"
# Extra inner keys and the innermost thumb key of each half.
DEFAULT_DROP = "SW_L_4_26,SW_L_4_45,SW_L_4_31,SW_L_4_46"
SVG_BORDER = 8.0
A4_LANDSCAPE = (297.0, 210.0)


def rotate(x, y, degrees):
    """Rotate a vector. With y pointing down this is a visually clockwise turn for positive degrees."""
    radians = math.radians(degrees)
    return (
        x * math.cos(radians) - y * math.sin(radians),
        x * math.sin(radians) + y * math.cos(radians),
    )


def rotate_key_ccw(key, pivot, degrees):
    """Turn a key visually counter-clockwise around a pivot, ergogen's positive splay direction."""
    dx, dy = rotate(key["x"] - pivot[0], key["y"] - pivot[1], -degrees)
    return {**key, "x": pivot[0] + dx, "y": pivot[1] + dy, "rot": key["rot"] + degrees}


def mirror_x(key):
    return {**key, "x": -key["x"], "rot": -key["rot"]}


def finger_columns(keys):
    """Columns of unrotated keys from pinky (lowest x) to inner."""
    finger_keys = sorted((key for key in keys if key["rot"] == 0), key=lambda key: key["x"])
    columns = []
    for key in finger_keys:
        if columns and abs(columns[-1][0]["x"] - key["x"]) < 1.0:
            columns[-1].append(key)
        else:
            columns.append([key])
    return columns


def column_pivot(column, is_first):
    bottom_key = max(column, key=lambda key: key["y"])
    if is_first:
        return bottom_key["x"], bottom_key["y"]
    return bottom_key["x"] - KEY_PITCH_X / 2, bottom_key["y"] + KEY_PITCH_Y / 2


def fan_columns(keys, column_splay, thumb_shift):
    """Apply ergogen column splay to a left-handed half. Thumb keys follow the inner finger column, plus thumb_shift (inward, down)."""
    columns = finger_columns(keys)
    splays = column_splay + [0.0] * (len(columns) - len(column_splay))
    rotations = []
    fanned = []
    for index, column in enumerate(columns):
        if splays[index]:
            rotations.append((column_pivot(column, index == 0), splays[index]))
        for key in column:
            for pivot, degrees in rotations:
                key = rotate_key_ccw(key, pivot, degrees)
            fanned.append(key)

    inner_before = max(columns[-1], key=lambda key: key["y"])
    inner_after = next(key for key in fanned if key["ref"] == inner_before["ref"])
    shift_x, shift_y = inner_after["x"] - inner_before["x"], inner_after["y"] - inner_before["y"]
    for key in keys:
        if key["rot"] != 0:
            fanned.append({**key, "x": key["x"] + shift_x + thumb_shift[0], "y": key["y"] + shift_y + thumb_shift[1]})
    return fanned


def inner_top_corner(keys):
    """Corner of the key grid beside the top key of the innermost column of a left-handed half."""
    inner_column = finger_columns(keys)[-1]
    top_key = min(inner_column, key=lambda key: key["y"])
    return top_key["x"] + CORNER_DX, top_key["y"] - CORNER_DY


def place_half(keys, half, splay, gap, column_splay, thumb_shift):
    """Fan the columns, rotate the half inward around its inner top corner and park that corner beside the centre line."""
    left_handed = keys if half == "left" else [mirror_x(key) for key in keys]
    corner_x, corner_y = inner_top_corner(left_handed)
    fanned = fan_columns(left_handed, column_splay, thumb_shift)
    placed = []
    for key in fanned:
        dx, dy = rotate(key["x"] - corner_x, key["y"] - corner_y, splay)
        placed.append({"ref": key["ref"], "half": half, "x": -gap / 2 + dx, "y": dy, "rot": key["rot"] - splay})
    return placed if half == "left" else [mirror_x(key) for key in placed]


def key_corners(key):
    """The four corners of the 18 x 17 mm key cell in board coordinates."""
    corners = []
    for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
        dx, dy = rotate(sx * KEY_PITCH_X / 2, sy * KEY_PITCH_Y / 2, -key["rot"])
        corners.append((key["x"] + dx, key["y"] + dy))
    return corners


def extents(keys):
    xs = [x for key in keys for x, _ in key_corners(key)]
    ys = [y for key in keys for _, y in key_corners(key)]
    return min(xs), min(ys), max(xs), max(ys)


def centre_in_envelope(keys, envelope, y_offset):
    """Centre the key extent in the usable envelope, origin is the keyboard well's top left corner."""
    min_x, min_y, max_x, max_y = extents(keys)
    shift_x = (envelope["x0"] + envelope["x1"] - (max_x - min_x)) / 2 - min_x
    shift_y = (envelope["y0"] + envelope["y1"] - (max_y - min_y)) / 2 - min_y + y_offset
    for key in keys:
        key["x"] = round(key["x"] + shift_x, 3)
        key["y"] = round(key["y"] + shift_y, 3)
        key["rot"] = round(key["rot"], 3)
    return keys


def inside(rect, x, y):
    return rect["x0"] < x < rect["x1"] and rect["y0"] < y < rect["y1"]


def fit_report(keys, notebook):
    """Key cells leaving the usable envelope or entering a keep-out."""
    envelope = notebook["envelope"]
    problems = []
    for key in keys:
        corners = key_corners(key)
        outside = [c for c in corners if not inside(envelope, *c)]
        if outside:
            problems.append(f'{key["ref"]} leaves the envelope by up to {max(well_overshoot(envelope, *c) for c in outside):.1f} mm')
        for keepout in notebook["keepouts"]:
            if any(inside(keepout, *c) for c in corners):
                problems.append(f'{key["ref"]} enters {keepout["name"]}')
    return problems


def well_overshoot(well, x, y):
    return max(well["x0"] - x, x - well["x1"], well["y0"] - y, y - well["y1"], 0.0)


def trackpad_notch(notebook):
    """Trackpad cut-out of the board: the trackpad keep-out widened by the clearance on each side."""
    trackpad = next(k for k in notebook["keepouts"] if k["name"] == "trackpad")
    clearance = notebook["board"]["trackpad_clearance"]
    return trackpad["x0"] - clearance, trackpad["x1"] + clearance, trackpad["y0"]


def board_holes(notebook):
    """Window polygons through the board: Touch ID widened by its clearance, the left edge at
    `touch_id_hole_x0` (see its note); empty without one."""
    board = notebook["board"]
    if "touch_id_hole_x0" not in board:
        return []
    touch_id = next(k for k in notebook["keepouts"] if k["name"] == "Touch ID")
    clearance = board["touch_id_clearance"]
    x0, x1 = board["touch_id_hole_x0"], touch_id["x1"] + clearance
    y0, y1 = touch_id["y0"] - clearance, touch_id["y1"] + clearance
    return [[(x0, y0), (x1, y0), (x1, y1), (x0, y1)]]


def board_outline(notebook):
    """Board polygon in well coordinates: full well width plus side overhang, a rest strip above the
    well, rest areas on the palm rest left and right of the trackpad, the trackpad itself cut out."""
    board = notebook["board"]
    well = notebook["well"]
    notch_x0, notch_x1, notch_y = trackpad_notch(notebook)
    x0, x1 = -board["side_overhang"], well["w"] + board["side_overhang"]
    y_top, y_bottom = -board["top_rest"], notch_y + board["bottom_rest"]
    return [
        (x0, y_top), (x1, y_top), (x1, y_bottom),
        (notch_x1, y_bottom), (notch_x1, notch_y),
        (notch_x0, notch_y), (notch_x0, y_bottom),
        (x0, y_bottom),
    ]


def rest_zones(notebook):
    """Where the board touches the deck: the strip above the well and the palm rest beside the trackpad."""
    board = notebook["board"]
    well = notebook["well"]
    notch_x0, notch_x1, notch_y = trackpad_notch(notebook)
    x0, x1 = -board["side_overhang"], well["w"] + board["side_overhang"]
    y_bottom = notch_y + board["bottom_rest"]
    return [
        {"name": "rest top", "x0": x0, "y0": -board["top_rest"], "x1": x1, "y1": 0.0},
        {"name": "rest left", "x0": x0, "y0": well["h"], "x1": notch_x0, "y1": y_bottom},
        {"name": "rest right", "x0": notch_x1, "y0": well["h"], "x1": x1, "y1": y_bottom},
    ]


def board_size(outline):
    xs = [x for x, _ in outline]
    ys = [y for _, y in outline]
    return max(xs) - min(xs), max(ys) - min(ys)


def svg_key(key):
    svg_turn = -key["rot"]
    return (
        f'<g transform="translate({key["x"]:.3f} {key["y"]:.3f}) rotate({svg_turn:.3f})">'
        f'<rect x="{-KEY_PITCH_X / 2}" y="{-KEY_PITCH_Y / 2}" width="{KEY_PITCH_X}" height="{KEY_PITCH_Y}" '
        f'fill="none" stroke="#bbb" stroke-width="0.15"/>'
        f'<rect x="{-SWITCH_W / 2}" y="{-SWITCH_H / 2}" width="{SWITCH_W}" height="{SWITCH_H}" '
        f'fill="none" stroke="#000" stroke-width="0.25"/>'
        f'<line x1="-1" y1="0" x2="1" y2="0" stroke="#000" stroke-width="0.15"/>'
        f'<line x1="0" y1="-1" x2="0" y2="1" stroke="#000" stroke-width="0.15"/>'
        f'<text x="0" y="5" font-size="2.2" text-anchor="middle" font-family="monospace" fill="#555">'
        f'{key["ref"].replace("SW_L_4_", "")}</text></g>'
    )


def svg_ruler(x0, y0, horizontal):
    """100 mm ruler with 0.1 mm wide ticks every 10 mm (long at 0, 50, 100), measured tick to tick."""
    parts = []
    for mm in range(0, 101, 10):
        tick = 4.0 if mm % 50 == 0 else 2.0
        if horizontal:
            parts.append(f'<line x1="{x0 + mm}" y1="{y0 - tick}" x2="{x0 + mm}" y2="{y0}" stroke="#000" stroke-width="0.1"/>')
        else:
            parts.append(f'<line x1="{x0}" y1="{y0 + mm}" x2="{x0 + tick}" y2="{y0 + mm}" stroke="#000" stroke-width="0.1"/>')
    x1, y1 = (x0 + 100, y0) if horizontal else (x0, y0 + 100)
    parts.append(f'<line x1="{x0}" y1="{y0}" x2="{x1}" y2="{y1}" stroke="#000" stroke-width="0.1"/>')
    return "".join(parts)


def svg_rect(rect, stroke, dash=None, label=None):
    dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
    svg = (f'<rect x="{rect["x0"]:.3f}" y="{rect["y0"]:.3f}" width="{rect["x1"] - rect["x0"]:.3f}" '
           f'height="{rect["y1"] - rect["y0"]:.3f}" fill="none" stroke="{stroke}" stroke-width="0.3"{dash_attr}/>')
    if label:
        svg += (f'<text x="{rect["x0"] + 1:.3f}" y="{rect["y0"] + 3:.3f}" font-size="2.5" '
                f'font-family="monospace" fill="{stroke}">{label}</text>')
    return svg


def write_svg(keys, notebook, args, problems, outline):
    """1:1 SVG. With a board outline the page is A4 landscape with the board centred, the scale
    bar and the notes sit in the trackpad notch; without one the page wraps well and keys."""
    well = notebook["well"]
    min_x, min_y, max_x, max_y = extents(keys)
    xs = [0.0, well["w"]] + [x for x, _ in outline]
    ys = [0.0, well["h"]] + [y for _, y in outline]
    if outline:
        width, height = A4_LANDSCAPE
        view_x0 = (min(xs) + max(xs) - width) / 2
        view_y0 = (min(ys) + max(ys) - height) / 2
        scale_x0, scale_y = (min(xs) + max(xs)) / 2 - 50, max(ys) - 25
    else:
        view_x0, view_y0 = min(xs) - SVG_BORDER, min(ys) - SVG_BORDER
        width = max(xs) - min(xs) + 2 * SVG_BORDER
        height = max(ys) - min(ys) + 2 * SVG_BORDER + 16
        scale_x0, scale_y = 0, max(ys) + 6
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width:.1f}mm" height="{height:.1f}mm" '
        f'viewBox="{view_x0:.1f} {view_y0:.1f} {width:.1f} {height:.1f}">',
        svg_rect({"x0": 0, "y0": 0, "x1": well["w"], "y1": well["h"]}, "#06c", label=f'{notebook["name"]} keyboard well'),
        svg_rect(notebook["envelope"], "#0a8", dash="3 1"),
        svg_rect({"x0": min_x, "y0": min_y, "x1": max_x, "y1": max_y}, "#e33", dash="2 1"),
    ]
    for keepout in notebook["keepouts"]:
        parts.append(svg_rect(keepout, "#c60", dash="1 1", label=keepout["name"]))
    if outline:
        for zone in rest_zones(notebook):
            parts.append(svg_rect(zone, "#999", dash="0.5 0.5", label=zone["name"]))
        for polygon in [outline, *board_holes(notebook)]:
            points = " ".join(f"{x:.3f},{y:.3f}" for x, y in polygon)
            parts.append(f'<polygon points="{points}" fill="none" stroke="#000" stroke-width="0.4"/>')
    parts.extend(svg_key(key) for key in keys)
    parts.append(
        svg_ruler(scale_x0, scale_y, horizontal=True) +
        f'<text x="{scale_x0 + 50}" y="{scale_y + 4}" font-size="3" text-anchor="middle" font-family="monospace">'
        f'100 mm scale check: A4 (not borderless), scale 100 %</text>'
    )
    if outline:
        # vertical ruler between the halves, catches a printer that scales one axis only
        bar_x = (min(xs) + max(xs)) / 2
        parts.append(
            svg_ruler(bar_x, 5, horizontal=False) +
            f'<text x="{bar_x + 5}" y="56" font-size="3" font-family="monospace">100 mm</text>'
        )
    parts.append(
        f'<text x="{scale_x0 + 50}" y="{scale_y + 8}" font-size="2.0" text-anchor="middle" font-family="monospace">'
        f'splay {args.splay} deg, gap {args.gap} mm, columns {args.column_splay}, thumbs {args.thumb_shift}, '
        f'keys extent {max_x - min_x:.1f} x {max_y - min_y:.1f} mm, {len(problems)} fit problems</text>'
    )
    parts.append("</svg>")
    SVG_PATH.parent.mkdir(parents=True, exist_ok=True)
    SVG_PATH.write_text("\n".join(parts) + "\n")


def widest_fitting_gap(build, start=0.0, stop=120.0, step=0.5):
    """Largest gap in [start, stop] whose layout has no fit problems, start if none fits."""
    best = start
    gap = start
    while gap <= stop:
        if not build(gap)[1]:
            best = gap
        gap += step
    return round(best, 1)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--splay", type=float, default=20.0, help="inward rotation per half in degrees")
    parser.add_argument("--gap", default="auto",
                        help="distance between the inner top corners in mm, or auto for the widest gap that still fits")
    parser.add_argument("--thumb-shift", default="8,1", help="move the thumb keys inward,down in mm (half's own frame)")
    parser.add_argument("--column-splay", default=DEFAULT_COLUMN_SPLAY,
                        help="ergogen style per column splay, pinky to inner, relative to the previous column")
    parser.add_argument("--notebook", default="mbp14", help="reference geometry from tools/notebooks.json")
    parser.add_argument("--drop", default=DEFAULT_DROP, help="comma separated switch references to leave out")
    parser.add_argument("--y-offset", type=float, default=0.0, help="move the keys down in the well (negative: up)")
    args = parser.parse_args()
    column_splay = [float(value) for value in args.column_splay.split(",")]
    dropped = set(filter(None, args.drop.split(",")))
    notebook = json.loads(NOTEBOOKS_PATH.read_text())[args.notebook]

    thumb_shift = tuple(float(value) for value in args.thumb_shift.split(","))
    source_keys = [key for key in json.loads(KEYS_PATH.read_text()) if key["ref"] not in dropped]

    def build(gap):
        keys = []
        for half in ("left", "right"):
            half_keys = [key for key in source_keys if key["half"] == half]
            keys.extend(place_half(half_keys, half, args.splay, gap, column_splay, thumb_shift))
        centre_in_envelope(keys, notebook["envelope"], args.y_offset)
        return keys, fit_report(keys, notebook)

    if args.gap == "auto":
        args.gap = widest_fitting_gap(build)
    else:
        args.gap = float(args.gap)
    keys, problems = build(args.gap)
    outline = board_outline(notebook) if "board" in notebook else []

    write_svg(keys, notebook, args, problems, outline)
    JSON_PATH.write_text(json.dumps({
        "notebook": args.notebook, "splay": args.splay, "gap": args.gap, "column_splay": column_splay,
        "thumb_shift": list(thumb_shift), "dropped": sorted(dropped),
        "outline": [[round(x, 3), round(y, 3)] for x, y in outline],
        "holes": [[[round(x, 3), round(y, 3)] for x, y in hole] for hole in (board_holes(notebook) if outline else [])],
        "corner_radius": notebook.get("board", {}).get("corner_radius"),
        "keys": keys,
    }, indent=2) + "\n")

    min_x, min_y, max_x, max_y = extents(keys)
    print(f'{len(keys)} keys, extent {max_x - min_x:.1f} x {max_y - min_y:.1f} mm in a '
          f'{notebook["well"]["w"]} x {notebook["well"]["h"]} mm well, margins '
          f'left {min_x:.1f} right {notebook["well"]["w"] - max_x:.1f} top {min_y:.1f} bottom {notebook["well"]["h"] - max_y:.1f}')
    for problem in problems:
        print(f"  ! {problem}")
    if outline:
        board_w, board_h = board_size(outline)
        print(f"board outline {board_w:.1f} x {board_h:.1f} mm")
        for name, other in json.loads(NOTEBOOKS_PATH.read_text()).items():
            limit = other.get("board_limit")
            if limit:
                verdict = "fits" if board_w <= limit["w"] and board_h <= limit["h"] else "TOO BIG"
                print(f'  {other["name"]} limit {limit["w"]} x {limit["h"]}: {verdict}')
    print(f"SVG  -> {SVG_PATH}")
    subprocess.run([sys.executable, "-I", str(REPO / "tools" / "svg_to_pdf.py"), str(SVG_PATH), str(PDF_PATH)], check=True)
    print(f"PDF  -> {PDF_PATH}")
    print(f"JSON -> {JSON_PATH}")


if __name__ == "__main__":
    main()
