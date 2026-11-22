#!/usr/bin/env python3
"""
PCB generator for the mnhTTn48 unibody. Needs KiCad's bundled Python (pcbnew module):

    /Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3 -I tools/gen_pcb.py

Reads board/layout.json (keys in well coordinates, board outline), tools/matrix.json (electrical
matrix) and the schematic netlist (exported with kicad-cli), writes board/mnhttn48-unibody.kicad_pcb.
tools/drc.sh runs this and the DRC.

Routing scheme (key frame = switch footprint coordinates, y down, KiCad rotation CCW positive;
well coordinates = board/layout.json, board coordinates = well + ORIGIN):
  COL bus    F.Cu at local y 10.2 through the keys of a physical row, stub from switch pad 2
             (entered at (1.75, 3.65) through solid material beside the pocket) via (1.0, 4.4).
             The bus ends in a via on its lane: B.Cu verticals at x 10..13 in the frame of the
             inner column's top key, which jog on B.Cu above the top key to global verticals
             beside the centre and run down to vias beside the shift register. Thumb keys reach
             the lane ends of rows 0/1 (frame y 62, under the row 3 bus) on F.Cu along their
             inner cell edge.
  anode band Each key's switch pad 1 leaves on B.Cu to the row gap below the switch (local y
             8.4 - 0.75 c, c = finger column 0 pinky .. 4 inner, the pinky lowest) and runs
             inward through the cells of its row. Where the next cell sits higher or lower
             (column splay) every passing track climbs on its own staircase lane at the inner
             edge of the outer cell (local x 7 + 0.75 n), ordered so nothing crosses. In the
             inner key the tracks drop to via A (local (4.5 + c, 9.2)), bridge the lanes on F.Cu
             at local y 6.4 + 0.5 c and go back to B.Cu at via B (frame x 15.5 + c, y 4.6 of the
             inner column), then run horizontally into the diode block on levels 1.2 mm apart,
             the innermost via B on the highest level so no line passes under another via.
  diodes     One block per half in the centre, four mini rows of five SOD-323 (net column c at
             x centre -/+ (11.3 - 1.9 c), vertical, anode on top) at the height of their key row
             plus two thumb diodes in column 5 (7 mm apart, above the bottom band). Thumb anodes
             run parallel to their switch inside a cell and horizontally in between (B.Cu is free
             in a cell's top strip): the inner thumb's along its top strip to its inner edge at
             its diode's height, the outer thumb's along its own top strip, across the gap, along
             the inner thumb's top strip (local y -7.5) down to its diode's height; both then
             straight into the block, below the row 3 crossbars. Via C on the
             B.Cu line drops on F.Cu into the anode; cathodes join F.Cu buses (one per net,
             x_c + 0.95) that run down to the bottom band.
  ROW nets   bottom band on B.Cu (well y 113.6 + 0.8 (5 - row), above the trackpad notch edge)
             from both blocks leftwards under the thumbs into the left palm rest leg, up the
             left margin (well x 1 + row) and from below into the XIAO's bottom pad row D0..D5.
  XIAO       top left corner, rotated 90 so the USB-C points left out of the board. Top pad row
             (5V, GND, 3V3, MOSI, CS, SCK, D7) is entered from below by the strip lines (B.Cu at
             LINE_Y). SW1 (reset, pads in two columns) sits below it, RST and the SW1 GND leave
             the XIAO between its bottom pads. SW2 (power), the battery pads and the battery sit
             in the centre above the register; +BATT leaves the
             XIAO on B.Cu, hops to F.Cu and runs along the top edge, BAT- hangs on the GND line.
  register   74HC595 rotated 90 (pins 1..8 bottom row, 9..16 top row) at well y 26 in the centre,
             risers on F.Cu up to the strip lines, C1 right of it, VCC tied to SRCLR under the
             chip, GND pin 8 through a riser right of the chip.
"""

import json
import math
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

import pcbnew

REPO = Path(__file__).resolve().parent.parent
BOARD_DIR = REPO / "board"
LIB = str(BOARD_DIR / "mnhttn.pretty")
PROJECT = "mnhttn48-unibody"
PCB_PATH = BOARD_DIR / f"{PROJECT}.kicad_pcb"
NETLIST_PATH = BOARD_DIR / f"{PROJECT}.net.xml"

