# The input loop measured, and how it compares with TI's own reference

**2026-09-18. Analysis only — nothing in this document was measured on hardware.** The
board has been sent to fab at revision `e6fe53a`; see §4.4, which is the section to read
if you only want to know what the hardware in flight can do. It records what the extracted copper and the vendors' own
capacitor data say about the input bank, what TI's datasheet and EVM do differently,
and which of those differences are worth acting on.

Tooling and provenance: `pv/ee/dcdc-tools/mlcc/` (commits `d396b52` … `806b2b0`),
which reads vendor curves and SPICE models from `vendorpull/store` and the board
copper from `pv/ee/dcdc-tools/parasitics` (FastHenry). Three independent Codex reviews
of that code raised twenty findings, all real, all fixed; the numbers below are
post-review. Everything here ran against a **scratch copy** of this project — the
board files were never written, and the KiCad locks were left alone.

To reproduce the tables: `python3 -m mlcc.vin_budget_tpsm33610` from `dcdc-tools`. It
reads an extraction JSON, so pointing it at a different board means re-running the
parasitics extractor first — and at the commit that was fabricated (§4.4), not at HEAD.

---

## 1. The limit, and where it comes from

TI publishes no input-ripple spec. It publishes a rating, and a warning:

* SNVSCS7E rev E §6.1 — **VIN to GND absolute maximum 40 V**; §6.3 recommends 3–36 V.
* §7.3.1 — *"Take extra care to confirm that the voltage at the VIN pin does not exceed
  the absolute maximum voltage rating of 40 V during line or load transient events.
  Voltage ringing at the VIN pins that exceeds the absolute maximum ratings can damage
  the IC."*

So at the top of the input range the **entire** ripple-plus-ring budget at the pin is
**4.0 V**, and only there: at 24 V in there is 16 V of headroom. The EN pin, tied to VIN
through R4, carries the same 40 V rating, so it is not a tighter constraint.

The 5 mΩ input-impedance target quoted in earlier discussion was never derived from
anything. This one is.

## 2. Two failure modes, with different causes and different fixes

**(a) The switching edge.** The pin sees `L_trunk × Iout / t_edge` — the shared copper
between the module pins and the point where the capacitors meet. TI publishes no edge
rate, so this is a parameter sweep, never a prediction. At 36 V, 1 A, board copper only,
the excursion **above** the rail (the one the rating has to survive):

| t_edge | overshoot | VIN peak | headroom |
|---|---|---|---|
| 1 ns | 3.93 V | 39.93 V | **0.07 V** |
| 2 ns | 1.90 V | 37.90 V | 2.10 V |
| 5 ns | 0.68 V | 36.68 V | 3.32 V |
| 20 ns | 0.13 V | 36.13 V | 3.87 V |

**(b) The C1/C2 anti-resonance.** The two branches are 4.633 nH (C1) and 0.646 nH (C2) —
a 7× imbalance — which resonates at 5.8 MHz at 36 V with a peak near 1.3 Ω. Worst single
harmonic across VIN and the switching-frequency band: **436 mV pp** (vendor-curve basis)
/ 417 mV (vendor-model basis), the third harmonic at 36 V. That figure is *optimistic*:
the model takes ESR from the 0 V curve at a bias-shifted resonance, which overstates
damping (see §6).

Note the switching frequency is a band, not 2.2 MHz: `tON_MIN` is 65 ns typ / 75 ns max
(§6.5), so above ~20 V the module stretches its cycle (§7.4.3.4), and the clock itself is
2.1/2.2/2.3 MHz with ±4 % DRSS, which this device option enables.

## 3. What the copper can and cannot fix

Measured on a scratch copy: the project was copied out, regenerated with its own
`gen_pcb.py` under KiCad's python, and re-extracted. The unmodified copy reproduces the
committed extraction exactly (L_loop 3.6710 nH, trunk 3.1038, C2 0.6464, C1 4.6331), so
the deltas below are the variants and not the pipeline. Both variants regenerate with no
new DRC severities.

