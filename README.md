# buck-tpsm33610

A 3–36 V to 3.3 V, 1 A break-out board for the TI **TPSM33610S3QRDNRQ1** — a
synchronous buck *module* with the controller, both FETs, the inductor and the
bootstrap capacitor inside one 3.5 × 4.5 × 2.1 mm QFN-FCMOD package.

**9.01 × 12.525 mm**, 2 layers, one 2.54 mm header row: VIN, GND, VOUT.

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
| Switching | 2.2 MHz, auto/PFM by default (see DRSS note below) |
| Layers | 2 × 35 µm (1 oz), ENIG, 1.6 mm FR4 |
| Drawn to | 150 µm track / 150 µm clearance |
| I/O | one 1×3 header, 2.54 mm: VIN, GND, VOUT |
| Control | EN, PGOOD, MODE on 1.0 mm solder pads; JP1 selects FPWM |

Pin rules from TI **SNVSCS7E** that shape the whole layout: SW (5, 6) carries no
copper beyond its lands; BOOT (7) is a no-connect because the 100 nF is internal;
MODE/SYNC (11) has a **5.5 V abs max** and must never reach VIN; PGOOD (1) tops
out at 20 V, so its pull-up goes to VOUT. `gen_sch.py` asserts these as an
abs-max-per-pin gate at generation time, so a net that could over-volt a pin
fails the build rather than the board.

The datasheet states the 100 nF bootstrap cap is internal (p.5, pin 7) and
requires external bypass at VIN (p.5, pin 3). It does not say whether any
internal VIN bypass exists; assume none and bypass externally.

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

- **Thermal is an estimate, not a measurement, and the estimate is unsourced.**
  ~120 °C/W at the 35 µm this board actually specifies, against TI's 54.1 °C/W
  JESD 51-7 four-layer figure and 22 °C/W for their EVM. No derivation for that
  number exists in this repo — treat it as an order-of-magnitude expectation, not
  a bounded estimate. That predicts full 1 A to roughly 80 °C ambient at
  24 V and ~64 °C at 36 V. Unverified. ΨJB is 16.3 °C/W, so the acceptance test
  is to probe board temperature beside the GND land and compute
  `Tj = Tboard + 16.3 × Pd`.
- **Input loop inductance: 3.67 nH of board copper** (C1‖C2), extracted with
  FastHenry at 0.25 mm mesh pitch, ±1 % over a 2.5× pitch range. This is **board
  copper only and a lower bound** — the module's pad-to-die path is not published
  and is deliberately not estimated. Not cross-checked against hardware. **The
  extraction tool is not in this repo** and neither is its output, so nothing here
  substantiates that figure; it is reproduced from an external run.
- **The VIN neck is 0.245 mm and is marginal at the specified copper weight.**
  At 35 µm, IPC-2221 gives **0.86 A at 10 K rise and 1.17 A at 20 K**. Worst-case
  input current is ~1.0–1.1 A, which occurs at the low end of the *regulating*
  input range (around 3.5–4 V, where duty is highest); below that the part is in
  dropout and no longer making 3.3 V. So the neck sits **above its 10 K rating and
  inside its 20 K rating** — it works, at a higher local rise than is comfortable.
  At 70 µm the same neck gives 1.43 A / 1.93 A and is unambiguously fine. TI asks
  for 2 oz outer layers (SNVSCS7E p.35 item 6); this board is drawn at 1 oz.
- **Resistance of the declared power paths** at 35 µm, 0.1 mm solver grid:
  `/VIN C1.1↔U1.3` 9.27 mΩ, `/VIN J1.1↔U1.3` 11.04, `GND J1.2↔U1.10` 3.23,
  `GND C2.2↔U1.10` 2.36, `/VOUT J1.3↔U1.4` 1.84, `/VOUT U1.4↔C4.1` 0.96.
- **Spread spectrum is mostly OFF in the shipped default.** Table 7-2 calls the
  MODE-low state "auto mode with spread spectrum", but §7.3.8 p.18 overrides it:
  DRSS is disabled whenever the clock is not free-running — including when the
  clock slows under light load in auto mode, and in dropout. Bridge JP1 for FPWM
  if you want DRSS active at light load.
- **Two accepted DRC warnings**: the C1–C4 courtyard overlap (side-by-side pair
  whose cheapest escape is X, not Y) and an R3/R6 silkscreen clearance. Zero
  errors, zero unconnected pads. The generators cite a `DESIGN.md` for the
  per-pair disposition of those warnings; **that file does not exist**, so the
  waiver is currently undocumented.
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
