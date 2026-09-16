#!/usr/bin/env python3
"""Generate the board for buck-tpsm33610.

MUST run under KiCad's bundled interpreter, the only one that can import pcbnew:

  P=/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3
  $P gen_pcb.py [--variant base] [--stage place|full]

GENERATED ARTEFACT -- this script is the source of truth. pcbnew edits are
overwritten on the next run. Close pcbnew before running.

`--stage place` stops after placement and the board outline: it is the floorplan
review artefact, and nothing here routes or pours until that has been rendered
and read. `--stage full` is the complete board.

The board is built FROM THE EXPORTED NETLIST, not from a second hand-written
table, which is what makes --schematic-parity a structural check rather than an
aspiration.
"""

import argparse
import hashlib
import json
import subprocess
import pathlib
import re
import sys

try:
    import wx
    # pcbnew's zone filler and several geometry calls reach into wxWidgets, which
    # asserts "create wxApp before calling this" from a bare script.
    if not wx.GetApp():
        _APP = wx.AppConsole()
    import pcbnew
except ImportError:
    sys.exit("pcbnew not importable -- run with KiCad's bundled python3 (see docstring)")

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import variants   # noqa: E402

VKEY, V = variants.select()
NAME = V["name"]
OUT = HERE / f"{NAME}.kicad_pcb"
NETLIST = HERE / f"{NAME}.net"
PRJ_FP = HERE / "lib" / "buck-tpsm33610.pretty"
KI_FP = pathlib.Path("/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints")

_ap = argparse.ArgumentParser(add_help=False)
_ap.add_argument("--stage", default="full", choices=("place", "full"))
_ap.add_argument("--variant", default="base")
STAGE = _ap.parse_known_args()[0].stage

ORG = pcbnew.VECTOR2I_MM(100.0, 100.0)   # board (0,0) on the KiCad page

W, H = V["W"], V["H"]
P = variants.PROCESS

# ============================================================================ floorplan
#
# Board coordinates are centred on the board: X east, Y SOUTH (KiCad's sense).
# Positions below are written RELATIVE TO U1 and shifted by V["u1"], because
# every placement decision here is a decision about distance to a U1 pin.
#
# Redone from scratch 2026-09-13 ("make the board smaller"): 13.7 x 12.45 ->
# 10.2 x 10.05 -> 8.91 x 10.825, then 9.91 x 10.825 once it had to be routable,
# then 9.91 x 12.525 on 2026-09-16 to open the Y gaps (see HEIGHT, below).
#
# U1 is rotated 90 degrees and sits in the NORTH-EAST corner, 0.25 mm from both
# edges: those two faces carry only SW and BOOT, which take no copper beyond the
# land, so nothing is lost by pressing them against the outline. The pin row
# PGOOD EN VIN VOUT faces SOUTH at the header; FB GND MODE and the VCC corner
# face WEST at the small parts.
#
#   south, one power row, west->east, lined up over the header:
#       C1  CIN bulk   GND west | VIN east   VIN pad over J1.1
#       C4  COUT       GND west | VOUT east  GND over J1.2, VOUT over J1.3
#       VIN runs from R4's VIN pad west ABOVE C4 to C1; VOUT drops straight from
#       the land through C4 to J1.3. The two never cross; GND pads meet in the
#       middle over J1.2 and every GND reaches B.Cu by via.
#   under the pin row:
#       R4  straddles EN and VIN (EN west pad, VIN east pad)
#       C2  CIN HF, F.Cu, directly below R4: VIN pad under R4's VIN pad, GND
#           pad west with TWO vias to the plane. The VIN run to C1 passes BELOW
#           C2 and above C4, which is what pushed the power row 0.8 mm south.
#           The input loop is C2.1 -> R4.1 -> pin 3 on F.Cu, and pin 10 -> via ->
#           plane -> those two vias back: the return runs UNDER the forward run,
#           2.37 mOhm end to end, and no B.Cu signal crosses it.
#   west face, FIVE ROWS, one per west-face pin, each part's EAST pad on that
#   pin's net and its WEST pad on the other. The row order is the pin order, so
#   no escape crosses another, and the 0.48 mm channel between each part's own
#   two pads is a free north-south lane:
#       C3  CVCC        VCC | GND   (pin 8,  u-rel y -1.52)
#       R1  RFBT        FB  | VOUT  (pin 9,  u-rel y -0.2475, 0.25 mm south of
#                                    the pin: that opens the VCC channel below C3)
#       R6  MODE strap  MODE| GND   (pin 11, u-rel y  0.7995)
#       R3  PGOOD p-up  PG  | VCC   (pin 1,  u-rel y  1.7495)
#       R5  EN divider  EN  | GND   (DNP,    u-rel y  2.7505, on the EN run to R4)
#   The last three sit 0.25 mm SOUTH of the pin rows they serve (2026-09-16), so
#   MODE and PGOOD leave their U1 pins level and then jog 45 deg down into the
#   row. That jog is the price of the courtyard fix; FB does not need one
#   because R1 did not move.
#   VCC leaves C3 westward between the C3 and R1 rows, turns south down the lane
#   between R1's and R6's own pads, and lands on R3's VCC pad -- the one crossing
#   on this board that would otherwise need a via, done in 0.15 mm of copper.
#   DNP options: C6 (CFF)
#   and R2 (RFBB) lie in the band between the EN row and C1, fed by the FB and
#   VOUT vias. That band is the only place three 0402s and two vias fit.
#   B.Cu solder pads (Fab, 2026-09-13 "move the MODE/PGOOD/EN pads on the
#       backside"; then "move the pads to the top edge"): MODE PG EN along the
#       north edge, labels under them on B.SilkS. PGOOD is labelled "PG" (Fab).
#       Their x positions are set by their B.Cu runs, not by the silk: each run
#       climbs its own lane and enters its pad from below without crossing.
#
# WIDTH, 2026-09-13: 8.91 -> 9.91 mm. The 8.91 mm board is not routable -- see
# variants.py for the finding and the four scouts behind it. The millimetre went
# on the WEST side only, so nothing east of the west cluster moved.
#
# HEIGHT, 2026-09-16: 10.825 -> 12.525 mm. Fab: "fix the cortyards overlaps in Y
# directions, increase board size". Eight of the eleven courtyard overlaps were
# parts stacked too close in Y. They cannot be fixed by stretching the outline
# alone -- two overlapping courtyards share a Y range by definition, so no cut
# line separates them; the parts themselves have to move apart. The moves are
# applied as FIVE RIGID GROUPS, not per part, so the geometry inside a group is
# untouched and only the runs BETWEEN groups stretch:
#       R3 R4 R5 R6 JP1  +0.25   (clears R1-R6 and R4-U1; R4 and R5 move
#                                 together so the EN run stays horizontal)
#       C6 R2            +0.30   (clears R5)
#       C2 C4            +0.50   (clears R4; C4 moves WITH C2 so the 0.70 mm
#                                 VIN channel between them survives)
#       C4               +0.10 more, widening that channel to 0.80 mm -- see
#                                 the VIN neck note in TRACKS
#       C1               +0.95   (clears C2)
#       J1               +1.70   (clears C4 and C1) -- and J1 is the southern
#                                 limit, so the board grew by exactly this much,
#                                 all of it on the SOUTH edge. U1, C3, R1 and the
#                                 three B.Cu solder pads keep their distance to
#                                 the north edge; not one of their tracks moved.
# Three overlaps REMAIN and are not bugs: C3-U1, C1-C4 and C6-R2 are side-by-side
# pairs whose cheapest escape is X, not Y. Growing the board downwards cannot
# reach them, and shrinking a courtyard to silence them would be a mute button --
# each of those courtyards is the part's real body plus the standard 0.25 mm.
#
UX, UY = V["u1"]