ORIGIN = (8.35, 20.0)          # well coordinates -> board coordinates, board centred on the A4 sheet
TRACK = 0.25
VIA_SIZE, VIA_DRILL = 0.8, 0.4
BOARD_THICKNESS = 2.0

DIODE_FOOTPRINT = "D_SOD-323_HandSoldering"
COL_Y = 10.2                   # COL bus y in the key frame (below the band, the bridges and the lane via)
BAND_Y0, BAND_STEP = 8.4, 0.75 # anode band levels in the key frame, pinky lowest
CELL_W, CELL_H = 18.0, 17.0
LANE_X = {0: 10.0, 1: 11.0, 2: 12.0, 3: 13.0}
LANE_TOP_Y = -CELL_H / 2 + 2.0
LANE_BOTTOM_Y = {0: 62.0, 1: 62.0, 2: 2 * CELL_H + COL_Y, 3: 3 * CELL_H + COL_Y}
VIA_A_X, VIA_A_Y, VIA_B_X, VIA_B_Y = 4.5, 9.2, 15.5, 4.6   # anode band hops around the lanes
BRIDGE_Y0, BRIDGE_STEP = 6.4, 0.5   # F.Cu bridge levels in the inner key (below the housing pad, above via A)
CROSSBAR_STEP = 1.2            # B.Cu levels into the diode block
THUMB_TOP_STRIP_Y = -7.5      # outer thumb anode in the inner thumb's cell (B.Cu is free above the pins)
STEP_LANE_X0, STEP_LANE_PITCH = 7.0, 0.75   # staircase lanes between two cells of a row (outer cell frame)
GLOBAL_LANE_DX = {0: 12.5, 1: 13.5, 2: 14.5, 3: 15.5}
JOG_ORDER = {0: 3, 1: 2, 2: 1, 3: 0}
LINE_Y = {"gnd": -1.4, "v33": -2.15, "mosi": -2.9, "cs": -3.65, "sck": -4.4}   # strip lines, well y
XIAO_POS, XIAO_ROT = (8.0, 0.5), 90
REG_Y = 26.0                   # well y of the shift register
BLOCK_DX0, BLOCK_PITCH = 11.3, 1.9      # diode columns at centre -/+ (BLOCK_DX0 - BLOCK_PITCH c)
BUS_DX = 0.95                  # cathode bus offset from the diode column, towards the centre
BAND_WELL_Y, BAND_PITCH = 113.6, 0.8   # bottom band lines ROW_0..5, well y
MARGIN_X = {row: 1.0 + row for row in range(6)}       # ROW buses up the left margin, well x
PAD_ENTRY_Y = {row: 10.6 + 0.75 * row for row in range(6)}   # into D0..D5 from below, well y
def mm(value):
    return pcbnew.FromMM(value)


def vec(x, y):
    return pcbnew.VECTOR2I(mm(x), mm(y))


def rotate(x, y, degrees):
    radians = math.radians(degrees)
    return x * math.cos(radians) - y * math.sin(radians), x * math.sin(radians) + y * math.cos(radians)


class Frame:
    def __init__(self, x, y, rot):
        self.x, self.y, self.rot = x, y, rot

    def g(self, lx, ly):
        dx, dy = rotate(lx, ly, -self.rot)
        return self.x + dx, self.y + dy

    def local(self, gx, gy):
        return rotate(gx - self.x, gy - self.y, self.rot)

    def ly_at(self, lx, gy):
        """Local y of the point on the local vertical x = lx that lies at global y gy."""
        radians = math.radians(-self.rot)
        return (gy - self.y - lx * math.sin(radians)) / math.cos(radians)

    def lx_at(self, ly, gy):
        """Local x of the point on the local horizontal y = ly that lies at global y gy."""
        radians = math.radians(-self.rot)
        return (gy - self.y - ly * math.cos(radians)) / math.sin(radians)


def point_at_y(frame, lx, inner, inner_y, ly0=4.7, ly1=-CELL_H / 2 - 1.0):
    """Point on the frame's local vertical x = lx (between ly0 and ly1) that lies at inner_y in `inner`."""
    a, b = frame.g(lx, ly0), frame.g(lx, ly1)
    t = (inner_y - inner.local(*a)[1]) / (inner.local(*b)[1] - inner.local(*a)[1])
    return a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1])


# ---------------------------------------------------------------- board helpers


