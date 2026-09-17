# buck-tpsm33610 — design record

This file exists because four generators defer to it: `gen_sch.py` for design
intent and the capture record, `gen_pcb.py` and `project_settings.py` for the
courtyard-warning disposition, and `gen_fp.py` for the copper-weight claim. It
was missing until 2026-09-17 — an independent review found that the DRC waivers
were made **by reference to a document that did not exist**. Every disposition
below is either evidence or is labelled as a preference.

Status of the board: **unbuilt**. Nothing here is a bench measurement.

---

## 1. Intent

TI's Table 8-3 fixed-output application — CIN bulk + 100 nF HF, CVCC, one COUT,
FB tied to VOUT — plus exactly three additions:

1. **R1, a 0 Ω RFBT that doubles as the fixed/adjustable selector.** §7.3.2.1
   p.12: the part *"determines whether fixed output voltage or adjustable output
   voltage is required by sensing the resistance of the feedback path during
   start-up."* 0 Ω fitted = fixed. Retune R1 and fit R2 to go adjustable.
2. **R4/R5, an EN strap that can become a UVLO divider.** R4 = 0 Ω VIN→EN as
   built.
3. **R6 + JP1, the MODE strap.** R6 100 k to GND is auto/PFM. Bridge JP1 for
   FPWM via VCC.

Everything else is either the datasheet's required external or a DNP land.

## 2. Capture record — as-captured netlist

Exported from `buck-tpsm33610.kicad_sch`, this is the artefact `--schematic-parity`
checks the PCB against:

```
/EN      R4.2 R5.1 TP1.1 U1.2
/FB      C6.2 R1.2 R2.1 U1.9
/MODE    JP1.2 R6.1 TP3.1 U1.11
/PGOOD   R3.2 TP2.1 U1.1
/SW      U1.5 U1.6
/VCC     C3.1 JP1.1 R3.1 U1.8
/VIN     C1.1 C2.1 J1.1 R4.1 U1.3
/VOUT    C4.1 C6.1 J1.3 R1.1 U1.4
GND      C1.2 C2.2 C3.2 C4.2 J1.2 R2.2 R5.2 R6.2 U1.10
unconnected-(U1-BOOT-Pad7) U1.7
```

`/SW` is a legitimate two-node net — pins 5 and 6 are the same internal node, and
a minimum-length inter-land stub satisfies ERC without inventing SW copper.
BOOT is explicitly no-connected; its capacitor is internal.

### Deviations from the original plan, and why

| plan | as built | why |
|---|---|---|
| J1 + J2, two 1×4 rows on 0.400 in, breadboard straddle | **one 1×3 header**, VIN GND VOUT | the board shrank to 9.01 mm wide, which cannot span 10.16 mm rows. The straddle was given up when the board was made small. |
| C7, second 22 µF COUT (DNP) | not placed | no room after the shrink |
| R7, MODE pull-up (DNP) | replaced by **JP1** | a solder jumper selects FPWM without a second fit option, and removes the R6/R7 mutual-exclusion hazard entirely |
| TP1–TP5 | TP1–TP3 (EN, PGOOD, MODE) | VOUT_SENSE and GND test pads dropped for space |
| 200 µm track / 200 µm clearance | **150/150** | see §5 |
| 70 µm copper | **35 µm** | see §5 |

## 3. DRC dispositions

DRC is run **without** `--refill-zones` — re-pouring from the project at check
time grades a board that is not the one in the file, and gerbers come from the
file. Current result: **0 errors, 0 unconnected pads, 2 warnings**, both below.

### `courtyards_overlap` — C1 / C4 — ACCEPTED

`project_settings.py` demotes this rule to *warning* rather than `ignore`, so it
still appears in every report and cannot pass unnoticed.

C1 (CIN bulk, 1206) and C4 (COUT, 1206) sit side by side in the southern power
row. Their courtyards are each the part's real body plus the standard IPC 0.25 mm,
and they overlap in X. **The copper does not.** The measured pad-to-pad copper gap
between the two parts clears `clearance_mm`, and `kicad_copper_collisions.py`
reports 0 collisions on the built board.

Why it is not fixed rather than waived: two overlapping courtyards share a Y range
by definition, so no cut line separates them — growing the board cannot reach this
pair, and their cheapest escape is X, which is the axis already at its limit.
Shrinking a courtyard to silence the warning would be a mute button: it would
change the reported number without changing the geometry.

**Accepted risk:** courtyard is a placement/assembly convention, not a fab rule.
Two 1206s at this spacing are within reflow practice. If this board is ever
hand-reworked with hot air, C1 and C4 will heat together.

### `silk_overlap` — R3 / R6 — ACCEPTED

0.070 mm between silkscreen segments against a 0.100 mm rule. R3 and R6 are two
of the five west-face rows, moved 0.25 mm south on 2026-09-16 to clear a
*courtyard* overlap; their reference designator outlines now touch.

This is ink on ink, not copper, and it is silkscreen-to-silkscreen rather than
silk-to-pad — no pad is obscured. The cost of fixing it is re-opening the west
cluster spacing that was just tightened to fix a real courtyard overlap.

**Accepted risk:** cosmetic. Two designators may bleed together on the printed
board.

## 4. MODE / JP1 — a hazard that is not a DRC finding

