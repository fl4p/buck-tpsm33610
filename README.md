# buck-tpsm33610

A 3–36 V to 3.3 V, 1 A break-out board for the TI **TPSM33610S3QRDNRQ1** — a
synchronous buck *module* with the controller, both FETs, the inductor and the
bootstrap capacitor inside one 3.5 × 4.5 × 2.1 mm QFN-FCMOD package.

**9.01 × 12.525 mm**, 2 layers, straddles a breadboard on 0.4 in header rows.

> **Status: unbuilt.** This board has never been fabricated, assembled or
> powered. No gerbers have been generated. Every number below is either a
> datasheet value or a computed estimate — none of it is a bench measurement.
> Treat it as a design under review, not a validated product.

## What is generated

Everything. The KiCad symbol, footprints, schematic and PCB are all outputs of
the Python in this repo; the `.kicad_sch` and `.kicad_pcb` are build artefacts
and hand edits in the GUI are overwritten on the next run.

```
variants.py           geometry constants -- the single source of truth
project_settings.py   owns .kicad_pro design rules; apply() / verify()
gen_sym.py         -> lib/buck-tpsm33610.kicad_sym
gen_fp.py          -> lib/buck-tpsm33610.pretty/*.kicad_mod
gen_sch.py         -> buck-tpsm33610.kicad_sch
gen_pcb.py         -> buck-tpsm33610.kicad_pcb   (placement, routing, pours, fill)
check_netlist.py      capture-completion gate
```

Regenerate, in order. `gen_pcb.py` needs KiCad's bundled interpreter, the only
one that can `import pcbnew`:

```sh
KI=/Applications/KiCad/KiCad.app/Contents
KIPY=$KI/Frameworks/Python.framework/Versions/Current/bin/python3
CLI=$KI/MacOS/kicad-cli

python3 gen_sym.py && python3 gen_fp.py && python3 gen_sch.py
$CLI sch erc --severity-all --exit-code-violations -o erc.rpt buck-tpsm33610.kicad_sch
$CLI sch export netlist -o buck-tpsm33610.net buck-tpsm33610.kicad_sch
$KIPY gen_pcb.py
$CLI pcb drc --severity-all --schematic-parity --exit-code-violations \
     -o drc.rpt buck-tpsm33610.kicad_pcb
```

Built and verified against KiCad 10.0.5.

Two flags matter more than they look. `--exit-code-violations` is not
decoration: without it `kicad-cli` writes the violations to the report and still
exits 0. And DRC is deliberately run **without** `--refill-zones` — re-pouring
from the project at check time grades a board that is not the one in the file,
and that is exactly how an isolated pad hid here once.

## Design

| | |
|---|---|
| Input | 3–36 V (40 V abs max), no reverse-polarity or transient protection |
| Output | 3.3 V fixed, 1 A, ±1 % |
| Switching | 2.2 MHz, auto/PFM by default, DRSS spread-spectrum active |
| Layers | 2 × 70 µm (2 oz), ENIG, 1.6 mm FR4 |
| Drawn to | 200 µm track / 200 µm clearance |
| I/O | 2 × 1×3 headers on 0.4 in rows: VIN, GND, VOUT |
| Control | EN, PGOOD, MODE on 1.0 mm solder pads; JP1 selects FPWM |

Pin rules from TI **SNVSCS7E** that shape the whole layout: SW (5, 6) carries no
copper beyond its lands; BOOT (7) is a no-connect because the 100 nF is internal;
MODE/SYNC (11) has a **5.5 V abs max** and must never reach VIN; PGOOD (1) tops
out at 20 V, so its pull-up goes to VOUT. `gen_sch.py` asserts these as an
abs-max-per-pin gate at generation time, so a net that could over-volt a pin
fails the build rather than the board.

The module has **no internal input bypass** — only the BOOT–SW bootstrap cap.
External bypass directly at the VIN pin is required, not optional.

### Two layers

TI's datasheet asks for four. The cost is quantified rather than waived: on a
1.6 mm two-layer board the image plane sits 1.6 mm below F.Cu instead of ~0.2 mm,
so a top-side switching run encloses roughly 8× the area. What makes it
defensible is that the highest-di/dt loop is kept small locally and the back side
is one unbroken ground pour.

### Verification gates

The generators are gates, not reports — each fails the build:

- **Fill runs in a clean subprocess.** `CreateEmptyBoard()` loads KiCad's default
  project into the interpreter, and a later `LoadBoard()` in the same process
  keeps those defaults, so an in-process pour uses the wrong clearances. This
  cost a silently isolated pad once.
- **Connectivity after fill** — every pad must reach every other pad on its net,
  or the build fails.
- **Courtyard overlap by polygon intersection**, not inflated bounding boxes.
- **Abs-max per U1 pin** from the datasheet table.
- **BOM line consistency** — parts sharing an MPN must agree on value and footprint.
- **MODE never floats** in any jumper state.

## Known and open

- **Thermal is an estimate, not a measurement.** ~105 °C/W at 70 µm (range
  95–115) for this board area, against TI's 54.1 °C/W JESD 51-7 four-layer figure
  and 22 °C/W for their EVM. That predicts full 1 A to roughly 80 °C ambient at
  24 V and ~64 °C at 36 V. Unverified. ΨJB is 16.3 °C/W, so the acceptance test
  is to probe board temperature beside the GND land and compute
  `Tj = Tboard + 16.3 × Pd`.
- **Input loop inductance: 3.67 nH of board copper** (C1‖C2), extracted with
  FastHenry at 0.25 mm mesh pitch, converged to ±1 % over a 2.5× pitch range.
  This is **board copper only and a lower bound** — the module's pad-to-die path
  is not published and is deliberately not estimated. Not cross-checked against
  hardware.
- **The VIN neck is 0.245 mm** and is a copper-weight constraint. At the
  specified 70 µm, IPC-2221 gives 1.43 A at 10 K rise against a worst-case
  ~1.2–1.4 A input at 3 V in / 1 A out — it passes. At 35 µm the same neck gives
  0.86 A and will not carry full load at low input voltage. Do not drop the
  copper weight without re-checking this.
- **Two accepted DRC warnings**: the C1–C4 courtyard overlap (side-by-side pair
  whose cheapest escape is X, not Y) and an R3/R6 silkscreen clearance. Zero
  errors, zero unconnected pads.
- **No input protection at all** — no TVS, no reverse-polarity FET, not even a
  DNP land. EN is hard-tied to VIN. Nothing here survives a hot-unplug inductive
  kick on a long 36 V lead. Bench use from a stiff supply only.
- `make_fab.py` is not written, so there are no gerbers and no assembly data.

## Datasheet

TI **SNVSCS7E**, "TPSM336xx-Q1". Not redistributed here —
`datasheets/PROVENANCE.md` carries the source URL and the SHA-256 of the exact
revision every page citation in this repo refers to.

## History

Developed inside a private monorepo; this repository starts from a squashed
snapshot, so the per-change history is not carried over.

## Licence

Not yet chosen, so no licence is granted — all rights reserved for now. If you
want to use any of this, open an issue and ask.