class Board:
    def __init__(self, pad_nets, values):
        self.board = pcbnew.BOARD()
        settings = self.board.GetDesignSettings()
        settings.SetCopperLayerCount(2)
        settings.SetBoardThickness(mm(BOARD_THICKNESS))
        self.pad_nets = pad_nets
        self.values = values
        self.nets = {}
        self.footprints = {}

    def net(self, name):
        if name not in self.nets:
            item = pcbnew.NETINFO_ITEM(self.board, name)
            self.board.Add(item)
            self.nets[name] = item
        return self.nets[name]

    def net_of(self, ref, pad):
        return self.pad_nets[ref][pad]

    def place(self, ref, footprint_name, x, y, rot, hide_reference=False):
        fp = pcbnew.FootprintLoad(LIB, footprint_name)
        fp.SetFPID(pcbnew.LIB_ID("mnhttn", footprint_name))
        fp.SetReference(ref)
        fp.SetValue(self.values[ref])
        fp.SetPosition(vec(x, y))
        fp.SetOrientationDegrees(rot)
        if hide_reference:
            fp.Reference().SetVisible(False)
        for pad in fp.Pads():
            net_name = self.pad_nets.get(ref, {}).get(pad.GetNumber())
            if net_name:
                pad.SetNet(self.net(net_name))
        self.board.Add(fp)
        self.footprints[ref] = fp
        return Frame(x, y, rot)

    def pad_xy(self, ref, number):
        for pad in self.footprints[ref].Pads():
            if pad.GetNumber() == number:
                pos = pad.GetPosition()
                return pcbnew.ToMM(pos.x), pcbnew.ToMM(pos.y)
        raise KeyError(f"{ref} pad {number}")

    def track(self, net_name, layer, points, width=TRACK):
        for (x1, y1), (x2, y2) in zip(points, points[1:]):
            if abs(x1 - x2) < 1e-6 and abs(y1 - y2) < 1e-6:
                continue
            segment = pcbnew.PCB_TRACK(self.board)
            segment.SetStart(vec(x1, y1))
            segment.SetEnd(vec(x2, y2))
            segment.SetWidth(mm(width))
            segment.SetLayer(layer)
            segment.SetNet(self.net(net_name))
            self.board.Add(segment)

    def via(self, net_name, x, y):
        via = pcbnew.PCB_VIA(self.board)
        via.SetPosition(vec(x, y))
        via.SetWidth(mm(VIA_SIZE))
        via.SetDrill(mm(VIA_DRILL))
        via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
        via.SetNet(self.net(net_name))
        self.board.Add(via)

    def edge_line(self, x1, y1, x2, y2):
        shape = pcbnew.PCB_SHAPE(self.board, pcbnew.SHAPE_T_SEGMENT)
        shape.SetStart(vec(x1, y1))
        shape.SetEnd(vec(x2, y2))
        shape.SetLayer(pcbnew.Edge_Cuts)
        shape.SetWidth(mm(0.1))
        self.board.Add(shape)


    def edge_arc(self, start, mid, end):
        shape = pcbnew.PCB_SHAPE(self.board, pcbnew.SHAPE_T_ARC)
        shape.SetArcGeometry(vec(*start), vec(*mid), vec(*end))
        shape.SetLayer(pcbnew.Edge_Cuts)
        shape.SetWidth(mm(0.1))
        self.board.Add(shape)

    def save(self):
        self.board.SetFileName(str(PCB_PATH))
        pcbnew.SaveBoard(str(PCB_PATH), self.board)


def export_netlist():
    subprocess.run(["kicad-cli", "sch", "export", "netlist", "--format", "kicadxml", "--output", str(NETLIST_PATH),
                    str(BOARD_DIR / f"{PROJECT}.kicad_sch")], check=True, capture_output=True)
    root = ET.parse(NETLIST_PATH).getroot()
    pad_nets = {}
    for net in root.find("nets"):
        name = net.get("name")
        if name.startswith("unconnected-"):
            name = name.replace("/", "{slash}")      # how the parity check spells these
        for node in net.findall("node"):
            pad_nets.setdefault(node.get("ref"), {})[node.get("pin")] = name
    values = {comp.get("ref"): comp.find("value").text for comp in root.find("components")}
    return pad_nets, values