**Bridging JP1 while also driving TP3 shorts an external driver to VCC.**

JP1 open: MODE is held at GND through R6 100 k — auto/PFM. A clock or logic level
on TP3 overrides it, which is why R6 is 100 k and not 0 Ω.
JP1 bridged: MODE is tied to VCC — FPWM. **TP3 must then be left alone.** Driving
TP3 low against a bridged JP1 puts the external driver across the internal LDO.

This is stated in JP1's `Spec` field in the schematic as well as here.

MODE's absolute maximum is **5.5 V** (SNVSCS7E p.6) and VCC is 3.1–3.5 V, so the
bridged state is legal. MODE must never see VIN. `check_net_ceilings()` proves
that from the netlist rather than from a comment.

## 5. Process — 35 µm ENIG, and why the copper weight is not free

Confirmed by Fab 2026-09-16: **35 µm (1 oz) ENIG**.

TI asks for 2 oz outer layers and no less than 1 oz (p.35 item 6). This board is
at that floor, and the reason is the land, not the thermals:

- The RDN0011B land has a **0.100 mm minimum copper gap** (pins 1–11 and 8–9),
  which is finer than every published Aisler 2-layer rule. It is a deliberate,
  scoped rule break — decided 2026-09-13, Fab: *"the aisler rules are
  conservative, breaking the rules has always worked so far, no bad boards."*
- At **35 µm** that gap is 1.25× under the 125 µm ENIG rule, with an etch aspect
  ratio around 0.35:1 — the rule is margin, not physics.
- At **70 µm** it is 1.75× under *and* about 0.7:1 in aspect ratio, which is a
  physical limit. This is the one place on the board where the rule should not be
  broken.

Independently, the board is drawn to **150/150 µm** outside the land (35 copper
tracks sit on that floor). That clears Aisler's 125/125 ENIG rule but **not**
35 µm HASL's 200 µm track rule. So the process is pinned: **ENIG, 35 µm**, and
the copper weight is not a choice deferred to checkout.

### What 35 µm costs

- **Thermal.** The 70 µm option was worth roughly **10 °C of ambient headroom**.
  That figure and the ~105 → ~120 °C/W θJA behind it are **estimates with no
  derivation in this repo** — an order-of-magnitude expectation, not a bounded
  result. TI publishes 54.1 °C/W (JESD 51-7, four layers, 76.2 × 114.3 mm) and
  22 °C/W (four-layer EVM); this board is two layers and ~113 mm².
  **Acceptance test:** ΨJB is 16.3 °C/W (p.7), so probe board temperature beside
  the GND land and compute `Tj = Tboard + 16.3 × Pd`. Until that is done the
  thermal claim stays an estimate.
- **The VIN neck.** 0.245 mm at 35 µm gives IPC-2221 **0.86 A at 10 K rise,
  1.17 A at 20 K**. Worst-case input current is ~1.0–1.1 A, at the low end of the
  *regulating* input range (~3.5–4 V, where duty is highest); below that the part
  is in dropout and is not making 3.3 V. So the neck runs **above its 10 K rating
  and inside its 20 K rating**. Accepted: it works, warmer than is comfortable.

### Measured path resistances

35 µm, 0.1 mm solver grid, `copper_guards.py resistance`:

| path | mΩ | budget |
|---|---|---|
| /VIN C1.1↔U1.3 | 9.27 | 5 — see below |
| /VIN J1.1↔U1.3 | 11.04 | 25 |
| GND J1.2↔U1.10 | 3.23 | 10 |
| GND C2.2↔U1.10 | 2.36 | 5 |
| /VOUT J1.3↔U1.4 | 1.84 | 10 |
| /VOUT U1.4↔C4.1 | 0.96 | 3 |

**The 5 mΩ on `/VIN C1.1↔U1.3` is not a derived limit.** It was written into the
plan without a failure mode behind it, and it is recorded here as a preference so
that nobody — including a future me — cites it as a spec. The same applies to the
plan's `L_in(HF) ≤ 3 nH`. The input-loop criterion that *is* derived is the
**8 nH total**, from overshoot against the 40 V abs max (p.6): at ~0.33 A/ns,
8 nH gives 2.6 V and 36 + 2.6 = 38.6 V. FastHenry measures **3.67 nH of board
copper** for C1‖C2 — board copper only and a lower bound, since the module's
pad-to-die path is not published.

Note the solver's default `--grid 0.2` makes the GND solve **exactly singular**
(nan) on this board; the guard fails closed on it. Use `--grid 0.1`.

## 6. Known gaps

- **No gerbers.** `make_fab.py` is not written.
- **No staleness gate** between `gen_sch.py` → `.net` → `gen_pcb.py`. Nothing
  checks that the netlist was exported from the current schematic; run the chain
  in order. This bit during the 2026-09-17 session — a `gen_pcb.py` run consumed
  a netlist from the previous day.
- **`gen_fp.py` does not prune** stale `.kicad_mod` files. Four are generated and
  four are present, so nothing is stale today, but a footprint rename leaves the
  old file behind and the board can silently keep using it.
- **Two claims unverified** by the 2026-09-17 review: exact pad X/Y against the
  p.47 land drawing, and the measured `/SW` copper area.