def _u(x, y, r):
    return (round(UX + x, 4), round(UY + y, 4), r)


POS = {
    "U1": _u(0.00, 0.00, 90),

    "R4": _u(-0.90, 4.410, 180),   # swapped with C2 (Fab, 2026-09-16)
    "C2": _u(-0.975, 3.070, 180),    # CIN HF hard against U1's pin row. R4 is a
                                     # 0R EN pull-up carrying ~10 nA and was
                                     # occupying this slot; TI SNVSCS7E 8.5.1 item
                                     # 1 wants the input cap here instead.
    "C1": _u(-4.390, 6.165, 180),    # rot 180 (Fab, 2026-09-16): VIN is the EAST
                                     # pad, GND the west one. That faces the VIN
                                     # pad at U1 instead of away from it and takes
                                     # /VIN C1.1<->U1.3 from 6.134 to 4.642 mOhm,
                                     # paying 0.39 mOhm on GND J1.2<->U1.10 (1.427
                                     # -> 1.818, against a 10 mOhm budget).
                                     # BOTH ends measured at --grid 0.1: the 0.2 mm
                                     # default under-resolves this board (it makes
                                     # the GND solve singular outright) and inflated
                                     # the same path to 12.259 mOhm.
                                     # 0.19 mm south: the most
                                     # that fits -- J1's courtyard starts 0.190 mm
                                     # below C1's, and its PTH pads 1.45 mm below.
    "C4": _u( 0.015, 6.175, 180),

    # ---- the west cluster, re-placed 2026-09-13 for routability (see the
    # header comment). Five ROWS, one per U1 west-face pin, each part turned so
    # that its EAST pad carries the pin's net and its WEST pad the other one:
    # that fixes the escape direction and leaves the 0.48 mm channel between
    # each part's own pads free as a north-south lane -- which is how VCC gets
    # from C3 past FB and MODE down to R3 without a layer change.
    "C3": _u(-4.325, -1.52, 180),    # VCC row, east pad at pin 8 (0.45 mm
                                     # west of U1, 2026-09-16: its courtyard
                                     # overlapped the module land by 0.365)
    "R1": _u(-4.245, -0.2475, 0),    # FB   row: VOUT west | FB east
    "R6": _u(-4.245,  0.7995, 180),  # MODE row: GND  west | MODE east
    "R3": _u(-4.245,  1.7495, 0),    # PG   row: VCC  west | PGOOD east
    "R5": _u(-4.245,  2.7505, 180),  # EN   row: GND  west | EN east   (DNP)

    # JP1, the MODE solder jumper (Fab, 2026-09-13), stands vertically in the
    # west margin the extra millimetre bought, VCC pad NORTH on the R3 feed and
    # MODE pad south. It is exactly where R7 stood and on R7's pad centres --
    # that is why replacing the pull-up with a jumper moved no copper. Its pads
    # are 0.80 x 0.80 on 1.00 mm pitch against the 0402's 0.54 x 0.64 on 1.02,
    # so both old track ends still land well inside the new lands.
    "JP1": _u(-6.240,  1.2595, 90),
    "C6": _u(-5.680,  3.7725, 0),    # CFF:  VOUT west | FB east (0.15 mm
                                     # west of R2, 2026-09-16: courtyards)
    "R2": _u(-3.735,  3.7725, 0),    # RFBB: FB   west | GND east

    # Solder pads on B.Cu along the north edge (Fab, 2026-09-13), labels under
    # them on B.SilkS. Block pitch is set by label width (MODE 2.30, PG 1.04,
    # EN 0.99 mm of ink) with 0.6 mm between labels: at 0.15 mm the render read
    # as one word. The short "PG" keeps the EN pad clear of the SW land above.
    # PG and EN moved east of their vias' lanes so each B.Cu run reaches its pad
    # without crossing another; EN's pad sits under the BOOT/SW6 pins, 1.6 mm of
    # FR4 away (~0.01 pF to SW, against an EN node held by R4).
    "TP3": _u(-4.84, -1.50, 0),     # MODE
    "TP2": _u(-2.385, -1.50, 0),    # PGOOD, silk "PG"
    "TP1": _u(-0.735, -1.50, 0),    # EN

    # J1 is positioned by pad 1 (VIN); the library footprint runs its pins along
    # +Y, so it is rotated to run them east. build() asserts where they landed.
    "J1": (V["hdr_x0"], V["hdr_y"], 90),
}
# Silk labels for the solder pads: (text, dx, dy, angle) from the pad centre.
# Labels centred under each pad (south of it): pad half-height 0.5 + 0.15 gap +
# half the 0.7 mm ink height at 0.6 mm text. Centred, so the offset is the same
# mirrored on B.SilkS.
TP_LABELS = {"TP3": ("MODE", 0.0, 1.08, 0, "center"),
             "TP2": ("PG", 0.0, 1.08, 0, "center"),      # Fab: "PGOOD = PG (silk)"
             "TP1": ("EN", 0.0, 1.08, 0, "center")}
# Every component on F.Cu (Fab, 2026-09-13: "put all smd parts on the front
# side"); only the three bare solder pads stay on B.Cu. This gives up TI's C2
# under the VIN/GND lands (SNVSCS7E Fig 8-21): C2 now sits below R4 and returns
# through a GND via, a larger hot loop than the through-board one.
BOTTOM = {"TP1", "TP2", "TP3"}

SIG_W = 0.25
PWR_W = 0.50
VIA_D, VIA_DRILL = P["via_pad_mm"], P["via_drill_mm"]