def rounded_outline(board, polygon, radius):
    """Edge.Cuts lines and arcs for a polygon with every corner rounded (convex or concave)."""
    count = len(polygon)
    corners = []
    for index in range(count):
        px, py = polygon[index - 1]
        cx, cy = polygon[index]
        nx, ny = polygon[(index + 1) % count]
        into = (px - cx, py - cy)
        out = (nx - cx, ny - cy)
        u_in = (into[0] / math.hypot(*into), into[1] / math.hypot(*into))
        u_out = (out[0] / math.hypot(*out), out[1] / math.hypot(*out))
        a = (cx + u_in[0] * radius, cy + u_in[1] * radius)
        b = (cx + u_out[0] * radius, cy + u_out[1] * radius)
        bisector = (u_in[0] + u_out[0], u_in[1] + u_out[1])
        blen = math.hypot(*bisector)
        centre = (cx + bisector[0] / blen * radius * math.sqrt(2), cy + bisector[1] / blen * radius * math.sqrt(2))
        mid = (centre[0] - bisector[0] / blen * radius, centre[1] - bisector[1] / blen * radius)
        corners.append((a, mid, b))
    for index in range(count):
        a, mid, b = corners[index]
        board.edge_arc(a, mid, b)
        next_a = corners[(index + 1) % count][0]
        board.edge_line(b[0], b[1], next_a[0], next_a[1])




# ---------------------------------------------------------------- key matrix


def band_y(column):
    return BAND_Y0 - BAND_STEP * column


def bridge_y(column):
    return BRIDGE_Y0 + BRIDGE_STEP * column


def key_cell_tracks(board, frame, sw, diode, column):
    """COL stub on F.Cu and the anode's drop to its band level on B.Cu."""
    board.track(board.net_of(sw, "2"), pcbnew.F_Cu, [frame.g(1.75, 3.65), frame.g(1.0, 4.4), frame.g(1.0, COL_Y)])
    board.track(board.net_of(diode, "2"), pcbnew.B_Cu, [frame.g(0.41, 3.65), frame.g(-0.6, 4.7), frame.g(-0.6, band_y(column))])


