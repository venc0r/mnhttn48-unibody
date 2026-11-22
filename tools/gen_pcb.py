#!/usr/bin/env python3
"""
PCB generator for the mnhTTn48 unibody. Needs KiCad's bundled Python (pcbnew module):

    /Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3 -I tools/gen_pcb.py

Reads board/layout.json (keys in well coordinates, board outline), tools/matrix.json (electrical
matrix) and the schematic netlist (exported with kicad-cli), writes board/mnhttn48-unibody.kicad_pcb.
tools/drc.sh runs this and the DRC.

Routing scheme (key frame = switch footprint coordinates, y down, KiCad rotation CCW positive;
well coordinates = board/layout.json, board coordinates = well + ORIGIN). In a switch cell B.Cu
is free except the pins (local x -1..3, y 0.4..4.2); F.Cu also carries the four housing pads, so
F.Cu tracks keep to the row gap (local y 6.3..10.7) or to x beyond +-7.3. One via per key: the
finger anodes stay on F.Cu from the switch to the diode, every cathode drops onto B.Cu.
  COL bus    B.Cu at local y -2 through the keys of a physical row (above the pins), stub from
             pad 2's upper annulus (2.165, 0.75). It ends on its lane: B.Cu verticals at x
             10..13 in the frame of the inner column's top key, which turn towards the centre
             where they reach the height of their via beside the shift register (REGISTER_VIAS,
             the lane nearest the centre turns lowest). Lanes 0/1 reach down to the thumbs, so
             rows 1-3 cross them on an F.Cu bridge (via at x 9.2 beside the inner key, via on
             the lane); row 0 needs none.
             Thumb keys reach the lane ends of rows 0/1 on F.Cu along their cell edges: up the
             inner edge, the inner thumb then along its top strip to the lane end at its outer
             top corner.
  anode band Each key's switch pad 1 leaves on F.Cu to the row gap below the switch (local y
             9.8 - 0.75 c, c = finger column 0 pinky .. 4 inner, the pinky lowest) and runs
             inward through the cells of its row. Where the next cell sits higher or lower
             (column splay) every passing track climbs on its own staircase lane at the inner
             edge of the outer cell (local x 7.4 + 0.5 n, right of the housing pads), ordered so
             nothing crosses. Past the inner key track c turns at local x 9.5 + 1.2 (4 - c) to
             global horizontal and runs straight into its diode column; the top track turns
             first, so the turns stack the lines 1.1 mm apart with the innermost column on top.
  diodes     One block per half in the centre, four mini rows of five SOD-123 (column c at
             x centre -/+ (11.3 - 1.9 c), vertical, anode on top, fed on F.Cu from the line
             above it) at the height of their key row, plus the two thumb diodes in an outer
             column at centre -/+ 13.2. Thumb anodes stay on B.Cu, because the row 3 lines leave
             the inner key right above the thumbs on F.Cu: parallel to the switch inside the
             cell, horizontal from the inner edge into the outer column, below the row 3 lines
             and the lane ends, one via at the diode. Cathodes: F.Cu stub to a via 1.6 mm below
             the pad, B.Cu bus (one per net, x_c + 0.95) down to the bottom band.
  ROW nets   bottom band on B.Cu (well y 113.6 + 0.8 (5 - row), above the trackpad notch edge)
             from both blocks leftwards under the thumbs into the left palm rest leg, up the
             left margin (well x 1 + row) and from below into the XIAO's bottom pad row D0..D5.
             Right block lines start at their bus, a line further right lies lower, so they meet
             without crossings; only the thumbs' bus (outer column) hops over the block on F.Cu.
             Under the left block every bus but the thumbs' (top line) hops over the lines above
             its own on F.Cu.
  XIAO       top left corner, rotated 90 so the USB-C points left out of the board. Top pad row
             (5V, GND, 3V3, MOSI, CS, SCK, D7) is entered from below by the strip lines (B.Cu at
             LINE_Y). SW1 (reset, pads in two columns) sits below it, RST and the SW1 GND leave
             the XIAO between its bottom pads. SW2 (power), the battery pads and the battery sit
             in the centre above the register; +BATT leaves the
             XIAO on B.Cu, hops to F.Cu and runs as the top strip line (LINE_Y, 0.75 above SCK),
             BAT- hangs on the GND line.
  register   74HC595 rotated 90 (pins 1..8 bottom row, 9..16 top row) at well y 26 in the centre,
             risers on F.Cu straight up from the pins to the strip lines. 3V3 is taken at VCC
             (pin 16) and GND drops left of it, so the strip vias climb left to right (GND, 3V3,
             MOSI, CS, SCK). SRCLR hangs on VCC by a tie under the chip and feeds C1 above the
             pin row. GND runs at C1's height on B.Cu past ~OE (pin 13) to C1's GND pad, a short
             riser right of the chip joins C1 and GND pin 8.
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
BOARD_THICKNESS = 1.6

DIODE_FOOTPRINT = "Diode_SOD123"
COL_Y = -2.0                   # COL bus on B.Cu in the key frame, above the pins (B.Cu is free there)
COL_PAD = (2.165, 0.75)        # COL stub enters pad 2's upper annulus, above its pocket
BAND_Y0, BAND_STEP = 9.8, 0.75 # anode band levels on F.Cu, in the row gap below the housing pads, pinky lowest
CELL_W, CELL_H = 18.0, 17.0
LANE_X = {0: 10.0, 1: 11.0, 2: 12.0, 3: 13.0}
LANE_BOTTOM_Y = {0: 62.0, 1: 62.0, 2: 2 * CELL_H + COL_Y, 3: 3 * CELL_H + COL_Y}
COL_BRIDGE_X = 9.2             # rows 1-3: via beside the inner key, F.Cu bridge over the lanes
COL_STEP_X = 8.5               # COL bus steps between splayed cells inside the next cell, this far from its centre
TURN_X0, TURN_STEP = 9.5, 1.2  # band track c turns to global horizontal at inner key x TURN_X0 + TURN_STEP (4 - c)
CATHODE_VIA_DY = 1.6           # cathode via below the cathode pad
BAND_HOP_DY = 0.8              # buses that cross bottom band lines hop on F.Cu from this far above the band
THUMB_PITCH = 7.0              # thumb diodes in the outer block column
THUMB_EXIT_LY = -8.0           # the inner thumb's anode crosses its inner edge no higher than this (local y)
THUMB_COL_TOP_LY = -8.0        # inner thumb COL along the top strip of its cell (F.Cu is free above the housing pads)
STEP_LANE_X0, STEP_LANE_PITCH = 7.4, 0.5    # staircase lanes between two cells of a row, right of the housing pads, before the next cell
LINE_Y = {"gnd": -1.4, "v33": -2.15, "mosi": -2.9, "cs": -3.65, "sck": -4.4, "batt": -5.15}   # strip lines, well y (+BATT on F.Cu)
XIAO_POS, XIAO_ROT = (8.0, 0.5), 90
REG_Y = 26.0                   # well y of the shift register
REGISTER_VIAS = {              # COL net -> (via offset from the register centre, pin); QA (COL_0) is on the top row
    0: ((-3.175, -6.5), "15"),
    1: ((-4.4, 6.5), "1"), 2: ((-3.2, 7.5), "2"), 3: ((-1.9, 8.5), "3"),
    4: ((-0.6, 5.5), "4"), 5: ((0.6, 6.5), "5"), 6: ((1.9, 7.5), "6"), 7: ((3.2, 8.5), "7"),
}
BLOCK_DX0, BLOCK_PITCH = 12.9, 2.3      # diode columns at centre -/+ (BLOCK_DX0 - BLOCK_PITCH c)
BUS_DX = 1.15                  # cathode bus offset from the diode column, towards the centre
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


def turn_x(column):
    return TURN_X0 + TURN_STEP * (4 - column)


def key_cell_tracks(board, frame, sw, diode, column):
    """COL stub on B.Cu up to the bus, the anode's drop to its band level on F.Cu."""
    board.track(board.net_of(sw, "2"), pcbnew.B_Cu, [frame.g(*COL_PAD), frame.g(COL_PAD[0], COL_Y)])
    board.track(board.net_of(diode, "2"), pcbnew.F_Cu, [frame.g(0.41, 3.65), frame.g(-0.6, 4.7), frame.g(-0.6, band_y(column))])