# ============================================================================ routing
#
# LAYER PLAN, committed before the first track:
#   F.Cu  every component, every signal, the VIN run and the VOUT pour. No
#         preferred direction: the escapes are radial off one package face, and
#         the four west rows make their own east-west lanes.
#   B.Cu  the GND plane, plus exactly six short signal runs that cannot exist on
#         F.Cu: MODE, PGOOD and EN down to their solder pads, FB out to the DNP
#         divider, and VOUT from the header pin back to the divider. Each one is
#         a named crossing, not a router's convenience.
#   Vias  one class, 0.50/0.25 mm, through-hole; on a 2-layer board every via is
#         a full-stack via by definition.
#
# The plane is what pays for those six runs, so where they cut it is the whole
# argument. The input hot loop returns C2.2 -> via -> B.Cu -> via -> U1.10, and
# that path runs EAST (under the VIN run, x 1.7..2.0 in board coords): none of
# the six touch it. The B.Cu signal lanes sit west of x 0.5 and north of the
# GND via at U1.10, which is why they cost plane where no return current flows.
#
# All routing coordinates below are U1-RELATIVE, the same frame as POS, so the
# board can grow at an edge without a single track moving.
F_CU, B_CU = "F", "B"

# (net, layer, width_mm, [(x, y), ...]) -- a polyline, one PCB_TRACK per span.
TRACKS = [
    # ---- VIN: header -> C1 -> C2 -> R4 -> pin 3, the widest path that fits.
    # The 0.39 mm neck is the run between C2's GND pad and C4's: 0.70 mm of
    # channel, 0.155 mm of clearance either side. At 35 um that is ~1.2 A at a
    # 20 K rise, over 2.6 mm -- the input current at the 3 V end of the range.
    ("/VIN", F_CU, 0.30, [(-0.520, 1.8625), (-0.520, 3.0700)]),          # pin 3 -> C2.1
    ("/VIN", F_CU, 0.40, [(-0.390, 3.3000), (-0.390, 4.4100)]),          # C2.1 -> R4.1
    # Split into three widths, 2026-09-16: only the MIDDLE leg is in the 0.70 mm
    # channel between C2's GND pad and C4's. The two vertical legs are in open
    # copper and were only 0.39 because they used to share one polyline -- and
    # after C1 moved 0.95 mm south this path went 4.51 -> 5.91 mOhm, over its
    # 5 mOhm budget.
    ("/VIN", F_CU, 0.40, [(-0.390, 4.4100), (-0.390, 5.0025)]),          # R4.1 -> channel
    # R4 now sits in the old C2/C4 channel, so the neck is pinched to 0.245 mm
    # between R4's lands (bottom 4.720) and C4's (top 5.275) until it clears
    # C4 at x -2.035, after which C1 and the /FB via allow 0.44 again.
    ("/VIN", F_CU, 0.245, [(-0.390, 5.0025), (-2.200, 5.0025)]),         # pinched
    ("/VIN", F_CU, 0.245, [(-2.200, 5.0025), (-2.400, 4.889)]),          # jog
    # C1 rotated 180 (2026-09-16), so its VIN pad is the EAST one: the run stops
    # 2.95 mm short of where it used to and never crosses under the body.
    ("/VIN", F_CU, 0.44, [(-2.400, 4.889), (-3.160, 4.889)]),            # -> C1.1 (east)
    # starts at 5.050, not 4.889: at 0.72 wide the round end cap reaches 0.36 mm
    # below the start point, and /EN's top edge is at 4.485 -- starting on the
    # corner left 0.044 mm. 5.050 puts the cap at 4.690, 0.205 mm clear, and the
    # endpoint still sits inside the 0.44 horizontal (4.669..5.109).
    ("/VIN", F_CU, 0.72, [(-3.160, 5.050), (-3.160, 5.800)]),            # into C1.1
    ("/VIN", F_CU, 0.70, [(-3.160, 6.500), (-3.160, 8.600), (-4.200, 8.600),
                          (-4.200, 9.1745)]),                            # C1.1 -> J1.1

    # ---- GND: pad stubs onto vias. Everything else is the pour.
    ("GND", F_CU, 0.50, [(-0.935, 0.1125), (-0.435, 0.1125)]),           # U1.10 -> via, east
    ("GND", F_CU, 0.40, [(-5.500, -1.5200), (-5.850, -1.5200)]),         # C3.2  -> via
    ("GND", F_CU, 0.50, [(-2.235, 3.0725), (-2.435, 3.0725)]),           # C2.2  -> via
    ("GND", F_CU, 0.40, [(-0.785, 6.1625), (0.065, 6.1625)]),            # C4.2  -> via
    ("GND", F_CU, 0.40, [(-5.850, 6.3025), (-5.850, 7.3400)]),           # C1.2  -> via
    ("GND", F_CU, 0.80, [(-1.435, 6.3625), (-1.435, 9.1745)]),           # C4.2  -> J1.2

    # ---- VOUT: the pour carries U1.4 -> C4 -> J1.3. These two stubs land the
    # B.Cu sense run on R1 and C6.
    ("/VOUT", F_CU, 0.25, [(-5.585, -0.2475), (-4.735, -0.2475)]),       # via -> R1.1
    ("/VOUT", F_CU, 0.25, [(-6.190, 3.7725), (-5.950, 3.7725)]),         # via -> C6.1
    # VOUT is sensed at J1.3, the point of regulation, and carried on B.Cu round
    # the south and west margins to the divider. It carries no load current --
    # with R1 fitted at 0 R it is the FB connection itself -- and it is the one
    # run that crosses the whole board, so it is kept outside every loop: south
    # of the output caps, west of everything.
    ("/VOUT", B_CU, 0.15, [(1.22, 9.1745), (1.22, 7.9625), (-6.365, 7.9625),
                           (-6.365, 3.7725), (-6.190, 3.7725)]),
    ("/VOUT", B_CU, 0.15, [(-6.365, 3.7725), (-6.365, -0.2475), (-5.585, -0.2475)]),

    # ---- VCC: pin 8 -> C3, then south past FB and MODE to R3 and JP1. The only
    # reason this exists on F.Cu is the lane between each row part's own pads.
    ("/VCC", F_CU, 0.30, [(-1.935, -1.5205), (-3.300, -1.5205)]),        # pin 8 -> C3.1
    ("/VCC", F_CU, 0.15, [(-3.465, -1.2375), (-3.465, -0.8075), (-4.245, -0.8075),
                          (-4.245, 1.7495), (-4.585, 1.7495)]),          # C3.1 -> R3.1
    ("/VCC", F_CU, 0.20, [(-4.885, 1.7495), (-6.235, 1.7495)]),          # R3.1 -> JP1.1

    # ---- the four west-face escapes, each into its row's east pad.
    ("/FB", F_CU, 0.15, [(-2.135, -0.4375), (-2.735, -0.4375),
                         (-2.935, -0.2375), (-3.735, -0.2375)]),         # pin 9  -> R1.2
    ("/MODE", F_CU, 0.15, [(-2.135, 0.4995), (-2.935, 0.4995),
                           (-3.185, 0.7495), (-3.735, 0.7495)]),          # pin 11 -> R6.1
    ("/MODE", F_CU, 0.20, [(-5.875, 0.7495), (-6.240, 0.7495)]),         # via    -> JP1.2
    ("/PGOOD", F_CU, 0.15, [(-2.035, 1.4995), (-2.935, 1.4995),
                            (-3.185, 1.7495), (-3.735, 1.7495)]),         # pin 1  -> R3.2
    ("/EN", F_CU, 0.25, [(-1.150, 1.8625), (-1.250, 2.1800), (-1.250, 2.3000),
                         (-0.975, 2.5000), (-0.975, 3.8500),
                         (-1.410, 4.2800)]),                             # pin 2 -> R4.2
    ("/EN", F_CU, 0.15, [(-1.535, 4.4100), (-3.735, 4.4100),
                         (-3.735, 2.9000)]),                             # R4.2 -> R5.1

    # ---- B.Cu: the six named crossings. MODE, PGOOD and EN run north to their
    # solder pads in three lanes that never cross; MODE branches west along the
    # north margin to TP3 and back down to JP1.
    ("/MODE", B_CU, 0.15, [(-2.935, 0.4995), (-2.435, -0.0005), (-2.435, -0.7375),
                           (-5.085, -0.7375), (-5.085, -1.2375)]),       # via -> TP3
    ("/MODE", B_CU, 0.15, [(-5.085, -0.7375), (-5.085, 0.7495), (-5.875, 0.7495)]),
    ("/PGOOD", B_CU, 0.15, [(-2.935, 1.4995), (-2.035, 0.5995), (-2.035, -1.1375)]),
    ("/EN", B_CU, 0.15, [(-1.250, 2.1800), (-1.635, 1.8000), (-1.635, -1.1875),
                         (-0.735, -1.1875)]),
    ("/FB", B_CU, 0.15, [(-2.935, -0.2375), (-3.585, 0.4125), (-3.585, 4.2625),
                         (-4.735, 4.2625)]),                             # via -> C6.2/R2.1
    ("/FB", F_CU, 0.20, [(-4.735, 4.2625), (-5.035, 3.9625)]),           # via -> C6.2
    ("/FB", F_CU, 0.20, [(-4.735, 4.2625), (-4.435, 3.9625)]),           # via -> R2.1

    # ---- SW: pins 5 and 6 are one internal node, so this stub is the whole net.
    # SNVSCS7E p.5 forbids anything else on it ("keep the amount of copper on
    # these pins to a minimum"), which is why it is 0.7 mm of land-to-land and
    # why the F.Cu pour is notched away from both lands.
    ("/SW", F_CU, 0.30, [(-0.635, -1.4375), (0.065, -1.4375)]),
]