def route_half(board, half_name, keys, frames, matrix, centre_x, oy):
    """COL buses, lanes and anode bands of one half. Returns the B vias per (row, column) and the thumbs."""
    sign = 1 if half_name == "left" else -1
    columns, rows, thumbs = {}, {}, []
    for key in keys:
        ref = key["ref"]
        col, row = matrix[ref]["col"], matrix[ref]["row"]
        if row == 5:
            thumbs.append((col, ref))
        else:
            columns.setdefault(row, []).append((col, ref))
            rows.setdefault(col, []).append((row, ref))
    for members in list(columns.values()) + list(rows.values()):
        members.sort()
    thumbs.sort()
    inner = frames[columns[4][0][1]]
    lane_x = {r: sign * x for r, x in LANE_X.items()}
    col_net = {col: board.net_of(members[0][1], "2") for col, members in rows.items()}
    anode_net = lambda ref: board.net_of(ref.replace("SW_L_4_", "D_L_4_"), "2")
    out = {"b_via": {}, "thumbs": thumbs, "sign": sign, "inner": inner, "rows": rows}

    # COL buses along the rows on F.Cu, ending in a via on the lane
    for col, members in rows.items():
        key_row = col % 4
        points = [frames[members[0][1]].g(1.0, COL_Y)]
        for index, (_, ref) in enumerate(members):
            if index < len(members) - 1:
                points.append(frames[ref].g(sign * CELL_W / 2, COL_Y))
                points.append(frames[members[index + 1][1]].g(-sign * CELL_W / 2, COL_Y))
        lane_point = inner.g(lane_x[key_row], key_row * CELL_H + COL_Y)
        points.append(lane_point)
        board.track(col_net[col], pcbnew.F_Cu, points)
        board.via(col_net[col], *lane_point)

    # lanes on B.Cu and their jogs to the global verticals
    first_col = 0 if sign == 1 else 4
    lane_top = {}
    for key_row, x in lane_x.items():
        top = inner.g(x, LANE_TOP_Y)
        board.track(col_net[first_col + key_row], pcbnew.B_Cu, [top, inner.g(x, LANE_BOTTOM_Y[key_row])])
        lane_top[key_row] = top
    top_min = min(point[1] for point in lane_top.values())
    out["global"] = {}
    for key_row, top in lane_top.items():
        jog_y = top_min - 1.0 - 1.0 * JOG_ORDER[key_row]
        gx = centre_x - sign * GLOBAL_LANE_DX[key_row]
        board.track(col_net[first_col + key_row], pcbnew.B_Cu, [top, (top[0], jog_y), (gx, jog_y)])
        out["global"][key_row] = (gx, jog_y)

    # thumbs: COL on F.Cu along the inner cell edge up to just below the lane end (via there)
    for col, ref in thumbs:
        f = frames[ref]
        key_row = col % 4
        lane_end = inner.g(lane_x[key_row], LANE_BOTTOM_Y[key_row])
        meet = point_at_y(f, sign * CELL_W / 2, inner, LANE_BOTTOM_Y[key_row] + 0.45, ly0=7.0)
        board.track(col_net[col], pcbnew.F_Cu, [f.g(1.0, 4.4), f.g(1.0, 7.0), f.g(sign * CELL_W / 2, 7.0), meet, lane_end])
        board.via(col_net[col], *lane_end)

    # anode bands: inward through the row on B.Cu. Between two cells every passing track climbs or
    # descends on its own staircase lane in the outer cell (the next cell sits higher or lower),
    # ordered so nothing crosses. In the inner key the tracks drop to via A, bridge the lanes on
    # F.Cu on their own level and go back to B.Cu at via B outside the cell.
    for col, members in rows.items():
        key_row = col % 4
        inner_key = frames[members[-1][1]]
        paths = {column: [frames[ref].g(-0.6, band_y(column))] for column, (_, ref) in enumerate(members)}
        for step in range(len(members) - 1):
            outer, nxt = frames[members[step][1]], frames[members[step + 1][1]]
            passing = list(range(step + 1))
            targets = {c: nxt.g(-sign * CELL_W / 2, band_y(c)) for c in passing}
            climbs = {c: outer.local(*targets[c])[1] - band_y(c) for c in passing}
            ascending = sum(climbs.values()) < 0
            order = sorted(passing, key=lambda c: band_y(c), reverse=not ascending)
            for lane, c in enumerate(order):
                lane_x = sign * (STEP_LANE_X0 + STEP_LANE_PITCH * lane)
                paths[c] += [outer.g(lane_x, band_y(c)), outer.g(lane_x, band_y(c) + climbs[c]), targets[c]]
        for column, (_, ref) in enumerate(members):
            net = anode_net(ref)
            ax = sign * (VIA_A_X + 1.0 * column)
            via_a = inner_key.g(ax, VIA_A_Y)
            board.track(net, pcbnew.B_Cu, paths[column] + [inner_key.g(ax, band_y(column)), via_a])
            board.via(net, *via_a)
            bx = sign * (VIA_B_X + 1.0 * column)
            via_b = inner.g(bx, key_row * CELL_H + VIA_B_Y)
            board.track(net, pcbnew.F_Cu, [via_a, inner_key.g(ax, bridge_y(column)), inner_key.g(bx, bridge_y(column)), via_b])
            board.via(net, *via_b)
            out["b_via"][(key_row, column)] = via_b
    return out


# ---------------------------------------------------------------- diode blocks