| variant | trunk | L_loop | loop R | overshoot @1 ns | worst harmonic |
|---|---|---|---|---|---|
| as built | 3.104 nH | 3.671 nH | 7.96 mΩ | 3.93 V | 436 mV |
| VIN stub 0.30/0.40 → 0.55 mm | 2.974 | 3.542 | 7.05 | 3.80 V | 429 mV |
| + a third GND via on the hot return | 2.999 | 3.493 | 6.78 | 3.75 V | 440 mV |
| + C1 branch at 1.0 nH *(assumed, not extracted)* | 2.999 | — | — | 3.65 V | **123 mV** |

**Routing tweaks do not buy the VIN margin** — 5 % off L_loop moves the headroom 0.07 →
0.25 V. The placement was already close to its floor before this analysis existed: C2 is
hard against the pin row (swapped with R4, citing §8.5.1 item 1), the hot return already
has two parallel vias plus one at U1.10, and C1 is rotated so its VIN pad faces the
module. What widening copper *does* buy is resistance (−15 %), which is damping.

**Moving C1 next to C2 is worth 72 % of the resonance** and almost nothing on the edge.
It is a placement-and-routing change (C1's VIN feed would have to cross C2's ground pad),
and the 1.0 nH is an assumed branch — the prize, not a measurement of a real layout.

## 4. TI's reference design, and the three things it does differently

From §8.5.2 Figure 8-21 and the TPSM33620QEVM user's guide (SNVU943 §4.3):

| | TI | this board |
|---|---|---|
| stackup | 4 layers, ground plane under the top, 2 oz outer / 1 oz inner | 2 layers, 35 µm, return 1.6 mm away |
| HF cap | ~100 nF 0402/0603 **on the bottom**, "through via nearest to VIN pin" | none on the bottom |
| input bank | 2 × 4.7 µF 1210 + 0.1 µF 0402 + **100 µF aluminium** | 10 µF 1206 + 1 µF 0603, no bulk |

### 4.1 The stackup is the biggest lever

Measured by moving the return pour closer to the top copper. The extractor spaces copper
layers evenly through the board thickness and via barrels shorten with it, so this is a
faithful **proxy** for a ground plane on layer 2 — not a drawn 4-layer board:

| return plane | trunk | L_loop | overshoot @1 ns | VIN peak | worst harmonic |
|---|---|---|---|---|---|
| 1.6 mm (as built) | 3.104 nH | 3.671 nH | 3.93 V | 39.93 V | 436 mV |
| 0.8 mm | 2.166 | 2.511 | 2.70 V | 38.70 V | 357 mV |
| 0.4 mm | 1.633 | 1.921 | 2.20 V | 38.20 V | 294 mV |
| 0.2 mm | 1.256 | 1.514 | **1.82 V** | 37.82 V | **226 mV** |

A plane at 0.2 mm takes 60 % off the trunk where routing took 3 %, and it is the only
change found that improves **both** failure modes at once. It is also a different
product: the 2-layer 35 µm ENIG choice is deliberate and documented in §5 of DESIGN.md
along with the rule-bending it required, and 4 layers with 2 oz outers changes fab, cost
and every clearance budget. The 2 oz copper itself mostly buys resistance, not
inductance.

### 4.2 The backside 100 nF — untested, and the cheapest item on the list

A capacitor under the pins on B.Cu is a third branch with an almost-zero shared path,
aimed straight at the edge term. It needs a schematic entry, a footprint on the back and
its vias, so it was not built in the scratch copy. **This is the recommended next
measurement** if the 40 V margin matters.

### 4.3 The bulk capacitor answers the capacitance question

TI's EVM ceramics alone: 9.50 µF nameplate, **3.87 µF effective at 36 V — 0.82×** of the
4.7 µF minimum. TI's own board does not meet an *effective* reading on ceramics either;
it meets it with the 100 µF electrolytic, which barely derates.