# (net, (x, y)) -- every via is a layer ASSIGNMENT with a stated destination.
VIAS = [
    ("GND", (-0.435, 0.1125)),     # U1.10, east of the land: the hot-loop return
    ("GND", (-2.435, 3.0725)),     # C2.2, the other end of that loop
    ("GND", (-2.985, 3.0725)),     # a second one beside it: two 0.25 mm
                                   # barrels in parallel on the highest-di/dt
                                   # return this board has
    ("GND", (0.065, 6.1625)),      # C4.2, the output loop
    ("GND", (-5.850, 7.34)),       # C1.2, NORTH of the land (C1 rotated 180)
    ("GND", (-5.89, 2.9005)),      # west margin, same (0.4 mm south of where
                               # it was: JP1 moved down onto it)
    ("GND", (-5.850, -1.5200)),    # C3.2, stitching CVCC's ground pocket. Its
                                   # predecessor at (-6.435, -1.5375) was proved
                                   # redundant at 9.41 mm wide and became
                                   # load-bearing again at 9.01.
    ("GND", (-5.435, 1.2495)),     # the MODE row pocket: R6.2 sits in a
                                   # pour region the rows and the VCC feed
                                   # cut off from every other one
    ("/EN", (-1.250, 2.1800)),     # -> TP1
    ("/PGOOD", (-2.935, 1.4995)),  # -> TP2
    ("/MODE", (-2.935, 0.4995)),   # -> TP3
    ("/MODE", (-5.875, 0.7495)),   # -> JP1.2. x is set by the DRILL, not the
                                   # annulus: at 9.41 mm wide JP1 sits where this
                                   # via used to, and a 0.25 mm hole inside a pad
                                   # you bridge by hand drains the solder. The
                                   # ring may overlap JP1.2 (same net); the hole
                                   # clears its east edge by 0.035 mm.
    ("/FB", (-2.935, -0.2375)),    # -> C6.2, R2.1
    ("/FB", (-4.735, 4.2625)),     # the same run's far end
    ("/VOUT", (-6.190, 3.7725)),   # -> C6.1
    ("/VOUT", (-5.585, -0.2475)),  # -> R1.1
]

# Zone outlines, U1-relative. The GND pour on F.Cu is the board minus a notch
# over the SW lands: SNVSCS7E p.5 says to keep copper on SW to a minimum, and a
# pour that close is copper. B.Cu is left SOLID under SW -- 1.6 mm of FR4 away,
# that plane is the return the switching node needs, and breaking it would cost
# more than the ~0.05 pF it saves.
BOARD_NW = (-6.44, -2.0)       # board rect inset by the copper-to-edge rule
BOARD_SE = (2.07, 10.025)
SW_NOTCH_W, SW_NOTCH_S = -1.335, 0.1005
GND_F_OUTLINE = [BOARD_NW, (SW_NOTCH_W, -2.0), (SW_NOTCH_W, SW_NOTCH_S),
                 (BOARD_SE[0], SW_NOTCH_S), BOARD_SE, (BOARD_NW[0], BOARD_SE[1])]
GND_B_OUTLINE = [BOARD_NW, (BOARD_SE[0], BOARD_NW[1]), BOARD_SE, (BOARD_NW[0], BOARD_SE[1])]
# VOUT owns the east strip: U1.4, C4 and J1.3 sit in it, and it is the only
# copper on the board wide enough to spread U1's heat.
VOUT_OUTLINE = [(0.305, 0.3625), (2.07, 0.3625), (2.07, 10.02), (0.305, 10.02)]


def mm(v):
    return pcbnew.FromMM(v)


def Pt(x, y):
    return pcbnew.VECTOR2I(ORG.x + mm(x), ORG.y + mm(y))


def uid(*parts):
    h = hashlib.sha1((NAME + "/pcb/" + "/".join(map(str, parts))).encode()).hexdigest()
    return h


# ============================================================= netlist (parity source)
def _block(text, start):
    depth, i, in_str, esc = 0, start, False, False
    while i < len(text):
        c = text[i]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
        else:
            if c == '"':
                in_str = True
            elif c == "(":
                depth += 1
            elif c == ")":
                depth -= 1
                if depth == 0:
                    return text[start:i + 1]
        i += 1
    raise ValueError("unbalanced s-expression in the netlist")