def route_block(board, half, frames, cx, ox, oy):
    """Diode block of one half: mini rows at the key rows' heights, cathode buses down to the band."""
    sign = half["sign"]
    inner = half["inner"]
    F, B = pcbnew.F_Cu, pcbnew.B_Cu
    diode_x = {c: cx - sign * (BLOCK_DX0 - BLOCK_PITCH * c) for c in range(6)}
    bus_x = {c: diode_x[c] + sign * BUS_DX for c in range(6)}
    cathodes = {c: [] for c in range(6)}

    def place_diode(ref, x, level):
        """Diode below `level` with the anode on top, via C on the B.Cu line above it, F.Cu drop."""
        board.place(ref, DIODE_FOOTPRINT, x, level + 3.85, 90, hide_reference=True)
        net = board.net_of(ref, "2")
        board.via(net, x, level)
        board.track(net, F, [(x, level), board.pad_xy(ref, "2")])
        cathodes[column_of[ref]].append(board.pad_xy(ref, "1"))

    column_of = {}
    for col, members in half["rows"].items():
        for column, (_, ref) in enumerate(members):
            column_of[ref.replace("SW_L_4_", "D_L_4_")] = column
    for _, ref in half["thumbs"]:
        column_of[ref.replace("SW_L_4_", "D_L_4_")] = 5

    lowest_level = 0.0
    for col, members in half["rows"].items():
        key_row = col % 4
        base_y = max(half["b_via"][(key_row, c)][1] for c in range(5))
        for column, (_, ref) in enumerate(members):
            diode = ref.replace("SW_L_4_", "D_L_4_")
            net = board.net_of(diode, "2")
            via_b = half["b_via"][(key_row, column)]
            level = base_y + CROSSBAR_STEP * (5 - column)
            board.track(net, B, [via_b, (via_b[0] + sign * 0.5, level), (diode_x[column], level)])
            place_diode(diode, diode_x[column], level)
            lowest_level = max(lowest_level, level)
    # thumbs: parallel to their switch inside a cell, horizontal in between. The inner thumb's
    # anode runs along its cell's top strip to the inner edge, which it crosses at its diode's
    # height, and straight into column 5. The outer thumb's runs along its own top strip,
    # horizontally across the gap into the inner thumb's top strip, along it down to its diode's
    # height and straight into column 5, above the inner thumb's line.
    (_, outer_ref), (_, inner_ref) = half["thumbs"]
    outer, inner_thumb = frames[outer_ref], frames[inner_ref]
    edge = sign * CELL_W / 2
    levels = [lowest_level + CROSSBAR_STEP + 7.0 * index for index in range(2)]

    def leave_upwards(f, ly):
        return [f.g(0.41, 3.65), f.g(-0.6, 4.7), f.g(-3.0, 4.7), f.g(-3.0, ly)]

    inner_ly = inner_thumb.ly_at(edge, levels[1])
    inner_path = leave_upwards(inner_thumb, inner_ly) + [inner_thumb.g(edge, inner_ly), (diode_x[5], levels[1])]
    gap_point = inner_thumb.g(-edge, THUMB_TOP_STRIP_Y)
    outer_ly = outer.ly_at(edge, gap_point[1])
    knee = inner_thumb.g(inner_thumb.lx_at(THUMB_TOP_STRIP_Y, levels[0]), THUMB_TOP_STRIP_Y)
    outer_path = leave_upwards(outer, outer_ly) + [outer.g(edge, outer_ly), gap_point, knee, (diode_x[5], levels[0])]
    for ref, path, level in ((outer_ref, outer_path, levels[0]), (inner_ref, inner_path, levels[1])):
        diode = ref.replace("SW_L_4_", "D_L_4_")
        board.track(board.net_of(diode, "2"), B, path)
        place_diode(diode, diode_x[5], level)
    # cathode buses: F.Cu verticals beside the column, stubs from every cathode, down to the band
    out = {"band_via_x": {}}
    for column in range(6):
        net = board.net_of("U1", str(column + 1))
        x = bus_x[column]
        pads = sorted(cathodes[column], key=lambda p: p[1])
        band_y_row = oy + BAND_WELL_Y + BAND_PITCH * (5 - column)
        board.track(net, F, [(x, pads[0][1] + 0.5), (x, band_y_row)])
        board.via(net, x, band_y_row)
        for pad in pads:
            board.track(net, F, [pad, (x, pad[1] + 0.5)])
        out["band_via_x"][column] = x
    return out


# ---------------------------------------------------------------- electronics and nets to the XIAO


def board_pads(board, ref, number):
    return [(pcbnew.ToMM(p.GetPosition().x), pcbnew.ToMM(p.GetPosition().y))
            for p in board.footprints[ref].Pads() if p.GetNumber() == number]