| bank | nameplate | effective @36 V | vs 4.7 µF |
|---|---|---|---|
| this board (10 µF + 1 µF) | 11.0 µF | 2.10 µF | 0.45× |
| TI Table 8-5 pair (4.7 + 0.1) | 4.8 µF | 1.95 µF | 0.41× |
| TI EVM ceramics (2 × 4.7 + 0.1) | 9.5 µF | 3.87 µF | 0.82× |
| this board + a second 10 µF 1206 | 21.0 µF | 4.08 µF | 0.87× |

Per part at 36 V, from the vendors' own DC-bias curves: TI's 4.7 µF 1210
(C3225X7R1H475K250AB) 4.435 → 1.924 µF (−57 %); the 0.1 µF 0402 (GRM155R61H104ME14D)
91 → 22 nF (−76 %).

**If the requirement is effective, the answer is bulk, not a bigger MLCC** — no
reasonable ceramic addition reaches 4.7 µF at 36 V.

Whether it *is* effective is unresolved: §8.2's note says application values are
effective unless stated otherwise and §8.2.2.3 does not state otherwise, but Table 8-5
footnote 2 marks TI's own recommendation as nameplate, and both TI's reference pair and
its EVM ceramics fail the effective reading. A public search (TI E2E, 2026-09-17) found
the same boilerplate across TI's module family and no answer for this part. **It needs a
question to TI.**

