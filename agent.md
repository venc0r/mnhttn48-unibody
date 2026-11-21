# Agent notes: mnhTTn48 unibody

## Goal

Unibody version of the mnhTTn48 split keyboard that lies on top of a notebook keyboard.
Target notebooks: Dell XPS 13 9300 (2020) and MacBook Pro 14 (2026, M6).
Parent project: `venc0r/mnhttn` (local `~/Documents/git/github/venc0r/mnhttn`), branch `main`.

## Decisions (2026-11-21)

| Topic | Decision | Why |
|---|---|---|
| Layout | mnhTTn48 key positions per half, unchanged. Halves splayed 20 degrees each (inward rotation like the earlier `mbpulp` try). Gap between halves is a parameter. | Keep keycaps, keymap and muscle memory. |
| Controller | One Seeed XIAO nRF52840 BLE + one 74HC595 shift register on SPI. Electrical matrix 8 register outputs x 6 XIAO inputs = 48 keys. | 48 keys need 15 matrix pins, XIAO has 11. Same trick as `rschenk/zmk-keyboard-re-gret`. Inputs stay on MCU pins so interrupt wake works. Rejected: XIAO nRF52840 Plus (bottom pads need reflow), charlieplex (polling only). |
| PCB thickness | 2.0 mm FR-4 | JLCPCB 2-layer max is 2.0 mm (2.4 / 3.2 mm only for 12+ layers). Bending stiffness scales with t^3: 37x stiffer than 0.6 mm, 2x than 1.6 mm. |
| Underside | Flat. No bottom components, switch pins must not protrude. | Board rests on the notebook keycaps with a rubber mat underneath. |
| Support | Flat on keycaps + rubber mat. | User choice. Fallback if the board presses notebook keys: 2 mm bars under the board that sit in the gaps between notebook key rows (MBP row gap 2.5 mm). |
| Repo workflow | Feature branches + PRs to `main`. | User choice (parent repo commits on main directly). |
| Keycaps | Reuse mnhTTn48 keycaps, not copied here. | Identical switches and pitch. |

## Matrix plan (8 x 6)

Register outputs are the driven side (`row2col` with register pins as rows, like re-gret).
Per half: 4 register outputs x 6 inputs. Inputs = 5 finger columns + 1 thumb line.
The 4 thumb keys of a half sit on the thumb input line, one per register output.

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
2. **Layout generator** `tools/`: reads mnhTTn48 switch positions, rotates each half by the splay
   angle, applies the gap, writes an SVG preview and the positions for the board.
3. **Schematic** `board/mnhttn48-unibody.kicad_sch`: XIAO, 74HC595, 48 switches + diodes, battery,
   power switch, reset switch. No split nets.
4. **Board** `board/mnhttn48-unibody.kicad_pcb`: single outline, 2.0 mm, no mouse bites, flat
   bottom. `make check-baseline` / `make check` around every change.
5. **Firmware**: shield `mnhttn48_unibody` in `zmk-config/`, single build target, keymap from mnhTTn48.
6. **Docs**: README, build guide delta (solder pins from the top only, 595 placement), mat spec.

## Reference numbers

mnhTTn48 board (`mnhttn.kicad_pcb`): panel 258 x 106 mm, one half main block ~112 x 88 mm,
thumb cluster adds 18 mm below. Switch footprint `Cherry_MX_ULP_Human`: 4 SMD contact pads
+ 4 THT locating pins, drill 1.016 mm, soldered from the top.

Cherry MX ULP (datasheet MX6C-T3NB): 3.9 mm total height, 13.08 x 13.6 mm, 1.8 mm travel.
Design guideline VR-00103: silicone dampening mat shore A40-60, 0.5 mm, cutout 13.4 x 13.9 mm
per switch. Keycap bump 0.38 mm recommended. No pin length given.

Notebooks (chassis only, keyboard wells are not published, measure them):
- XPS 13 9300: 295.65 mm wide, keyboard edge to edge, key pitch 19.05 x 18.05 mm.
- MacBook Pro 14 M6: 312.6 x 221.2 x 15.5 mm. From the `mbpulp` try (unverified estimates):
  keycap 16.2 x 16 mm, pitch 19.0 x 18.5 mm, row gap 2.5 mm, speaker grille inset ~28 mm.

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

## Open items

- Phase 0 measurements.
- Gap between halves and exact placement on each notebook, after the paper fit test.
- Battery placement (top side or pocket), must keep the underside flat.
- Whether the mat alone keeps notebook keys from actuating under ~100 g of board.
