#!/usr/bin/env python3
"""Board geometry and the variant table for buck-tpsm33610.

Every dimension that more than one generator needs lives here, so gen_sch.py,
gen_pcb.py, project_settings.py and audit.py cannot disagree about the board.

One variant, `base`. An unknown variant name is an error, never a silent fallback to
`base`: a typo that fell through would rebuild the wrong board while every line
on screen carried the other one's name.
"""

import argparse
import sys

# ---------------------------------------------------------------- process (Aisler)
# Aisler 2-layer, 35 um copper, ENIG. Their published rules for that stack are
# 125 um track / 125 um space; the board is drawn to 150/150 everywhere OUTSIDE
# the module land (35 copper tracks sit on that 0.15 mm floor). That clears the
# 125/125 ENIG rule but NOT 35 um HASL's 200 um track rule, so this board is
# ENIG-only -- the copper weight is no longer a free choice at checkout.
# The only other geometry near a limit is the land itself
# (0.100 mm, a deliberate accepted rule break -- see gen_fp.py and
# docs/2026-09-13-rdn0011b-land-pattern.md).
PROCESS = {
    # Fab, 2026-09-13: "you can break the aisler rules a bit". Aisler 2L 35 um
    # ENIG publishes 125/125 um track/space, 0.3 mm via drill with 200 um ring
    # (0.70 mm pad), 300 um copper-to-edge and 0.8 mm silk text. The values
    # below keep track/space ON the published rule and bend the other three a
    # little, each for a named reason:
    #   via 0.25 / 0.50 mm -- a 0.70 mm via pad does not fit beside a 0.35 mm
    #       land at 0.5 mm pitch; 0.50 does, next to the GND and VIN pins.
    #   edge 0.25 mm       -- 50 um under the rule, on a board with nothing but
    #       pours near its edge.
    #   silk 0.7 mm text / 0.12 mm stroke -- Aisler asks for 0.8 mm text on a
#       0.15 mm stroke; neither the solder-pad labels nor the three header
#       names fit at 0.8 mm on 2.54 mm pitch. 0.7/0.12 is the largest that
#       does fit, and it is the break most likely to SHOW: expect these
#       labels to print lighter than the rest of the silk.
    "fab": "Aisler",
    "layers": 2,
    "thickness_mm": 1.6,
    "copper_um": 35,
    "finish": "ENIG",
    "track_mm": 0.15,
    "clearance_mm": 0.15,
    "via_drill_mm": 0.25,
    "via_pad_mm": 0.50,
    "pth_drill_mm": 1.00,      # 0.1 in header pin
    "pth_pad_mm": 1.70,
    "edge_clearance_mm": 0.25,
    "mask_dam_mm": 0.10,
    "silk_height_mm": 0.70,
    "silk_to_pad_mm": 0.10,
    "silk_thickness_mm": 0.12,
}

# ---------------------------------------------------------------- the header
# One 1x03 row on 2.54 mm: VIN GND VOUT, pin 1 = VIN. It runs along the SOUTH
# edge, west to east, which is the face of the module (U1 at 90 degrees) that
# carries VIN and VOUT.
HDR_PITCH = 2.54
HDR_COLS = 3
HDR_NETS = ("VIN", "GND", "VOUT")

# ---------------------------------------------------------------- the module land
# Mirrors gen_fp.py; the two are cross-checked in gen_pcb.py rather than trusted.
U1_BODY = (3.5, 4.5, 2.1)

# Placement is settled at the floorplan gate (gen_pcb.py --stage place). W and H
# are the outline that gate arrived at, not an estimate.
VARIANTS = {
    "base": dict(
        name="buck-tpsm33610",
        descr="single 1x03 header, VIN GND VOUT",
        # 8.91 -> 9.91 mm wide, 2026-09-13. The 8.91 mm board could not be
        # routed: west of U1, VCC has to cross FB to reach R3 and R7, the DNP
        # feedback parts then cannot reach FB at all, and there was no 0.8 x
        # 0.8 mm of free F.Cu anywhere in that cluster for the vias those
        # crossings need. Four Freerouting scouts (as-placed, nudged, with the
        # DNP parts deleted, and 1 mm wider) left 8, 6, 6 and 5 connections
        # open. Fab chose the extra millimetre over dropping the DNP divider.
        # It is added entirely on the WEST side -- U1, C1, C2, C4, R4 and J1
        # keep their positions relative to each other, so the input loop, the
        # output run and the header geometry are unchanged.
        # H 10.825 -> 12.425, 2026-09-16. Fab: "fix the cortyards overlaps in
        # Y directions, increase board size". Eight of the eleven courtyard
        # overlaps were parts stacked too close in Y; clearing them walks a
        # chain south -- R4 off U1's pin row, C2 off R4, C1 off C2, J1 off C4 --
        # and the header has to keep its 1.10 mm to the south edge. The 1.60 mm
        # goes on the SOUTH edge only, so U1, C3, R1 and the three solder pads
        # keep their distance to the north edge and none of their copper moved.
        # The three overlaps left (C3-U1, C1-C4, C6-R2) are side-by-side pairs
        # whose cheapest escape is X, not Y: growing the board downwards cannot
        # reach them. See gen_pcb.py POS for the per-group offsets.
        W=9.01, H=12.525,
        hdr_x0=-1.675,         # VIN pin, board-centred coords
        hdr_y=5.1625,          # header row, board-centred coords (+Y = south)
        u1=(2.185, -4.0125),   # U1 centre, board-centred coords
    ),
}


def _self_check():
    for key, v in VARIANTS.items():
        pad_r = PROCESS["pth_pad_mm"] / 2
        x0 = v["hdr_x0"] - pad_r
        x1 = v["hdr_x0"] + (HDR_COLS - 1) * HDR_PITCH + pad_r
        assert x0 >= -v["W"] / 2 + PROCESS["edge_clearance_mm"] - 1e-9, f"{key}: header off the west edge"
        assert x1 <= v["W"] / 2 - PROCESS["edge_clearance_mm"] + 1e-9, f"{key}: header off the east edge"
        assert v["hdr_y"] + pad_r <= v["H"] / 2 - PROCESS["edge_clearance_mm"] + 1e-9, (
            f"{key}: header row is off the south edge")
        v["area_mm2"] = v["W"] * v["H"]


_self_check()


def select(argv=None):
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("--variant", default="base")
    known, _ = ap.parse_known_args(argv if argv is not None else sys.argv[1:])
    if known.variant not in VARIANTS:
        raise SystemExit(f"unknown variant {known.variant!r}; "
                         f"known: {', '.join(sorted(VARIANTS))}")
    return known.variant, VARIANTS[known.variant]


if __name__ == "__main__":
    for k, v in VARIANTS.items():
        print(f"{k:6s} {v['W']:5.2f} x {v['H']:5.2f} mm = {v['area_mm2']:6.1f} mm^2")
