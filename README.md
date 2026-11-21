# mnhTTn48 unibody

Unibody variant of the [mnhTTn48](https://github.com/venc0r/mnhttn) split keyboard,
made to sit on top of a notebook keyboard (Dell XPS 13 9300, MacBook Pro 14 2026).

* Same 5x4+3+1 per side layout, Cherry MX ULP switches, mnhTTn48 keycaps
* Both halves on one PCB, 20 degree splay per half
* One Seeed XIAO nRF52840 BLE + 74HC595 shift register, 8x6 matrix, ZMK
* 2.0 mm PCB for stiffness and a flat underside, rests on the notebook keys on a rubber mat

Status: planning, see [agent.md](agent.md).

## Layout
Mnhttn48 key positions are the source of truth. The generator in `tools/` (todo) rotates each
half and writes positions for the board.

## PCB
KiCad 10 project in [board/](board/), footprints in `board/mnhttn.pretty` (copied from mnhTTn48).

## Keycaps
Unchanged, use the [mnhTTn48 keycaps](https://github.com/venc0r/mnhttn/tree/main/keycaps).

## Firmware
ZMK shield `mnhttn48_unibody` in [zmk-config/](zmk-config/) (todo).