def route_half(board, half_name, keys, frames, matrix, centre_x, oy):
    """COL buses, lanes and anode bands of one half. Returns where each band track turns towards the block."""
    sign = 1 if half_name == "left" else -1
    F, B = pcbnew.F_Cu, pcbnew.B_Cu
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
    out = {"band_end": {}, "thumbs": thumbs, "sign": sign, "inner": inner, "rows": rows}

    # COL buses on B.Cu along the rows, above the pins. Row 0 runs straight into its lane, rows 1-3
    # cross the lanes of rows 0/1 (they reach down to the thumbs) on an F.Cu bridge.
    for col, members in rows.items():
        key_row = col % 4
        net = col_net[col]
        points = [frames[members[0][1]].g(COL_PAD[0], COL_Y)]
        for index, (_, ref) in enumerate(members):
            if index < len(members) - 1:
                # step to the next cell's bus height inside that cell, parallel to its side edge
                outer, nxt = frames[ref], frames[members[index + 1][1]]
                edge_point = outer.g(sign * CELL_W / 2, COL_Y)
                step_x = -sign * COL_STEP_X
                points += [edge_point, nxt.g(step_x, nxt.local(*edge_point)[1]), nxt.g(step_x, COL_Y)]
        lane_point = inner.g(lane_x[key_row], key_row * CELL_H + COL_Y)
        if key_row == 0:
            board.track(net, B, points + [lane_point])
        else:
            bridge = inner.g(sign * COL_BRIDGE_X, key_row * CELL_H + COL_Y)
            board.track(net, B, points + [bridge])
            board.via(net, *bridge)
            board.track(net, F, [bridge, lane_point])
            board.via(net, *lane_point)

    # lanes on B.Cu up the inner column; each turns towards the register where it reaches its via's
    # height (the lane nearest the centre lowest, so the turns nest), COL_0 runs on above the chip
    first_col = 0 if sign == 1 else 4
    for key_row, x in lane_x.items():
        (dx, dy), _ = REGISTER_VIAS[first_col + key_row]
        via = (centre_x + dx, oy + REG_Y + dy)
        turn = inner.g(x, inner.ly_at(x, via[1]))
        board.track(col_net[first_col + key_row], B, [inner.g(x, LANE_BOTTOM_Y[key_row]), turn, via])
    out["lane_ends"] = [inner.g(lane_x[r], LANE_BOTTOM_Y[r]) for r in (0, 1)]

    # thumbs: COL on F.Cu along the cell edges to the lane end (via there): up the inner edge, and
    # if the lane end lies beyond the outer side (inner thumb), along the top strip to it
    for col, ref in thumbs:
        f = frames[ref]
        key_row = col % 4
        lane_end = inner.g(lane_x[key_row], LANE_BOTTOM_Y[key_row])
        path = [f.g(1.0, 4.4), f.g(1.0, 7.0), f.g(sign * CELL_W / 2, 7.0)]
        if f.local(*lane_end)[0] * sign < 0:
            path += [f.g(sign * CELL_W / 2, THUMB_COL_TOP_LY), f.g(-sign * CELL_W / 2, THUMB_COL_TOP_LY)]
        else:
            path.append(point_at_y(f, sign * CELL_W / 2, inner, LANE_BOTTOM_Y[key_row] + 0.45, ly0=7.0))
        board.track(col_net[col], F, path + [lane_end])
        board.via(col_net[col], *lane_end)

    # anode bands: inward through the row on F.Cu. Between two cells every passing track climbs or
    # descends on its own staircase lane in the outer cell (the next cell sits higher or lower),
    # ordered so nothing crosses. Past the inner key each track turns towards the block at its
    # band end, the top one first, so the turns stack the tracks without crossings.
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
                step_x = sign * (STEP_LANE_X0 + STEP_LANE_PITCH * lane)
                paths[c] += [outer.g(step_x, band_y(c)), outer.g(step_x, band_y(c) + climbs[c]), targets[c]]
        for column, (_, ref) in enumerate(members):
            end = inner_key.g(sign * turn_x(column), band_y(column))
            board.track(anode_net(ref), F, paths[column] + [end])
            out["band_end"][(key_row, column)] = end
    return out