def _props(body):
    """{name: value} walking each (property ...) block.

    A block walk, not one cross-block regex: pairing a (name ...) with a later
    (value ...) across property boundaries returns a plausible wrong answer --
    here it would read a neighbouring field as the DNP flag.
    """
    out = {}
    for m in re.finditer(r'\(property\s', body):
        blk = _block(body, m.start())
        n = re.search(r'\(name\s+"([^"]*)"\s*\)', blk)
        if not n:
            continue
        v = re.search(r'\(value\s+"([^"]*)"\s*\)', blk)
        out[n.group(1)] = v.group(1) if v else ""
    return out


NOT_A_FIELD = {"Reference", "Value", "Footprint", "Datasheet", "Description",
               "Sheetname", "Sheetfile", "exclude_from_bom", "dnp"}


def read_netlist():
    text = NETLIST.read_text()
    comps = {}
    for m in re.finditer(r'\(comp\s+\(ref\s+"([^"]+)"\s*\)', text):
        body = _block(text, m.start())
        val = re.search(r'\(value\s+"([^"]*)"\s*\)', body)
        fp = re.search(r'\(footprint\s+"([^"]*)"\s*\)', body)
        props = _props(body)
        comps[m.group(1)] = {
            "value": val.group(1) if val else "",
            "footprint": fp.group(1) if fp else "",
            "dnp": props.get("DNP") == "yes",
            "fields": {k: v for k, v in props.items()
                       if k not in NOT_A_FIELD and not k.startswith("ki_")},
        }
    nets = {}
    for m in re.finditer(r'\(net\s+\(code\s+"\d+"\s*\)\s*\(name\s+"([^"]+)"\s*\)', text):
        body = _block(text, m.start())
        nets[m.group(1)] = re.findall(
            r'\(node\s+\(ref\s+"([^"]+)"\s*\)\s*\(pin\s+"([^"]+)"\s*\)', body)

    # A partial parse must never read as a clean one: count what was extracted
    # against what the file contains.
    if not comps or not nets:
        raise SystemExit("netlist parsed to zero components or zero nets -- "
                         "an empty parse is not a clean parse; re-run gen_sch.py")
    n_comp = len(re.findall(r'\(comp\s+\(ref\s', text))
    n_node = len(re.findall(r'\(node\s+\(ref\s', text))
    if len(comps) != n_comp:
        raise SystemExit(f"parsed {len(comps)} components, file has {n_comp}")
    if sum(len(v) for v in nets.values()) != n_node:
        raise SystemExit("node count mismatch between the parse and the file")
    for ref, spec in comps.items():
        if not spec["footprint"]:
            raise SystemExit(f"{ref}: no footprint in the netlist")
    return comps, nets


COMPS, NETS = read_netlist()
import project_settings   # noqa: E402  (after the netlist guard, on purpose)