Also worth recording: on this board's copper, TI's Table 8-5 pair would be **worse** than
the parts fitted — 931 mV worst harmonic against 436, and a 4.34 Ω peak at 13.3 MHz
against 1.36 Ω at 5.8 MHz — because a 0.1 µF on the short branch rings harder against the
long one than the fitted 1 µF does. No part change is indicated. (Caveat: the copper was
extracted for 1206/0603 pads, not TI's 1210/0402.)

### 4.4 The board that went to fab is NOT the board in the repo

Checked 2026-09-18 after Fab reported the fabbed board has C1's GND pad on the right.
That is the orientation at **`e6fe53a`**; `92baceb` (2026-09-16) rotated C1 180 deg and
swapped C2/R4 so the input cap sits hard against the pin row. Everything in sections 2-3
above was extracted from repo HEAD, i.e. from a board that was never fabricated.

Extracted from `e6fe53a` itself, the same way:

| | trunk | L_loop | C2 branch | C1 branch |
|---|---|---|---|---|
| repo HEAD (C1 rot 180, C2 close) | 3.104 nH | 3.671 nH | 0.646 nH | 4.633 nH |
| **as fabbed (e6fe53a)** | **3.288 nH** | **3.890 nH** | 0.707 nH | 4.041 nH |

The fabbed board's shared trunk is 6 % LONGER — R4, not C2, had the slot against the pin
row — so its edge spike is 6 % larger. Its C1 branch is shorter, so the branch imbalance
is 5.7x rather than 7.2x and the resonance is slightly milder. The two changes pull in
opposite directions: **ripple a little better, VIN margin a little worse.**

### What the fabbed board does, 1 A out

| VIN | C_eff | worst harmonic | overshoot @1 ns | headroom | @2 ns | headroom |
|---|---|---|---|---|---|---|
| 12 V | 6.68 µF | 180 mV | 4.25 V | 23.8 V | 2.11 V | 25.9 V |
| 24 V | 3.53 µF | 351 mV | 4.15 V | 11.9 V | 2.01 V | 14.0 V |
| 30 V | 2.72 µF | 351 mV | 4.19 V | 5.8 V | 2.06 V | 7.9 V |
| 35 V | 2.15 µF | 383 mV | 4.14 V | **0.86 V** | 2.01 V | 3.0 V |
| 36 V | 2.10 µF | 390 mV | 4.12 V | **-0.12 V** | 1.99 V | 2.0 V |

**12-35 V at 1 A is fine.** The spike barely varies with input voltage (it is
`L·di/dt`, set by current and copper), so the headroom is simply `40 V - VIN - spike`.
36 V is the first point where the most pessimistic assumption (a 1 ns edge) crosses the
absolute maximum; 35 V keeps 0.86 V even there, and 3.0 V at a more typical 2 ns edge.
Input ripple stays under 0.4 V pp, about 1 % of the rail.

**So: run it at 12-35 V, 1 A. Do not sit at 36 V until the edge rate is measured.**

## 5. What to do

The hardware exists, so this splits into what governs *this* board and what governs the
next revision.

### 5.1 This board, now

1. **Run it at 12-35 V, 1 A** (§4.4). No change is required to do that.
2. **Measure the edge at bring-up before going above 35 V.** This is the single
   measurement that collapses the whole parameter sweep: the entire 36 V question is a
   disagreement between a 1 ns assumption (-0.12 V) and a 2 ns one (+2.0 V), and nothing
   in the analysis can settle it. See §5.3 for how.
3. **A backside 100 nF is retrofittable.** On a 2-layer board the bottom copper under the
   VIN pins is reachable; if the measured edge turns out to be fast, this is the fix that
   does not need a new board.

### 5.2 Next revision

1. **Decide the stackup question first.** It is the only change that fixes both modes,
   and it is a product decision (fab, cost), not a layout tweak.
2. **If staying 2-layer: add the backside 100 nF** as a placed part, and consider moving
   C1 beside C2. Take the copper tweaks (wider VIN stub, third via) as free damping.
3. **Add bulk** if the minimum-capacitance requirement turns out to be effective — and
   ask TI which it is (§4.3).
4. **Re-extract from the commit that is actually fabricated**, not from HEAD. §4.4 exists
   because that was not done.

### 5.3 The bring-up measurement

What to capture, so the result is comparable with the tables above:

* **Where:** across U1's VIN and GND *pads*, not at the connector and not across C1 —
  everything here is referenced to the module pads.
* **How:** ground spring, not a clip lead. A clip lead's own loop has been measured on
  this bench to invent ringing that is not there (`~/dev/kb`, sw-ring-15mhz-was-probe-clip).
* **What:** VIN at the switching edge, at 1 A, at 24 V and 35 V. Read (a) the peak
  excursion **above** VIN — that is the number §4.4 compares with 40 V — and (b) the
  10-90 % edge time.
* **The verdict:** the overshoot column of §4.4 is `L_trunk x Iout / t_edge`. If the
  measured edge is >=2 ns, 36 V has ~2 V of margin and the pessimistic row can be
  retired. If it is near 1 ns, 35 V is the ceiling as written.

## 6. What this analysis does not know

* **The module's internals.** The extraction closes the loop at the package pads. TI
  publishes no pad-to-die geometry and no internal decoupling, so every inductance here
  is a **lower bound**. TI's integration list names the FETs, controller, inductor and
  boot capacitor — no input capacitor.
* **The switch edge rate.** Unpublished; every number in §2(a) is conditional on it.
* **Damping near resonance.** ESR is read from the 0 V curve at a bias-shifted
  resonance. Against TDK's own encrypted DC-bias model at 36 V the construction reads
  8.6 mΩ (model basis) / 16.1 mΩ (curve) where TDK says 2.24 mΩ, i.e. too much damping,
  which **understates** resonant peaks. The 436 mV is therefore optimistic.
* **Temperature and tolerance.** Every curve used is 25 °C and one typical sample.
* **The vendors disagree with themselves.** A part's simple model and its own impedance
  curve differ on ESL by a median 1.79× across 1271 TDK parts, and the DC-bias models
  show the same gap. That is why every impedance figure here carries two bases; they are
  two vendor artifacts, not an error band. See
  `~/dev/kb/spice/mlcc-model-and-curve-disagree-on-esl.md`.