def route_electronics(board, left_block, right_block, cx, ox, oy):
    F, B = pcbnew.F_Cu, pcbnew.B_Cu
    pad = board.pad_xy

    def w(x, y):
        return ox + x, oy + y

    def reg(dx, dy):
        return cx + dx, oy + REG_Y + dy

    board.place("U1", "xiao-ble-smd-cutout", *w(*XIAO_POS), XIAO_ROT)
    board.place("U2", "SOIC-16_3.9x9.9mm_P1.27mm", cx, oy + REG_Y, 90)
    board.place("C1", "C_0603_1608Metric", cx + 8.5, oy + REG_Y - 5.0, 0)
    board.place("SW1", "PushSwitch", *w(13.0, 20.0), 90)
    board.place("SW2", "MSK12C02", cx - 24.0, oy + 0.8, 90)   # pins up, locating pins just below the GND line
    board.place("BAT+1", "BatteryPad", cx - 22.0, oy + 8.0, 0)
    board.place("BAT-1", "BatteryPad", cx - 16.0, oy + 8.0, 0)
    if pad("C1", "1")[0] > pad("C1", "2")[0]:
        board.footprints["C1"].SetOrientationDegrees(180)
    for number in ("1", "2"):
        board.track(board.net_of("SW1", number), F, board_pads(board, "SW1", number))
    nets = {name: board.net_of("U1", number) for name, number in
            (("gnd", "13"), ("v33", "12"), ("mosi", "11"), ("cs", "10"), ("sck", "9"), ("rst", "17"), ("batt", "19"))}
    nets["bat_sw"] = board.net_of("SW2", "2")
    line_y = {name: oy + y for name, y in LINE_Y.items()}

    # bottom band: ROW nets from both blocks on B.Cu, then up the left margin into D0..D5 from below
    for row in range(6):
        net = board.net_of("U1", str(row + 1))
        band = oy + BAND_WELL_Y + BAND_PITCH * (5 - row)
        margin_x = ox + MARGIN_X[row]
        target = pad("U1", str(row + 1))
        board.track(net, B, [(right_block["band_via_x"][row], band), (margin_x, band),
                             (margin_x, oy + PAD_ENTRY_Y[row]), (target[0], oy + PAD_ENTRY_Y[row]), target])

    # COL lanes from the jog points down to vias beside the shift register, F.Cu into the pads
    via_for = {
        0: ((-4.5, -6.5), "15", [(-3.2, -5.0)]),
        1: ((-4.4, 6.5), "1", []), 2: ((-3.2, 7.5), "2", []), 3: ((-1.9, 8.5), "3", []),
        4: ((-0.6, 5.5), "4", []), 5: ((0.6, 6.5), "5", []), 6: ((1.9, 7.5), "6", []), 7: ((3.2, 8.5), "7", []),
    }
    for side, sign in ((left_block["half"], 1), (right_block["half"], -1)):
        for key_row in (0, 1, 2, 3):
            col = (0 if sign == 1 else 4) + key_row
            via_rel, number, path = via_for[col]
            net = board.net_of("U2", number)
            start = side["global"][key_row]
            via_point = reg(*via_rel)
            board.track(net, B, [start, (start[0], via_point[1]), via_point])
            board.via(net, *via_point)
            board.track(net, F, [via_point] + [reg(*p) for p in path] + [pad("U2", number)])

    # SPI, 3V3 and GND lines from the XIAO's top row (entered from below) to the register's risers
    riser = {"mosi": ("14", cx - 1.9), "cs": ("12", cx + 0.6), "sck": ("11", cx + 1.9), "v33": ("10", cx + 3.2), "gnd": ("13", cx - 0.6)}
    gnd_right = cx + 9.275
    for name, number in (("gnd", "13"), ("v33", "12"), ("mosi", "11"), ("cs", "10"), ("sck", "9")):
        px, py = pad("U1", number)
        if name == "gnd":
            start = (px + 1.0, line_y[name])
            board.track(nets[name], B, [start, (start[0], py + 2.0), (px, py + 1.2), (px, py)])
            board.track(nets[name], B, [start, (gnd_right, line_y[name])])
        else:
            board.track(nets[name], B, [(px, py), (px, line_y[name]), (riser[name][1], line_y[name])])
        top = pad("U2", riser[name][0])
        board.track(nets[name], F, [top, (top[0], line_y[name])])
        board.via(nets[name], top[0], line_y[name])
    p13, p18, p20 = pad("U1", "13"), pad("U1", "18"), pad("U1", "20")
    board.track(nets["gnd"], B, [(p18[0] + 0.53, p18[1]), (p13[0] + 1.0, p18[1]), (p13[0] + 1.0, p13[1] + 2.0)])
    board.track(nets["gnd"], B, [(p20[0] - 0.58, p20[1] + 0.3), (p13[0] + 1.0, p20[1] + 0.3), (p13[0] + 1.0, p18[1])])
    board.track(nets["v33"], F, [pad("U2", "16"), reg(-4.4, -1.0), reg(3.2, -1.0), pad("U2", "10")])
    board.track(nets["v33"], F, [reg(3.2, -5.0), reg(7.0, -5.0), pad("C1", "1")])
    pin8 = pad("U2", "8")
    board.track(nets["gnd"], F, [pin8, (gnd_right, pin8[1]), (gnd_right, line_y["gnd"])])
    board.via(nets["gnd"], gnd_right, line_y["gnd"])
    board.track(nets["gnd"], F, [(gnd_right, pad("C1", "2")[1]), pad("C1", "2")])

    # reset beside the XIAO (pads in two columns, pin 2 left), RST and GND come down between the
    # XIAO's bottom pads
    gap = lambda a, b: (pad("U1", a)[0] + pad("U1", b)[0]) / 2
    p19, p17 = pad("U1", "19"), pad("U1", "17")
    if min(p[0] for p in board_pads(board, "SW1", "2")) > min(p[0] for p in board_pads(board, "SW1", "1")):
        board.footprints["SW1"].SetOrientationDegrees(270)
    sw1_pin2 = min(board_pads(board, "SW1", "2"), key=lambda p: p[1])
    sw1_pin1 = sorted(board_pads(board, "SW1", "1"), key=lambda p: p[1])
    board.track(nets["rst"], F, [(p17[0] + 0.53, p17[1]), (gap("5", "6"), p17[1]), (gap("5", "6"), sw1_pin2[1] - 2.0), sw1_pin2])
    board.track(nets["gnd"], F, [p13, (p13[0], oy - 5.5), (p13[0] + 1.0, oy - 4.5), (gap("6", "7"), oy - 4.5),
                                 (gap("6", "7"), sw1_pin1[0][1] - 2.0), sw1_pin1[0]])
    # battery: SW2 and the pads in the centre above the register, the battery lies right of the
    # pads over the risers. +BATT leaves the XIAO to the right on B.Cu (RST and GND cross
    # its way on F.Cu), hops to F.Cu and runs along the top edge; BAT- hangs on the GND strip line.
    sw2_pin3, sw2_pin2 = pad("SW2", "3"), pad("SW2", "2")
    bat_plus, bat_minus = pad("BAT+1", "1"), pad("BAT-1", "1")
    batt_via, batt_y = (ox + 17.5, oy + 0.5), oy - 8.0
    board.track(nets["batt"], B, [p19, (batt_via[0], p19[1]), batt_via])
    board.via(nets["batt"], *batt_via)
    board.track(nets["batt"], F, [batt_via, (batt_via[0], batt_y), (sw2_pin3[0], batt_y), sw2_pin3])
    board.track(nets["bat_sw"], F, [sw2_pin2, (sw2_pin2[0] - 1.0, sw2_pin2[1] + 1.5), (sw2_pin2[0] - 1.0, bat_plus[1] - 3.0), bat_plus])   # past the locating pin
    board.track(nets["gnd"], B, [(bat_minus[0], line_y["gnd"]), bat_minus])