# ================================================================================ build
def build():
    board = pcbnew.CreateEmptyBoard()

    netmap = {}
    for name in sorted(NETS):
        ni = pcbnew.NETINFO_ITEM(board, name)
        board.Add(ni)
        netmap[name] = ni
    pad_net = {}
    for name, nodes in NETS.items():
        for ref, pad in nodes:
            pad_net[(ref, pad)] = name

    if sorted(POS) != sorted(COMPS):
        raise SystemExit(f"placement/netlist mismatch: only-in-POS="
                         f"{sorted(set(POS) - set(COMPS))} "
                         f"only-in-netlist={sorted(set(COMPS) - set(POS))}")

    for ref, spec in sorted(COMPS.items()):
        lib, fpname = spec["footprint"].split(":", 1)
        # Two nicknames, one directory: "Connector_buck-tpsm33610" exists so that
        # J1's stock symbol filter ("Connector*:*_1x??_*") admits this project's
        # own derived header land without editing the symbol.
        libdir = (PRJ_FP if lib in ("buck-tpsm33610", "Connector_buck-tpsm33610")
                  else (KI_FP / f"{lib}.pretty"))
        fp = pcbnew.FootprintLoad(str(libdir), fpname)
        if fp is None:
            raise SystemExit(f"{ref}: footprint {spec['footprint']} not found in {libdir}")
        x, y, rot = POS[ref]
        board.Add(fp)
        # The FPID must carry the library nickname, or --schematic-parity reports
        # every footprint as "doesn't match footprint given by symbol".
        fp.SetFPID(pcbnew.LIB_ID(lib, fpname))
        fp.SetPosition(Pt(x, y))
        fp.SetOrientationDegrees(rot)
        if ref in BOTTOM:
            fp.Flip(Pt(x, y), False)
        fp.SetReference(ref)
        fp.SetValue(spec["value"])
        fp.SetExcludedFromBOM(False)
        if spec["dnp"]:
            fp.SetDNP(True)
        # Copy the symbol's user fields onto the footprint. KiCad 10's
        # --schematic-parity reports every symbol field the footprint lacks as
        # footprint_symbol_field_mismatch, and reports only the FIRST per
        # footprint, so fixing them off a DRC report converges one per run.
        for fname, fval in sorted(spec["fields"].items()):
            f = pcbnew.PCB_FIELD(fp, pcbnew.FIELD_T_USER, fname)
            f.SetText(fval)
            f.SetVisible(False)
            f.SetLayer(pcbnew.B_Fab if ref in BOTTOM else pcbnew.F_Fab)
            f.SetTextSize(pcbnew.VECTOR2I(mm(0.5), mm(0.5)))
            f.SetTextThickness(mm(0.08))
            fp.Add(f)
        missing = [k for k in spec["fields"] if not fp.HasField(k)]
        if missing:
            raise SystemExit(f"{ref}: symbol fields {missing} did not attach")
        # Reference designators go on F.Fab, not silk: at Aisler's 0.8 mm legible
        # minimum a refdes is wider than most of the parts on this board.
        for item in (fp.Reference(), fp.Value()):
            item.SetLayer(pcbnew.B_Fab if ref in BOTTOM else pcbnew.F_Fab)
            item.SetTextSize(pcbnew.VECTOR2I(mm(0.5), mm(0.5)))
            item.SetTextThickness(mm(0.08))
        for pad in fp.Pads():
            key = (ref, pad.GetNumber())
            if key in pad_net:
                pad.SetNet(netmap[pad_net[key]])
            # The RDN0011B land is drawn to the datasheet, and its own pad-to-pad
            # gaps are 0.100 mm -- below the 0.15 mm design clearance, and not
            # ours to widen. Scope the exception to U1's pads instead of relaxing
            # the global rule: KiCad resolves a pair to the LARGER of the two
            # clearances, so this applies only between two U1 pads, and U1 against
            # any track or pour still gets the full 0.15 mm.
            if ref == "U1":
                pad.SetLocalClearance(mm(0.09))

    fps = {fp.GetReference(): fp for fp in board.Footprints()}

    def pad_xy(ref, num):
        for p in fps[ref].Pads():
            if p.GetNumber() == str(num):
                pos = p.GetPosition()
                return (round(pcbnew.ToMM(pos.x - ORG.x), 4),
                        round(pcbnew.ToMM(pos.y - ORG.y), 4))
        raise KeyError(f"{ref} has no pad {num}")

    # ---- the header pads must have landed where the floorplan says they did.
    #      Rotation sign conventions are exactly the kind of thing that looks
    #      right in a render and is mirrored in the gerbers.
    for i, nname in enumerate(variants.HDR_NETS):
        px, py = pad_xy("J1", i + 1)
        wx, wy = V["hdr_x0"] + i * variants.HDR_PITCH, V["hdr_y"]
        if abs(px - wx) > 1e-3 or abs(py - wy) > 1e-3:
            raise SystemExit(f"J1 pad {i+1} landed at ({px}, {py}), floorplan says "
                             f"({wx}, {wy}) -- header rotation is wrong")
        got = pad_net[("J1", str(i + 1))].lstrip("/")
        if got != nname:
            raise SystemExit(f"J1 pad {i+1} is on net {got}, floorplan says {nname}")

    # ---- header silk. The library outline is a 2.54 mm box around the pins: on
    #      this board it cuts across the C1 and C4 pads and runs off the south
    #      edge, so it is dropped (the square pad still marks pin 1). The pin
    #      names go on B.SilkS instead, where the underside above the header row
    #      is empty. 0.6 mm, the same size as the solder-pad labels, keeps all
    #      three on one row (VOUT 2.21 + GND 1.70 mm of ink on 2.54 mm pitch);
    #      VOUT is pulled 0.3 mm west to stay off the east edge.
    hdr_label_off = {"VIN": (0.0, -1.45), "GND": (0.0, -1.45), "VOUT": (-0.20, -1.45)}
    # "VOUT" at 0.7 mm is 2.58 mm of ink on a 2.54 mm pitch: it ran off the
    # east edge and into "GND". "OUT" is three glyphs like "GND", and the pin
    # it names is the only output on the board.
    hdr_label_text = {"VIN": "VIN", "GND": "GND", "VOUT": "OUT"}
    for i, nname in enumerate(variants.HDR_NETS):
        px, py = pad_xy("J1", i + 1)
        px, py = px + hdr_label_off[nname][0], py + hdr_label_off[nname][1] + 1.45
        t = pcbnew.PCB_TEXT(board)
        t.SetText(hdr_label_text[nname])
        t.SetLayer(pcbnew.B_SilkS)
        t.SetMirrored(True)
        t.SetTextSize(pcbnew.VECTOR2I(mm(P["silk_height_mm"]), mm(P["silk_height_mm"])))
        t.SetTextThickness(mm(P["silk_thickness_mm"]))
        t.SetHorizJustify(pcbnew.GR_TEXT_H_ALIGN_CENTER)
        t.SetVertJustify(pcbnew.GR_TEXT_V_ALIGN_CENTER)
        t.SetPosition(Pt(px, py - 1.45))
        board.Add(t)

    # ---- silk labels on the solder pads (Fab, 2026-09-13). 0.6 mm text: under
    #      Aisler's 0.8 mm minimum, a rule break Fab authorised the same day.
    for ref, (text, ldx, ldy, lang, just) in TP_LABELS.items():
        px, py = pad_xy(ref, 1)
        t = pcbnew.PCB_TEXT(board)
        t.SetText(text)
        t.SetLayer(pcbnew.B_SilkS if ref in BOTTOM else pcbnew.F_SilkS)
        t.SetMirrored(ref in BOTTOM)
        t.SetTextSize(pcbnew.VECTOR2I(mm(P["silk_height_mm"]), mm(P["silk_height_mm"])))
        t.SetTextThickness(mm(P["silk_thickness_mm"]))
        t.SetTextAngleDegrees(lang)
        t.SetHorizJustify({"left": pcbnew.GR_TEXT_H_ALIGN_LEFT,
                           "center": pcbnew.GR_TEXT_H_ALIGN_CENTER}[just])
        t.SetVertJustify(pcbnew.GR_TEXT_V_ALIGN_CENTER)
        t.SetPosition(Pt(px + ldx, py + ldy))
        board.Add(t)

    # ---- board outline
    for (ax, ay), (bx, by) in (((-W / 2, -H / 2), (W / 2, -H / 2)),
                               ((W / 2, -H / 2), (W / 2, H / 2)),
                               ((W / 2, H / 2), (-W / 2, H / 2)),
                               ((-W / 2, H / 2), (-W / 2, -H / 2))):
        seg = pcbnew.PCB_SHAPE(board)
        seg.SetShape(pcbnew.SHAPE_T_SEGMENT)
        seg.SetStart(Pt(ax, ay))
        seg.SetEnd(Pt(bx, by))
        seg.SetLayer(pcbnew.Edge_Cuts)
        seg.SetWidth(mm(0.1))
        board.Add(seg)

    return board, fps, pad_xy, netmap


def _up(x, y):
    """U1-relative mm -> a board point, the same frame TRACKS and VIAS use."""
    return Pt(UX + x, UY + y)


def route(board, netmap):
    """Author every track, via and zone. Generated, so the board is the output
    of this file and never the other way round: an edit made in pcbnew is gone
    on the next run, which is what keeps the layer plan above truthful."""
    lay = {F_CU: pcbnew.F_Cu, B_CU: pcbnew.B_Cu}
    n_seg = 0
    for net, layer, w, pts in TRACKS:
        for a, b in zip(pts, pts[1:]):
            t = pcbnew.PCB_TRACK(board)
            t.SetStart(_up(*a))
            t.SetEnd(_up(*b))
            t.SetWidth(mm(w))
            t.SetLayer(lay[layer])
            t.SetNet(netmap[net])
            board.Add(t)
            n_seg += 1
    for net, (x, y) in VIAS:
        v = pcbnew.PCB_VIA(board)
        v.SetPosition(_up(x, y))
        v.SetViaType(pcbnew.VIATYPE_THROUGH)
        v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
        v.SetWidth(mm(VIA_D))
        v.SetDrill(mm(VIA_DRILL))
        v.SetNet(netmap[net])
        board.Add(v)
    for net, layer, outline, prio in (("GND", pcbnew.F_Cu, GND_F_OUTLINE, 0),
                                      ("GND", pcbnew.B_Cu, GND_B_OUTLINE, 0),
                                      ("/VOUT", pcbnew.F_Cu, VOUT_OUTLINE, 1)):
        z = pcbnew.ZONE(board)
        z.SetLayer(layer)
        z.SetNet(netmap[net])
        o = z.Outline()
        o.NewOutline()
        for x, y in outline:
            p = _up(x, y)
            o.Append(p.x, p.y)
        z.SetLocalClearance(mm(P["clearance_mm"]))
        z.SetMinThickness(mm(P["track_mm"]))
        # Solid, not thermal spokes: on this board the pours ARE the heatsink,
        # and every part on them is reflowed, not hand-soldered.
        z.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)
        z.SetAssignedPriority(prio)
        # An island is copper the fill could not connect to the net. Keeping
        # them would report as unconnected_items -- which is true, and is not
        # a routing defect, so remove them rather than explain them away.
        z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
        board.Add(z)
    return n_seg, len(VIAS)


