# Agent notes: mnhTTn48 unibody

## Goal

Unibody version of the mnhTTn48 split keyboard that lies on top of a notebook keyboard.
Target notebooks: Dell XPS 13 9300 (2020) and MacBook Pro 14 (2026, M6).
Parent project: `venc0r/mnhttn` (local `~/Documents/git/github/venc0r/mnhttn`), branch `main`.

## Decisions (2026-11-21)

| Topic | Decision | Why |
|---|---|---|
| Layout | mnhTTn48 key positions per half, minus the extra inner key (SW 26 / 45) and the innermost thumb key (SW 31 / 46): 5x4+2 per side, 44 keys. Re-gret finger splay (ergogen column splay 11,-7,-4 = pinky 11 deg, ring 4 deg, rest straight). Halves splayed 20 degrees each (inward rotation like the earlier `mbpulp` try). Gap between halves is a parameter. | Keep keycaps, keymap and muscle memory. User likes the re-gret finger splay, 2 thumb keys per side are enough. With 48 keys the field was 6 mm too deep for the MBP well; with 44 it fits at 20 deg. |
| Fit target | MacBook Pro 14: usable envelope = well width x down to the trackpad top edge (280.3 x 118.6 mm), keep Touch ID, speakers and trackpad free. XPS 13: anything up to 296 x 190 mm does not overhang. | Pencil rubbing fit test 2026-11-21. User: no clearance needed above the trackpad. |
| Placement | Halves as far apart as Touch ID allows (`--gap auto` = 41.5 mm, key 1 hits Touch ID at 42). Thumbs 8 mm inward, 1 mm down in the half's frame (`--thumb-shift 8,1`), thumb 30 / 47 end exactly on the trackpad top edge. | User wants the halves outward up to Touch ID, thumbs a bit inward and down. Every extra mm of thumb travel costs 0.34 mm depth from the 20 deg rotation, the envelope has 3.8 mm total. |
| Controller | One Seeed XIAO nRF52840 BLE + one 74HC595 shift register on SPI. Electrical matrix 8 register outputs x 6 XIAO inputs = 48 keys. | 48 keys need 15 matrix pins, XIAO has 11. Same trick as `rschenk/zmk-keyboard-re-gret`. Inputs stay on MCU pins so interrupt wake works. Rejected: XIAO nRF52840 Plus (bottom pads need reflow), charlieplex (polling only). |
| PCB thickness | 2.0 mm FR-4 | JLCPCB 2-layer max is 2.0 mm (2.4 / 3.2 mm only for 12+ layers). Bending stiffness scales with t^3: 37x stiffer than 0.6 mm, 2x than 1.6 mm. |
| Underside | Flat. No bottom components, switch pins must not protrude. | Nothing may touch the notebook keys. |
| Support | Board extends past the keyboard and rests on the deck: strip above the well (hinge side) and the palm rest left and right of the trackpad, trackpad cut out. Thin pads (~1 mm) only in those rest zones, so the board hovers above the keycaps. MBP: 2 mm side overhang allowed (covers 1 mm of speaker grille). XPS: board must stay inside the chassis (296 x 190), covering its trackpad is fine. | Decided 2026-11-22 after discussing that "flat on keycaps + mat" cannot guarantee that typing force does not actuate notebook keys (ULP bottom-out 200 cN spread over a few 60 cN notebook keys). Fallback for mid-span flex: ribs in the 2.5 mm gaps between MBP key rows (the `mbpulp` idea). |
| Repo workflow | Feature branches + PRs to `main`. | User choice (parent repo commits on main directly). |
| Keycaps | Reuse mnhTTn48 keycaps, not copied here. | Identical switches and pitch. |

## Matrix plan (8 x 6)