# ---------------------------------------------------------------- diode blocks


def route_block(board, half, frames, cx, ox, oy):
    """Diode block of one half: mini rows at the key rows' heights fed on F.Cu, the thumbs fed on
    B.Cu in the outer column, every cathode through a via onto a B.Cu bus down to the bottom band."""
    sign = half["sign"]
    F, B = pcbnew.F_Cu, pcbnew.B_Cu
    diode_x = {c: cx - sign * (BLOCK_DX0 - BLOCK_PITCH * c) for c in range(5)}
    diode_x[5] = cx - sign * (BLOCK_DX0 + BLOCK_PITCH)
    bus_x = {c: diode_x[c] + sign * BUS_DX for c in range(6)}
    cathode_vias = {c: [] for c in range(6)}

    def place_diode(ref, column, level):
        """Diode below `level` with the anode on top, fed on F.Cu from `level`, cathode via below it."""
        x = diode_x[column]
        board.place(ref, DIODE_FOOTPRINT, x, level + 3.85, 90, hide_reference=True)
        board.track(board.net_of(ref, "2"), F, [(x, level), board.pad_xy(ref, "2")])
        cathode = board.pad_xy(ref, "1")
        via = (bus_x[column], cathode[1] + CATHODE_VIA_DY)
        board.track(board.net_of(ref, "1"), F, [cathode, via])
        board.via(board.net_of(ref, "1"), *via)
        cathode_vias[column].append(via)

    # rows: every band track runs horizontally from its band end into its column
    lowest_level = 0.0
    for col, members in half["rows"].items():
        key_row = col % 4
        for column, (_, ref) in enumerate(members):
            diode = ref.replace("SW_L_4_", "D_L_4_")
            end = half["band_end"][(key_row, column)]
            board.track(board.net_of(diode, "2"), F, [end, (diode_x[column], end[1])])
            place_diode(diode, column, end[1])
            lowest_level = max(lowest_level, end[1])

    # thumbs: anodes on B.Cu, because the row 3 tracks leave the inner key above the thumbs on F.Cu.
    # Parallel to the switch inside the cell, horizontal from its inner edge into the outer column,
    # below the row 3 tracks and the lane ends; a via at the diode.
    (_, outer_ref), (_, inner_ref) = half["thumbs"]
    edge = sign * CELL_W / 2
    level_outer = max(lowest_level, max(y for _, y in half["lane_ends"])) + 0.8
    level_inner = max(level_outer + THUMB_PITCH, frames[inner_ref].g(edge, THUMB_EXIT_LY)[1])
    for ref, level in ((outer_ref, level_outer), (inner_ref, level_inner)):
        f = frames[ref]
        ly = f.ly_at(edge, level)
        diode = ref.replace("SW_L_4_", "D_L_4_")
        net = board.net_of(diode, "2")
        board.track(net, B, [f.g(0.41, 3.65), f.g(-0.6, 4.7), f.g(-3.0, 4.7), f.g(-3.0, ly), f.g(edge, ly),
                             (diode_x[5], level)])
        board.via(net, diode_x[5], level)
        place_diode(diode, 5, level)

    # cathode buses on B.Cu down to the bottom band, whose lines run leftwards under both blocks.
    # In the right block a line that starts further right lies lower, so its buses meet their lines
    # without crossings; only the thumbs' bus in the outer column hops over the block on F.Cu. In
    # the left block every bus but the thumbs' (top line) hops over the lines above its own.
    right_block = sign == -1
    band_top = oy + BAND_WELL_Y
    hop_y = band_top - BAND_HOP_DY
    out = {"line_start_x": {}}
    for column in range(6):
        net = board.net_of("U1", str(column + 1))
        x = bus_x[column]
        top = min(y for _, y in cathode_vias[column])
        line_y = band_top + BAND_PITCH * (5 - column)
        if column == 5 and right_block:
            start = cx + 1.0
            board.track(net, B, [(x, top), (x, hop_y)])
            board.via(net, x, hop_y)
            board.track(net, F, [(x, hop_y), (start, hop_y)])
            board.via(net, start, hop_y)
            board.track(net, B, [(start, hop_y), (start, line_y)])
            out["line_start_x"][column] = start
        elif column == 5 or right_block:
            board.track(net, B, [(x, top), (x, line_y)])
            out["line_start_x"][column] = x
        else:
            board.track(net, B, [(x, top), (x, hop_y)])
            board.via(net, x, hop_y)
            board.track(net, F, [(x, hop_y), (x, line_y)])
            board.via(net, x, line_y)
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
    board.place("C1", "C_0603_1608Metric", cx + 6.5, oy + REG_Y - 8.0, 0)   # above the pin row, clear of the GND riser
    board.place("SW1", "PushSwitch", *w(13.0, 20.0), 90)
    board.place("SW2", "MSK12C02", cx - 24.0, oy + 0.8, 90)   # pins up, locating pins just below the GND line
    board.place("BAT+1", "BatteryPad", cx - 22.0, oy + 8.0, 0)
    board.place("BAT-1", "BatteryPad", cx - 16.0, oy + 8.0, 0)
    for ref in ("BAT+1", "BAT-1"):         # JLCPCB prints silkscreen text from 1.0 mm height, 0.15 mm stroke
        label = board.footprints[ref].Value()
        label.SetTextSize(vec(1.0, 1.0))
        label.SetTextThickness(mm(0.15))
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
        board.track(net, B, [(right_block["line_start_x"][row], band), (margin_x, band),
                             (margin_x, oy + PAD_ENTRY_Y[row]), (target[0], oy + PAD_ENTRY_Y[row]), target])

    # COL lanes end in vias beside the shift register, F.Cu straight into the pads
    for (dx, dy), number in REGISTER_VIAS.values():
        net = board.net_of("U2", number)
        board.via(net, *reg(dx, dy))
        board.track(net, F, [reg(dx, dy), pad("U2", number)])

    # SPI, 3V3 and GND lines from the XIAO's top row (entered from below) to the register's risers.
    # Each riser rises straight from its pin; with 3V3 taken at pin 16 (pin 10 hangs on the tie under
    # the chip) and GND dropping left of it, the vias climb from left to right in the lines' order
    # (GND, 3V3, MOSI, CS, SCK). GND comes down to C1's height and runs on B.Cu past ~OE (pin 13)
    # to C1's GND pad; a short riser right of the chip joins C1 and GND pin 8.
    riser_pin = {"v33": "16", "mosi": "14", "cs": "12", "sck": "11"}
    gnd_right = cx + 9.275
    gnd_drop = (pad("U2", "16")[0] - 1.25, line_y["gnd"])
    for name, number in (("gnd", "13"), ("v33", "12"), ("mosi", "11"), ("cs", "10"), ("sck", "9")):
        px, py = pad("U1", number)
        if name == "gnd":
            start = (px + 1.0, line_y[name])
            board.track(nets[name], B, [start, (start[0], py + 2.0), (px, py + 1.2), (px, py)])
            board.track(nets[name], B, [start, gnd_drop])
            continue
        top = pad("U2", riser_pin[name])
        board.track(nets[name], B, [(px, py), (px, line_y[name]), (top[0], line_y[name])])
        board.track(nets[name], F, [top, (top[0], line_y[name])])
        board.via(nets[name], top[0], line_y[name])
    p13, p18, p20 = pad("U1", "13"), pad("U1", "18"), pad("U1", "20")
    board.track(nets["gnd"], B, [(p18[0] + 0.53, p18[1]), (p13[0] + 1.0, p18[1]), (p13[0] + 1.0, p13[1] + 2.0)])
    board.track(nets["gnd"], B, [(p20[0] - 0.58, p20[1] + 0.3), (p13[0] + 1.0, p20[1] + 0.3), (p13[0] + 1.0, p18[1])])
    board.track(nets["v33"], F, [pad("U2", "16"), reg(-4.4, -1.0), reg(3.2, -1.0), pad("U2", "10")])
    pin10, c1_v33, c1_gnd = pad("U2", "10"), pad("C1", "1"), pad("C1", "2")
    v33_y = c1_v33[1] + 1.6        # below the GND line that runs at C1 height on B.Cu
    board.track(nets["v33"], F, [pin10, (pin10[0], v33_y), (c1_v33[0], v33_y), c1_v33])
    pin8 = pad("U2", "8")
    board.track(nets["gnd"], F, [pin8, (gnd_right, pin8[1]), (gnd_right, c1_gnd[1]), c1_gnd])
    gnd_down = (gnd_drop[0], c1_gnd[1])
    oe_pin = pad("U2", "13")
    oe_via, c1_via = (oe_pin[0], c1_gnd[1]), ((c1_gnd[0] + gnd_right) / 2, c1_gnd[1])
    board.via(nets["gnd"], *gnd_drop)
    board.track(nets["gnd"], F, [gnd_drop, gnd_down])
    board.track(nets["gnd"], F, [oe_pin, oe_via])
    for point in (gnd_down, oe_via, c1_via):
        board.via(nets["gnd"], *point)
    board.track(nets["gnd"], B, [gnd_down, oe_via, c1_via])

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
    # its way on F.Cu), hops to F.Cu and runs as the top strip line; BAT- hangs on the GND strip line.
    sw2_pin3, sw2_pin2 = pad("SW2", "3"), pad("SW2", "2")
    bat_plus, bat_minus = pad("BAT+1", "1"), pad("BAT-1", "1")
    batt_via = (ox + 17.5, oy + 0.5)
    board.track(nets["batt"], B, [p19, (batt_via[0], p19[1]), batt_via])
    board.via(nets["batt"], *batt_via)
    board.track(nets["batt"], F, [batt_via, (batt_via[0], line_y["batt"]), (sw2_pin3[0], line_y["batt"]), sw2_pin3])
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
