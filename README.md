# mnhTTn48 unibody

Unibody variant of the [mnhTTn48](https://github.com/venc0r/mnhttn) split keyboard,
made to sit on top of a notebook keyboard (Dell XPS 13 9300, MacBook Pro 14 2026).

* mnhTTn48 key positions, reduced to 5x4+2 per side (44 keys), Cherry MX ULP switches, mnhTTn48 keycaps
* Both halves on one PCB, 20 degree splay per half, re-gret style finger splay (pinky 11, ring 4)
* Fits the MacBook Pro 14 keyboard well, clear of Touch ID, speakers and trackpad
* One Seeed XIAO nRF52840 BLE + 74HC595 shift register, 8x6 matrix, ZMK
* 1.6 mm PCB with a flat underside, rests on the deck above the keyboard and on the palm rest
  beside the trackpad, so the notebook keys are never touched

Status: PCB (1.6 mm) and parts ordered 2026-11-22, ZMK shield written but not built yet, see [agent.md](agent.md).

## Layout
mnhTTn48 key positions are the source of truth (`tools/keys-mnhttn48.json`, extracted from the
parent board). The generator drops the extra inner key and the innermost thumb key of each
half, fans the finger columns like ergogen does for the
[re-gret](https://github.com/rschenk/re-gret), rotates each half inward around its inner top
corner, centres the result in the notebook's keyboard well (`tools/notebooks.json`) and writes
a 1:1 print for the paper fit test plus the key positions for the board:

```sh
tools/extract_keys.py ../mnhttn/board/mnhttn.kicad_pcb        # only after the parent layout changed
tools/layout.py                                               # docs/images/layout.svg, board/layout.json
tools/layout.py --splay 20 --gap auto --column-splay 11,-7,-4 --thumb-shift 8,1   # the defaults
tools/layout.py --notebook xps13                              # same keys in the XPS 13 envelope
```

`--column-splay` is ergogen style: pinky to inner, each relative to the previous column.
`--gap auto` widens the halves until a key cell would leave the usable area or touch a keep-out
(on the MacBook that is Touch ID). Key cells outside the envelope or inside a keep-out are reported.

Print `docs/images/layout.pdf` at 100 % (A4 landscape, the board outline is centred on the page)
and check both 100 mm rulers (trackpad notch, between the halves), measured from the long tick
at 0 to the long tick at 100. Paper size plain A4, not
"borderless" (that enlarges about 3 %), scale 100 %, not "fit". Print the PDF, not the SVG: the macOS print
dialog shrinks SVGs to the printable area (about 1 %). `tools/svg_to_pdf.py` writes the PDF without
external tools and asks the viewer not to scale it.

![Layout](docs/images/layout.svg)

## Schematic
Generated, not drawn: `tools/gen_schematic.py` writes the root sheet, the switch sub-sheet and
the project file into [board/](board/). The matrix is one 74HC595 (8 driven columns) x 6 XIAO
inputs, see `tools/matrix.json`. Check with

```sh
tools/gen_schematic.py
kicad-cli sch erc --severity-all board/mnhttn48-unibody.kicad_sch
```

## PCB
Generated as well: `tools/gen_pcb.py` places the switches from `board/layout.json`, the diodes
in two blocks between the halves, the XIAO in the top left corner (USB-C out of the left edge,
reachable while typing), the shift register between the halves and routes the whole matrix. It
needs KiCad's own Python (pcbnew), `tools/drc.sh` wraps generation and DRC:

```sh
tools/drc.sh            # regenerate the board, DRC summary and key matrix check
tools/drc.sh details    # every violation with coordinates
tools/check_matrix.py   # key matrix from the netlist vs tools/matrix.json, prints the grid
```

KiCad 10 project in [board/](board/), footprints in `board/mnhttn.pretty` (copied from mnhTTn48
plus SOIC-16 and 0603 from the KiCad library). 1.6 mm, 2 layers.

Fabrication files for JLCPCB (Gerber X2 with Protel extensions, Excellon drills, settings from
their KiCad guide): `make -C board fab` writes `board/out/` and `board/out.zip` (not tracked).
Order 2 layers, 1.6 mm thickness, 284.3 x 190 mm.

## Parts

| Part | Count | Package / remarks |
| ---- | ----: | ----------------- |
| PCB | 1 | 2 layers, 1.6 mm, 284.3 x 190 mm |
| Seeed Studio XIAO nRF52840 | 1 | BLE version, not the Plus |
| Cherry MX ULP | 44 | |
| 1N4148W | 44 | SOD-123 |
| 74HC595 | 1 | SOIC-16 narrow (3.9 mm), e.g. 74HC595D |
| Capacitor 100 nF | 1 | 0603, X7R, 25 V or more |
| MSK12C02 | 1 | power switch |
| COM-08720 | 1 | reset switch, optional |
| 301030 LiPo | 1 | 3.7 V, 80 mAh, 32 x 10 x 3 mm |
| Keycaps | 44 | mnhTTn48 keycaps |
| Rest pads, rubber strips | | rest pads on the deck and palm rest, strips between the notebook key rows |

## Keycaps
Unchanged, use the [mnhTTn48 keycaps](https://github.com/venc0r/mnhttn/tree/main/keycaps).

## Firmware
ZMK v0.3, shield `mnhttn48_unibody` for the `xiao_ble` board. This repo is a ZMK module
(`zephyr/module.yml`, shield in [zmk-config/boards/shields/mnhttn48_unibody](zmk-config/boards/shields/mnhttn48_unibody/)),
like the re-gret. The shield ships an example keymap, your own keymap lives in your zmk-config.
Add the module to `config/west.yml` there:

```yaml
manifest:
  remotes:
    - name: venc0r
      url-base: https://github.com/venc0r
  projects:
    - name: mnhttn48-unibody
      remote: venc0r
      revision: main
```

and the build to `build.yaml`:

```yaml
include:
  - board: xiao_ble
    shield: mnhttn48_unibody
```

Keymap order: four rows of ten (left pinky to inner, right inner to pinky), then the thumbs left
outer, left inner, right inner, right outer. The 74HC595 drives COL_0..7 (QA..QH), the XIAO reads
ROW_0..5 on D0..D5, `col2row`; SPI on D8 (SCK), D10 (MOSI), D9 (latch as chip select).
`tools/gen_zmk.py` writes the matrix transform and the physical layout (ZMK Studio) from
`board/layout.json` and `tools/matrix.json`, `tools/check_matrix.py` checks the wiring.