_FILL_CHILD = r"""
import json, sys
import wx
if not wx.GetApp():
    _a = wx.AppConsole()
import pcbnew
p = sys.argv[1]
b = pcbnew.LoadBoard(p)
pcbnew.ZONE_FILLER(b).Fill(b.Zones())
unfilled = [z.GetNetname() for z in b.Zones() if not z.IsFilled()]
areas = []
for z in b.Zones():
    polys = z.GetFilledPolysList(z.GetLayer())
    areas.append([z.GetNetname(), b.GetLayerName(z.GetLayer()), polys.OutlineCount(),
                  sum(pcbnew.ToMM(pcbnew.ToMM(polys.Outline(i).Area()))
                      for i in range(polys.OutlineCount()))])
pcbnew.SaveBoard(p, b, True)
print("@@" + json.dumps({"unfilled": unfilled, "areas": areas}))
"""

_CONN_CHILD = r"""
import json, sys
import wx
if not wx.GetApp():
    _a = wx.AppConsole()
import pcbnew
b = pcbnew.LoadBoard(sys.argv[1])
b.BuildConnectivity()
cc = b.GetConnectivity()
loose = []
for f in b.Footprints():
    for pad in f.Pads():
        if not pad.GetNetname():
            continue
        reach = {f"{i.GetParentFootprint().GetReference()}.{i.GetNumber()}"
                 for i in cc.GetConnectedItems(pad) if i.Type() == pcbnew.PCB_PAD_T}
        want = {f"{g.GetReference()}.{q.GetNumber()}" for g in b.Footprints()
                for q in g.Pads() if q.GetNetCode() == pad.GetNetCode()}
        reach.add(f"{f.GetReference()}.{pad.GetNumber()}")
        if reach != want:
            loose.append([f"{f.GetReference()}.{pad.GetNumber()}", pad.GetNetname(),
                          sorted(want - reach)])
print("@@" + json.dumps({"ratsnest": cc.GetUnconnectedCount(True), "loose": loose}))
"""


def _child(code, path):
    """Run a pcbnew snippet in a FRESH interpreter and return its JSON payload."""
    r = subprocess.run([sys.executable, "-c", code, str(path)],
                       capture_output=True, text=True)
    line = [l for l in r.stdout.splitlines() if l.startswith("@@")]
    if r.returncode != 0 or not line:
        raise SystemExit(f"fill helper failed (rc={r.returncode}):\n"
                         f"{r.stdout[-2000:]}\n{r.stderr[-2000:]}")
    return json.loads(line[-1][2:])


def fill(path):
    """Fill the pours on the SAVED board, in a SEPARATE PROCESS, and prove it stuck.

    The separate process is the whole point, and a plain reload is NOT enough.
    build() calls pcbnew.CreateEmptyBoard(), which loads KiCad's DEFAULT project
    into this interpreter's settings manager; a later LoadBoard() in the same
    process keeps those defaults instead of reading the .kicad_pro beside the
    board. So an in-process fill pours against KiCad's clearances, not ours.

    Measured 2026-09-16, and this is what it costs: the in-process fill wrote a
    GND F.Cu pour of SIX regions with C3.2 -- CVCC's ground pad -- alone on an
    island connected to nothing, while the identical fill in a clean process
    gives FOUR regions and a fully connected net. It survived because the DRC
    gate ran `--refill-zones`, which re-pours from the project and so reported a
    board that does not match the one on disk. A fill you cannot see is worse
    than no fill: the gerbers come from the file, not from the refill.

    So: pour in a clean child, then ask a SECOND clean child whether every pad
    on every net actually reaches every other pad on that net. Anything loose is
    fatal here, not a warning downstream.
    """
    got = _child(_FILL_CHILD, path)
    if got["unfilled"]:
        raise SystemExit(f"zone(s) did not fill: {got['unfilled']}")
    conn = _child(_CONN_CHILD, path)
    if conn["ratsnest"] or conn["loose"]:
        detail = "\n  ".join(f"{pad} [{net}] cannot reach {missing}"
                              for pad, net, missing in conn["loose"])
        raise SystemExit(
            f"the SAVED fill leaves {conn['ratsnest']} unconnected item(s):\n  {detail}\n"
            f"Do not trust a DRC run with --refill-zones here; it re-pours and "
            f"hides exactly this.")
    return got["areas"]