Register outputs are the driven side. Net names follow the mnhTTn48 switch sheet, which has
the diode cathode on ROW and the switch on COL, so the register drives COL_0..7 and the XIAO
reads ROW_0..5: ZMK `col2row` with `col-gpios` on the shifter and `row-gpios` on the XIAO,
exactly the ZMK shift register example. Electrical COL_c = physical key row (c 0..3 left,
4..7 right, top to bottom), ROW_i = finger column (0 pinky .. 4 inner), ROW_5 = thumbs with
the outer thumb on COL_0 / COL_4 and the inner one on COL_1 / COL_5. Per half 4 x 6 = 24
positions for 22 keys. Full table: `tools/matrix.json`.

| XIAO pin | Use |
|---|---|
| D0-D5 | 6 matrix inputs, `GPIO_ACTIVE_HIGH \| GPIO_PULL_DOWN`, wakeup-source |
| D8 | SPI SCK |
| D10 | SPI MOSI |
| D9 | SPI CS for the 595 (MISO unused) |
| D6, D7 | spare |

ZMK: `zmk,gpio-595` on `&xiao_spi`, `ngpios = <8>`, `spi-max-frequency = <200000>`, `CONFIG_SPI=y`.
Docs: https://zmk.dev/docs/development/hardware-integration/shift-registers

## Phases

0. **Measure** (user, calipers): keyboard well width/depth and keycap height above deck on both
   notebooks, touchpad top edge distance, hinge clearance. ULP switch pin length below the body
   (drawing TSM0058 is not public). 1:1 paper print of the layout on both notebooks.
1. **Repo scaffold** (done): tooling, footprints, this file.
2. **Layout generator** `tools/` (done 2026-11-21): `extract_keys.py` pulls the 48 switch positions
   out of the parent board into `keys-mnhttn48.json`, `layout.py --splay --gap --column-splay`
   drops the keys in `--drop`, fans the finger columns, rotates each half around its inner top
   corner (corner = innermost column top key + half a pitch), centres the field in the notebook
   envelope from `tools/notebooks.json` and writes `docs/images/layout.svg` (1:1, mm units, with
   the well, envelope and keep-outs) and `board/layout.json`. 44 keys at 20 deg / gap auto 41.5 /
   11,-7,-4 / thumbs 8,1: key cell extent 261.8 x 118.5 mm, 9.2 mm to the well sides, top at the
   well edge, bottom 3.4 mm below the well on the trackpad top edge. (Earlier: gap 12, thumbs 0,0:
   232.3 x 114.8 mm.)
   Conventions: output coordinates are board coordinates (y down) with the origin at the well's
   top left corner, `rot` is the KiCad footprint rotation (CCW positive), so SVG draws with
   `rotate(-rot)`. Verified by rendering splay 0 next to `kicad-cli pcb export svg` of the parent
   board. Earlier 48-key numbers: 257.8 x 121.1 mm at 20 deg, 248.0 x 113.7 mm at 10 deg.
   Column splay reproduces ergogen (`src/points.js`): columns are laid out flat, then column i gets
   the rotations of columns 1..i applied in order, each around the flat pivot of its own column
   (first column: bottom key centre, others: `origin` = bottom outer corner of the bottom key).
   Each half has 6 columns (5 finger + the extra inner key) and 3 thumbs; thumbs and the extra
   key translate with the inner column (net column angle 0 after 11-7-4).
