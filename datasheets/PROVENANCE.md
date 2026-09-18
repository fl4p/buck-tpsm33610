# Datasheet provenance

Where each PDF in this directory came from, so a claim sourced from one can be
re-checked without guessing which document or revision was read.

| file | part | document | retrieved | source URL |
|---|---|---|---|---|
| `TI-TPSM336xx-Q1-SNVSCS7E-revE.pdf` | TI **TPSM33610S3QRDNRQ1** (U1) | **SNVSCS7E**, APRIL 2025 – REVISED SEPTEMBER 2026 (Rev. E) | 2026-09-13 | `https://www.ti.com/lit/ds/symlink/tpsm33610-q1.pdf` |

SHA-256:

```
59703a765616bffb3e0278fa0100bafd4b9f95aa9751f244311d5f2f2782d572  TI-TPSM336xx-Q1-SNVSCS7E-revE.pdf
```

Hashed **after** the copy into this directory, not at download.

**The PDF itself is not stored in this repository.** TI's document is not
redistributed here; fetch it from the source URL above and check it against the
SHA-256 before reading a number out of it. `datasheets/*.pdf` is gitignored.

## Fetch record

Rung 1 of the access ladder (plain `curl -L` with a desktop Chrome UA) returned
the document on the second URL tried. Recorded because the first URL is the one
an obvious guess produces and it is wrong:

| URL | result |
|---|---|
| `https://www.ti.com/lit/ds/symlink/tpsm33610.pdf` | **HTTP 404**, 3298 bytes of HTML — TI's "Error 404 not found" page, saved under a `.pdf` name. Not a datasheet. |
| `https://www.ti.com/lit/ds/symlink/tpsm33610-q1.pdf` | HTTP 200, 3 231 249 bytes, `%PDF-1.6`, 49 pages. **This file.** |
| `https://www.ti.com/lit/gpn/tpsm33610-q1` | HTTP 200, byte-identical to the above |

No WAF, no interstitial, no CAPTCHA. Judged by content: `pdfinfo` reports
`Keywords: SNVSCS7E`, `Author: Texas Instruments, Incorporated [SNVSCS7,E?]`,
`Title: TPSM336xx-Q1 Automotive, 3V to 36V Input, 1V to 7V Output, 0.6A, 1A, and
2A Synchronous Buck Converter Power Modules in a HotRod™ QFN Package With
Mitigated Interference and Noise Technology (MINT) datasheet (Rev. E)`.

## Why the family document, and what it costs

There is no `TPSM33610S3QRDNRQ1`-only datasheet. SNVSCS7E covers three current
ratings — TPSM33606-Q1 (0.6 A), **TPSM33610-Q1 (1 A, ours)** and TPSM33620-Q1
(2 A) — in two fixed-output trims (3.3 V `S3`, 5 V `S5`) plus an adjustable part.
**Most of the application tables in Section 8 are written against the 2 A part.**
Anything read from this document must therefore name the device column, not just
the page. In particular:

- **Table 8-1 and Table 8-2 (p. 26) are `TPSM33620-Q1`.** They call for
  2 × 22 µF of COUT. They are *not* the component table for this board.
- **Table 8-3 (p. 26) is the fixed-output `TPSM33610/06-Q1` table** — the one that
  applies here: CIN 4.7 µF + 100 nF, CVCC 1 µF, **COUT 1 × 22 µF**, RFBT short,
  RFBB and CFF do-not-populate.
- The **Thermal Information table (p. 7) is shared across all three dies**, and the
  RθJA figure printed there is measured on `TPSM33625EVM` (22 °C/W) or a 4-layer
  JESD 51-7 board (54.1 °C/W). Its own footnote says the JESD value "can not be
  used for design purposes."
- The **current-limit rows in the Electrical Characteristics (p. 7–8) are
  per-device.** Ours is `IL_HS` 1.7/2.0/2.3 A, `IL_LS` 0.85/1.1/1.4 A — *not* the
  3.4/4/4.6 A row, which is the 2 A part.

## Page map used by this project

Cite these page numbers, not section numbers alone; they are PDF pages of this
exact file (49 pages total).

| topic | page |
|---|---|
| Device Comparison Table — `TPSM33610S3QRDNRQ1` = "3.3 V fixed / adjustable", spread spectrum **yes** | 4 |
| Figure 5-1 pinout, **TOP VIEW**, + Pin Functions table | 5 |
| Absolute Maximum Ratings — VIN 40 V, **MODE/SYNC 5.5 V**, EN 40 V, PG 20 V, VOUT 16 V, FB 16 V | 6 |
| Thermal Information (RθJA 22 / 54.1, ΨJB 16.3) + Electrical Characteristics | 7–8 |
| §7.3.2 Output Voltage Selection; Eq. 1–3; Table 7-1 divider values | 12–13 |
| §7.3.3 Enable, start-up, shutdown | 14–15 |
| §7.3.4 External CLK SYNC; Table 7-2 mode selection; pulse-dependent MODE control | 15–17 |
| Table 8-3 — **fixed-output TPSM33610/06-Q1 external components** | 26 |
| §8.2.2.3 input capacitor selection + recommended parts | 27–28 |
| Thermal design, IOUT,max equation (9) | 29 |
| Efficiency curves, 3.3 V / 2.2 MHz | 30 |
| §8.5.1 Layout Guidelines; Figure 8-19 fast-edge current loops | 34–35 |
| §8.5.2 Layout Example, Figures 8-20 / 8-21 | 36 |
| §9.1.3 Device nomenclature (decodes `S3` = 3.3 V fixed, `S` = spread spectrum on) | 37 |
| **PACKAGE OUTLINE RDN0011B**, drawing 4231197/B 08/2025 | **46** |
| **EXAMPLE BOARD LAYOUT / LAND PATTERN EXAMPLE** | **47** |
| **EXAMPLE STENCIL DESIGN** | **48** |