def report(fps, pad_xy):
    """Numbers the floorplan review needs, MEASURED off the built board.

    Copper first, courtyards second. A courtyard is a placement convention with
    an IPC density level baked into it; copper clearance is what the fab and DRC
    actually care about, and on a board this dense the two say different things.
    Reporting only the courtyard number would have made this floorplan look 21
    times broken when the copper was fine.
    """
    import math
    print(f"board                {W} x {H} mm = {W * H:.1f} mm^2, "
          f"{P['layers']}L {P['copper_um']} um {P['finish']}")

    # ---- copper: pad bounding boxes, per footprint
    cu = {}
    for ref, fp in fps.items():
        xs, ys = [], []
        for pad in fp.Pads():
            bb = pad.GetBoundingBox()
            xs += [pcbnew.ToMM(bb.GetLeft() - ORG.x), pcbnew.ToMM(bb.GetRight() - ORG.x)]
            ys += [pcbnew.ToMM(bb.GetTop() - ORG.y), pcbnew.ToMM(bb.GetBottom() - ORG.y)]
        cu[ref] = (min(xs), min(ys), max(xs), max(ys))

    worst_edge = min(((min(x0 + W / 2, W / 2 - x1, y0 + H / 2, H / 2 - y1), r)
                      for r, (x0, y0, x1, y1) in cu.items()))
    print(f"copper to board edge {worst_edge[1]} at {worst_edge[0]:.3f} mm "
          f"(rule {P['edge_clearance_mm']})")

    # Pad-to-pad, per copper layer, different nets only, between footprints.
    # Measured on the pad polygons, not footprint bounding boxes: a box over a
    # whole footprint reports the notch between two pads as a collision, and a
    # box ignores layers, so a B.Cu part reads as sitting on the top pads above it.
    def layers(pad):
        return {l for l in (pcbnew.F_Cu, pcbnew.B_Cu) if pad.IsOnLayer(l)}
    allpads = [(ref, p) for ref, fp in fps.items() for p in fp.Pads() if layers(p)]
    gaps = []
    for i, (ra, pa) in enumerate(allpads):
        for rb, pb in allpads[i + 1:]:
            if ra == rb or pa.GetNetCode() == pb.GetNetCode():
                continue
            common = layers(pa) & layers(pb)
            if not common:
                continue
            lay = sorted(common)[0]
            sa = pa.GetEffectiveShape(lay)
            sb = pb.GetEffectiveShape(lay)
            # Collide(shape, clearance) is the geometry DRC itself uses; bisect
            # it to a 1 um gap. Anything >= 2 mm apart reads as 2 mm.
            if sa.Collide(sb, 0):
                g = 0.0
            else:
                lo, hi = 0, pcbnew.FromMM(2.0)
                if sa.Collide(sb, hi):
                    while hi - lo > pcbnew.FromMM(0.001):
                        mid = (lo + hi) // 2
                        lo, hi = (lo, mid) if sa.Collide(sb, mid) else (mid, hi)
                g = pcbnew.ToMM(hi)
            gaps.append((g, f"{ra}.{pa.GetNumber()}-{rb}.{pb.GetNumber()}"))
    gaps.sort()
    print(f"tightest pad-to-pad copper gaps between footprints, same layer, "
          f"different nets (rule {P['clearance_mm']}):")
    for g, pair in gaps[:8]:
        flag = "  <-- below rule" if g < P["clearance_mm"] else ""
        print(f"    {pair:<14} {g:6.3f} mm{flag}")

    # Silk labels, both sides: clearance to copper pads on the same side and to
    # the board edge.
    silk_cu = {pcbnew.F_SilkS: pcbnew.F_Cu, pcbnew.B_SilkS: pcbnew.B_Cu}
    for t in [d for d in fps[next(iter(fps))].GetBoard().GetDrawings()
              if isinstance(d, pcbnew.PCB_TEXT) and d.GetLayer() in silk_cu]:
        ink = t.GetEffectiveTextShape().BBox()
        box = (pcbnew.ToMM(ink.GetLeft() - ORG.x), pcbnew.ToMM(ink.GetTop() - ORG.y),
               pcbnew.ToMM(ink.GetRight() - ORG.x), pcbnew.ToMM(ink.GetBottom() - ORG.y))
        worst = (99, "")
        for ref, p in allpads:
            if silk_cu[t.GetLayer()] not in layers(p):
                continue
            bb = p.GetBoundingBox()
            px0, py0 = pcbnew.ToMM(bb.GetLeft() - ORG.x), pcbnew.ToMM(bb.GetTop() - ORG.y)
            px1, py1 = pcbnew.ToMM(bb.GetRight() - ORG.x), pcbnew.ToMM(bb.GetBottom() - ORG.y)
            g = max(px0 - box[2], box[0] - px1, py0 - box[3], box[1] - py1)
            worst = min(worst, (g, f"{ref}.{p.GetNumber()}"))
        edge = min(box[0] + W / 2, W / 2 - box[2], box[1] + H / 2, H / 2 - box[3])
        bad = worst[0] < P["silk_to_pad_mm"] or edge < P["edge_clearance_mm"]
        print(f"silk '{t.GetText()}' ink to pad {worst[1]} {worst[0]:.3f} mm, to edge "
              f"{edge:.3f} mm{'  <-- below rule' if bad else ''}")
        if bad:
            gaps.append((-1, f"silk {t.GetText()}"))

    # ---- courtyards, for the per-pair disposition the skill requires.
    #      POLYGON intersection, not a bounding box. GetCourtyard() returns the
    #      courtyard OUTLINE, which carries the 0.05 mm graphic stroke, so a
    #      bbox test called any pair within ~0.10 mm of each other an overlap:
    #      this printed 10 pairs on 2026-09-16 where DRC found 3, and seven of
    #      them had real clearance. A placement report that disagrees with the
    #      authority in the pessimistic direction is worse than none -- it makes
    #      the disposition list in DESIGN.md an exercise in explaining away
    #      things that are fine.
    courtyards = {}
    for ref, fp in fps.items():
        cy = fp.GetCourtyard(pcbnew.F_CrtYd)
        if cy.OutlineCount() == 0:
            continue
        courtyards[ref] = cy
    over = []
    for a in courtyards:
        for b in courtyards:
            if a >= b:
                continue
            inter = pcbnew.SHAPE_POLY_SET(courtyards[a])
            inter.BooleanIntersection(courtyards[b])
            if inter.OutlineCount() and inter.Area() > 0:
                over.append(f"{a}-{b}")
    print(f"courtyard overlaps   {len(over)} (dispositioned in DESIGN.md): "
          f"{', '.join(sorted(over)) if over else 'none'}")

    def dist(ref, u1pin):
        px, py = pad_xy(ref, "1")
        qx, qy = pad_xy("U1", u1pin)
        return math.hypot(px - qx, py - qy)
    print("functional proximity, pad 1 to the U1 pin it serves:")
    for ref, pin, why in (("C2", "3", "CIN HF -> VIN"), ("C1", "3", "CIN bulk -> VIN"),
                          ("C3", "8", "CVCC -> VCC"), ("C4", "4", "COUT -> VOUT"),
                          ("R1", "9", "RFBT -> FB"), ("R2", "9", "RFBB -> FB"),
                          ("C6", "9", "CFF -> FB"), ("R6", "11", "MODE strap"),
                          ("JP1", "11", "MODE jumper"), ("R3", "1", "PGOOD pull-up"),
                          ("R4", "2", "EN pull-up"), ("R5", "2", "EN divider"),
                          ("TP1", "2", "EN pad"), ("TP2", "1", "PGOOD pad"),
                          ("TP3", "11", "MODE pad")):
        print(f"    {ref:<3} -> U1.{pin:<2} {dist(ref, pin):5.2f} mm   {why}")
    return sum(1 for g, _ in gaps if g < P["clearance_mm"])


def main():
    board, fps, pad_xy, netmap = build()
    if STAGE == "place":
        out = HERE / f"{NAME}-floorplan.kicad_pcb"
        board.Save(str(out))
        print(f"STAGE=place -- floorplan review artefact only, no routing, no pours")
        n_close = report(fps, pad_xy)
        print(f"wrote {out.name}")
        return 1 if n_close else 0
    n_seg, n_via = route(board, netmap)
    board.Save(str(OUT))
    project_settings.apply(project_settings.prj_path(VKEY))
    areas = fill(OUT)
    print(f"routed              {n_seg} track segments, {n_via} vias")
    for net, layer, n_region, area in areas:
        print(f"pour {net:6s} {layer:5s} {n_region} region(s), {area:6.2f} mm^2")
    print(project_settings.verify(project_settings.prj_path(VKEY)))
    report(fps, pad_xy)
    print(f"wrote {OUT.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