3. **Schematic** (done 2026-11-22): `tools/gen_schematic.py` writes `board/mnhttn48-unibody.kicad_sch`
   (root, A3), `board/switch.kicad_sch` (mnhTTn48 switch sub-sheet, instances regenerated) and
   `board/mnhttn48-unibody.kicad_pro` (mnhTTn48 project settings, sheets list dropped). Symbols
   come from `tools/sch_symbols/` (copied out of the parent schematic and the KiCad 10 libs),
   everything is wired with local labels on 2.54 mm stubs, UUIDs are uuid5 of element names.
   The matrix assignment is derived from the parent key coordinates and `layout.json`'s dropped
   list, written to `tools/matrix.json`. ERC via `kicad-cli sch erc --severity-all`: 0 errors,
   6 warnings (XIAO GND pins 13/18/20 are all power_out on one net, project ERC pin map relaxed
   to warning; embedded copies of SW_SPDT / D_Small / Cherry symbol differ from the current libs;
   library "mcu" is not in sym-lib-table, the symbol is embedded). Netlist checked with
   `kicad-cli sch export netlist --format kicadxml`.
   Extras vs the parent: 74HC595 U2 (SER<-MOSI D10, SRCLK<-SCK D8, RCLK<-CS D9, ~SRCLR and ~OE
   tied to 3V3 / GND, QA..QH = COL_0..7, QH' open), C1 100n 0603 on 3V3, battery minus on GND
   (parent had a separate -BATT net on XIAO pin 20).
4. **Board** (done 2026-11-22): `tools/gen_pcb.py` runs under KiCad's bundled Python
   (`/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3 -I`,
   pcbnew 10.0.8) and writes `board/mnhttn48-unibody.kicad_pcb` from `layout.json`, `matrix.json`
   and the schematic netlist (`kicad-cli sch export netlist --format kicadxml`, gitignored).
   `tools/drc.sh [details]` regenerates and runs `kicad-cli pcb drc --severity-all
   --all-track-errors`: 0 violations, 0 unconnected, `--schematic-parity` clean. Routing scheme
   (documented in the script header): diodes in two central blocks between the halves (user:
   not beside the switches, like the mnhTTn48), anode bands on B.Cu through the row gaps with
   staircase lanes at the splay steps, F.Cu bridges over the COL lanes in the inner key, B.Cu
   crossbars into the blocks, F.Cu cathode buses down to a B.Cu bottom band that runs into the
   left leg and up the left margin into D0..D5, COL buses F.Cu with B.Cu lanes to the register,
   XIAO top left, register in the centre, power switch and battery in the centre above the register. 2.0 mm,
   2 layers, no zones yet, outline with 3 mm corner radius from `layout.json`, origin offset
   (8.35, 20) mm so the board sits centred on the A4 landscape sheet (6.35 mm side, 10 mm top/bottom
   margin) and prints 1:1 from KiCad. Not yet: GND zones, silkscreen labels.
5. **Firmware**: shield `mnhttn48_unibody` in `zmk-config/`, single build target, keymap from mnhTTn48.
6. **Docs**: README, build guide delta (solder pins from the top only, 595 placement), mat spec.

## Reference numbers

mnhTTn48 board (`mnhttn.kicad_pcb`): panel 258 x 106 mm, one half main block ~112 x 88 mm,
thumb cluster adds 18 mm below. Switch footprint `Cherry_MX_ULP_Human`: 4 SMD contact pads
+ 4 THT locating pins, drill 1.016 mm, soldered from the top.

Cherry MX ULP (datasheet MX6C-T3NB): 3.9 mm total height, 13.08 x 13.6 mm, 1.8 mm travel.
Design guideline VR-00103: silicone dampening mat shore A40-60, 0.5 mm, cutout 13.4 x 13.9 mm
per switch. Keycap bump 0.38 mm recommended. No pin length given.

Notebooks (`tools/notebooks.json`, origin = top left corner of the keyboard well, y down):
- MacBook Pro 14 M6 (312.6 x 221.2 x 15.5 mm chassis). Measured 2026-11-21 from a pencil rubbing
  of the deck on the 1:1 print, scanned at 600 dpi (23.62 px/mm, print scale confirmed 100 %):
  well 280.3 x 115.2 mm, chassis x -16.1..296.4; Touch ID x 260.6-277.1 y 3.2-17.2; speakers
  beside the well from y 0 (key top edge) to y 109.7 (user's mark); trackpad top edge y 118.6,
  x 74.7-205.7 from the rubbing; measured on the MacBook it is 130 mm wide (user, 2026-11-22),
  now x 75.15-205.15, centred on the well. Scan mapping used: svg_x = 5 + (scan_y - 283) / 23.62, svg_y = 5 + (4560 - scan_x)
  / 23.62 (print was landscape on A4 portrait, dashed key extent box as registration).
- XPS 13 9300: 295.65 mm wide, keyboard edge to edge, key pitch 19.05 x 18.05 mm. User limit for
  a board that does not overhang: 296 x 190 mm. Not binding for a ~236 x 120 mm board.
- The `mbpulp` try's MBP estimates (keycap 16.2 x 16, pitch 19.0 x 18.5) are unverified.

## KiCad on this Mac (carried over from mnhTTn48)

- KiCad 10 from the Homebrew cask, `kicad-cli` on PATH. No GUI control from the agent, edit
  `.kicad_pcb` / `.kicad_mod` by script and verify with `kicad-cli`.
- `kicad-cli` cannot create a project or update footprints from the library. Patch embedded
  footprints by script, let the `lib_footprint_mismatch` DRC check prove board == library.
- Every `kicad-cli` run rewrites `*.kicad_prl`. Revert it before committing.
- `board/Makefile` grouped targets need GNU make >= 4.3; installed make is 3.81, `check` targets work.
- `board/check.sh generate <dir>` / `compare <a> <b>`: DRC JSON, gerbers, drills, position file,
  600 dpi rasters. Acceptance: everything PASS except the deltas the change is supposed to make.
- Track moves need a zone refill afterwards (`kicad-cli pcb drc --refill-zones --save-board`).
- `mnhttn48-unibody.kicad_dru` accepts the ULP pads and XIAO pads straddling their pocket edges.
- Footprint library nickname stays `mnhttn` (footprints and the dru rule reference `mnhttn:`).
- Quick SVG preview without a browser: `qlmanage -t -s 1600 -o <dir> file.svg` writes `file.svg.png`
  (square thumbnail, crops wide pages). For the board: `kicad-cli pcb export svg --layers
  F.Cu,B.Cu,Edge.Cuts --page-size-mode 2 --exclude-drawing-sheet` then `magick -density 220 x.svg
  -background white -flatten x.png` (ImageMagick renders SVG itself, PDF would need ghostscript).
- pcbnew API lessons: pad angles in the file are absolute (frame rotation added), `FootprintLoad`
  gives a library footprint, set `SetFPID(LIB_ID("mnhttn", name))` for the parity check. KiCad does
  not treat two pads with the same number as connected unless copper joins them (the PushSwitch
  pins get a bridge track). Netlist names with `/` show up as `{slash}` in the parity report, so
  pads on `unconnected-*` nets are left without a net. The XIAO footprint's oval pads carry a
  drill offset of 0.475 mm, their copper extends to |x| 9.47 mm, not 9.0.
- Matrix: ROW_0..5 sit on D0..D5 (XIAO pins 1..6), COL_0..7 on the 595 outputs QA..QH. The ZMK
  row-gpios / col-gpios lists follow it.
- Electronics placement (user, 2026-11-22): the XIAO sits in the top left corner with the USB-C
  pointing left out of the board, so it can be charged while typing (pointing at the hinge would
  push the plug into the screen). XIAO centre at well (8, 0.5), rotation 90: the castellated pad
  rows become the top row (5V, GND, 3V3, MOSI, CS, SCK, D7, left to right) and the bottom row
  (D0..D6). Reset switch below it (well (13, 20)). Power switch SW2, battery pads and the battery
  (size still open, no outline drawn) sit in the centre above the 74HC595 (user, 2026-11-22: there is
  room there): SW2 at well (centre - 24, 0.8), pins up, locating pins just below the GND strip
  line (NPTH holes need 0.725 mm to a line), pads at (centre - 22 / - 16, 8), battery
  right of the pads over the register risers. The 74HC595 stays in the
  centre.
- Routing lessons (central diode scheme, 2026-11-22): vias need 1.0 mm pitch and 0.725 mm to the
  next track centreline (clearance 0.2, via 0.8, track 0.25), hole clearance 0.575. Tracks that
  share a gap must be nested: the line on the lowest level takes the via nearest the block /
  turns last, otherwise it passes under the other vias (crossbars, band -> margin turn). Between
  splayed cells the band tracks need a staircase in the outer cell (the next cell sits 1-2.5 mm
  higher or lower), straight segments cross. Tracks run parallel to the switch inside a cell and
  horizontally between cells (user, 2026-11-22); a ULP cell is free on B.Cu except the pins at
  local x -1..3, y 0.4..4.2 (housing pads are F.Cu only), so its top strip carries the thumb lines.
  `Frame.ly_at` / `lx_at` find where a local line reaches a global y. Thumb COL lines use
  `point_at_y` (point of a local vertical at a given y of another frame) instead of fixed cell
  corners, the thumbs are rotated 8 deg against the inner column.
  The top strip only carries GND, 3V3, MOSI, CS, SCK (B.Cu at
  0.75 mm pitch, well y -1.4 .. -4.4). +BATT, RST and the SW1 GND leave the XIAO on F.Cu
  through the gaps between the bottom-row pads (D2/D3, D4/D5, D5/D6).
- DRC with `--schematic-parity` takes ~20 s and needs the `.kicad_sch` next to the board.
- Printing (user, 2026-11-22): macOS prints an SVG about 1 % small (100 mm bar measured 99 mm) and
  offers no scale above 100 %. A print of the PDF measured 103 mm although the PDF is exact
  (rendered at 10 px/mm both bars are 1000 px + line caps): borderless paper or "fill" scaling in
  the print dialog. The drawing now has a vertical ruler too and says "A4 (not borderless)". With
  plain A4 at 100 % the user still measured 101 mm: the old bars had round caps (+0.4 mm end to
  end), now butt caps and 0.1 mm ticks every 10 mm. What is left is printer tolerance (about 1 %,
  often only in the paper feed direction); compensate with the scale field below 100 % if both
  rulers agree.
  `layout.py` therefore also writes `docs/images/layout.pdf` through
  `tools/svg_to_pdf.py` (own SVG subset, Courier text, `/PrintScaling /None`). No SVG->PDF tool
  (rsvg, inkscape, gs) is installed, ImageMagick cannot read PDFs without gs; preview a PDF with
  `qlmanage -t -s 1600 -o <dir> file.pdf`.
- `cp`, `mv`, `rm` are interactive aliases in this shell, use `command cp -f` etc. in scripts.
- Run the python tools with `python3 -I` (no inline python per user rules, script files are fine).

## Open items

- Phase 0 measurements.
- Second paper test with the 44-key print (gap 41.5, thumbs 8,1, outline).
- Board outline (`board` block in `tools/notebooks.json`, polygon in `board/layout.json`):
  x -2..282.3, top rest strip 10 mm (MBP deck between well and hinge is 12 mm, 2 mm kept free;
  XPS has 7 mm but the board sits wherever it fits there), bottom edge at y 180 so the board
  uses the full XPS depth of 190 mm (user: an edge under the palms would be annoying), trackpad
  notch x 74.65-205.65 (trackpad + `trackpad_clearance` 0.5 per side) open from y 118.6 to the
  bottom edge, so the board is a U with two palm
  rest legs. 284.3 x 190.0 mm, corner radius 3 mm to be applied in Edge.Cuts.
  Still to measure on both notebooks: keycap top vs deck (pad thickness follows from it), MBP
  palm rest depth available beside the trackpad.
- Thumb keys 30 / 47 sit on the trackpad notch edge with no rim (switch body still 2 mm away).
- Schematic files are KiCad 8 format (version 20231120) like the parent; KiCad 10 reads them
  and will rewrite them on save. `kicad-cli sch erc` creates `board/*.kicad_prl`, gitignored.
- Board: GND zones, silkscreen labels. Print check: `docs/images/layout.pdf` (A4, board outline
  centred) and the board itself (`kicad-cli pcb export pdf --layers Edge.Cuts,F.Cu`, A4 sheet).
- Battery placement (top side or pocket), must keep the underside flat.
- Whether the mat alone keeps notebook keys from actuating under ~100 g of board.