def main():
    layout = json.loads((REPO / "board" / "layout.json").read_text())
    matrix = json.loads((REPO / "tools" / "matrix.json").read_text())
    board = Board(*export_netlist())
    ox, oy = ORIGIN
    outline = [(x + ox, y + oy) for x, y in layout["outline"]]
    rounded_outline(board, outline, layout["corner_radius"])
    centre_x = (layout["outline"][0][0] + layout["outline"][1][0]) / 2 + ox

    frames = {}
    half_keys = {"left": [], "right": []}
    for key in layout["keys"]:
        ref = key["ref"]
        frames[ref] = board.place(ref, "Cherry_MX_ULP_Human", key["x"] + ox, key["y"] + oy, key["rot"])
        half_keys[key["half"]].append(key)
    halves, blocks = {}, {}
    for half_name in ("left", "right"):
        keys = half_keys[half_name]
        half = route_half(board, half_name, keys, frames, matrix, centre_x, oy)
        for key in keys:
            ref = key["ref"]
            if matrix[ref]["row"] != 5:
                key_cell_tracks(board, frames[ref], ref, ref.replace("SW_L_4_", "D_L_4_"), matrix[ref]["row"])
            else:
                board.track(board.net_of(ref, "2"), pcbnew.F_Cu, [frames[ref].g(1.75, 3.65), frames[ref].g(1.0, 4.4)])
        halves[half_name] = half
        blocks[half_name] = route_block(board, half, frames, centre_x, ox, oy)
        blocks[half_name]["half"] = half
    route_electronics(board, blocks["left"], blocks["right"], centre_x, ox, oy)
    board.save()
    print(f"wrote {PCB_PATH}")


if __name__ == "__main__":
    main()
