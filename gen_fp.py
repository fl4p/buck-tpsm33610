#!/usr/bin/env python3
"""Generate the project-specific footprints for buck-tpsm33610.

GENERATED ARTEFACT -- this script is the source of truth. Do not hand-edit the
.kicad_mod files; run `python3 gen_fp.py` instead.

Every dimension below is traceable to a datasheet drawing, and the transcription
itself -- how the drawing was read, and how each number was tied back to a named
callout -- is written up in docs/2026-09-13-rdn0011b-land-pattern.md. Read that
before changing any constant here.

Source: TI SNVSCS7E rev E (APRIL 2025 - REVISED SEPTEMBER 2026), package drawing
4231197/B 08/2025, in datasheets/TI-TPSM336xx-Q1-SNVSCS7E-revE.pdf.

  * page 46, "PACKAGE OUTLINE  RDN0011B"
      body                    3.6 / 3.4 (X)  x  4.6 / 4.4 (Y),  2.1 / 1.9 tall
      body is centred on the land-pattern datum (measured: the big terminals sit
      at Y = -0.996 from the body centre and at Y = -0.995 from the land datum)
  * page 47, "EXAMPLE BOARD LAYOUT / LAND PATTERN EXAMPLE"
      metal = the BLUE dashed outlines; solder mask opening = the GREEN outlines
      SOLDER MASK DEFINED is marked (PREFERRED), 0.05 MIN ALL AROUND
  * page 48, "EXAMPLE STENCIL DESIGN"
      0.1 mm stencil; PIN 4 & 5: 72% SOLDER COVERAGE BY AREA

THREE THINGS ABOUT THIS PACKAGE THAT A NORMAL QFN GENERATOR GETS WRONG:

1. It is SOLDER-MASK-DEFINED, not NSMD.  TI marks SMD "(PREFERRED)" on p.47 and
   draws the mask opening 0.05 INSIDE the metal.  That is the opposite of the
   TMP117 in the neighbouring project and the opposite of Aisler's default
   +50 um mask expansion, so it is set explicitly on every pad and must not be
   left to the fab.

2. Pins 4 and 5 have a mask opening that is NOT their copper inset.  RDN is
   flip-chip-on-lead: the copper is a plain 1.6 x 2.15 rectangle, but the
   package terminal only touches the board over a 1.125 x 2.05 body plus four
   0.375 x 0.25 lead fingers.  The mask opening follows the terminal, which
   leaves a 0.375 mm strip of copper along the outer edge of each pad covered.
   A KiCad pad's mask aperture is always concentric with its copper, so pins 4
   and 5 carry NO mask layer of their own and their openings are emitted as
   F.Mask polygons.  Flattening this to a plain rectangle would expose that
   strip with no terminal above it to wet it.

3. Their paste is seven apertures each, transcribed from p.48, not KiCad's 1:1
   default.  Coverage is referenced to the MASK OPENING (70.9 %, TI's "72%"),
   not to the copper (55.2 %) -- see the guard at the bottom.
"""

import hashlib
import pathlib
import sys

OUT = pathlib.Path(__file__).resolve().parent / "lib" / "buck-tpsm33610.pretty"

# ------------------------------------------------------- SNVSCS7E p.47, copper
# THE DATASHEET LAND, exactly as transcribed. Never edit these to make something
# fit -- edit TRIM below, which is the declared departure and is guarded.
# (pin, name, centre X, centre Y, width, height) in DATASHEET coordinates:
# +X right, +Y up, origin = "0.000 SYMM" / "0.000 PKG", top view, as drawn.
# KiCad's Y runs the other way; the flip happens once, in _k() below.
LAND_TI = [
    ("1",  "PGOOD",     -1.3875,  1.960, 1.225, 0.470),
    ("2",  "EN",        -1.400,   1.150, 1.200, 0.350),
    ("3",  "VIN",       -1.400,   0.650, 1.200, 0.350),
    ("4",  "VOUT",      -1.200,  -0.995, 1.600, 2.150),
    ("5",  "SW",         1.200,  -0.995, 1.600, 2.150),
    ("6",  "SW",         1.400,   0.650, 1.200, 0.350),
    ("7",  "BOOT",       1.400,   1.150, 1.200, 0.350),
    ("8",  "VCC",        1.3875,  1.960, 1.225, 0.470),
    ("9",  "FB",         0.500,   2.060, 0.350, 0.900),
    ("10", "GND",        0.000,   1.690, 0.400, 1.620),
    ("11", "MODE/SYNC", -0.500,   2.060, 0.350, 0.900),
]

# ------------------------------- PROCESS: TI's land is finer than Aisler's rules
# TI's land has a 0.100 mm minimum copper gap (pins 1-11 and 8-9) and 0.125 mm
# (pins 9-10 and 10-11). That is finer than EVERY published Aisler 2-layer rule:
#
#     35 um HASL 200/150     35 um ENIG 125/125
#     70 um HASL 225/225     70 um ENIG 175/175
#
# and finer than the usual 2-layer prototype processes elsewhere (JLCPCB 2L
# 127 um, PCBWay 2L standard 150 um).
#
# DECIDED 2026-09-13 (Fab): build it at 35 um ENIG with the land UNTRIMMED, and
# accept the rule break. His words: "the aisler rules are conservative, breaking
# the rules has always worked so far, no bad boards." So TRIM stays empty and
# MIN_GAP is the datasheet's own 0.100 mm -- the guard below still runs, it is
# just calibrated to the package rather than to the fab.
#
# This is a DECISION, not an oversight, and it is scoped:
#   * 0.100 mm at 35 um ENIG is 1.25x under a published 125 um rule. Etch aspect
#     ratio there is about 0.35:1 -- the rule is margin, not physics.
#   * It is also why the copper stays 35 um. At 70 um the same 0.100 mm gap is
#     1.75x under the rule AND about 0.7:1 in etch aspect ratio, which is a
#     physical limit rather than a conservative one. The 70 um option was worth
#     roughly 10 C of ambient headroom (see DESIGN.md); it is the one place on
#     this board where the rule should not be broken.
#   * Everything OUTSIDE this footprint is drawn to 150/150 um, so the
#     violation is confined to the 4.0 x 4.6 mm under the module and is the
#     only thing an Aisler DRC complaint could be about.
#
# The trim mechanism is kept, empty, because it is the documented way to back
# out of this if a board ever does come back with a short under the module:
# trim per EDGE, positive = that edge moves INWARD, in DATASHEET coordinates,
#   pin: (west, east, south, north)
# and 0.150 mm minimum gap is reached with
#   "1":(0,0.025,0,0)  "8":(0.025,0,0,0)  "11":(0.025,0.0125,0,0)
#   "9":(0.0125,0.025,0,0)  "10":(0.0125,0.0125,0,0)
# at a cost of 15 % of the wetted joint width on FB and MODE/SYNC.
MIN_GAP = 0.100                  # the package's own minimum, not the fab's
TRIM = {}

# Package TERMINAL extents, p.46 terminal view, measured off the drawing in the
# same way as the land (see the land-pattern doc). Datasheet coordinates. These
# exist so the trim can be checked against the thing the joint actually needs --
# the terminal -- rather than against the land it came from.
# (pin, centre X, centre Y, width, height)
TERMINAL = {
    "1":  (-1.2875, 1.960, 0.925, 0.375),
    "8":  ( 1.2875, 1.960, 0.925, 0.375),
    "9":  ( 0.500,  1.910, 0.250, 0.500),
    "11": (-0.500,  1.910, 0.250, 0.500),
    "10": ( 0.000,  1.530, 0.300, 1.250),
}


def _apply_trim():
    out = []
    for pin, name, x, y, w, h in LAND_TI:
        tw, te, ts, tn = TRIM.get(pin, (0.0, 0.0, 0.0, 0.0))
        x0, x1 = x - w / 2 + tw, x + w / 2 - te
        y0, y1 = y - h / 2 + ts, y + h / 2 - tn
        out.append((pin, name, (x0 + x1) / 2, (y0 + y1) / 2, x1 - x0, y1 - y0))
    return out


LAND = _apply_trim()

BIG = ("4", "5")                 # the two lead-frame pads with shaped mask+paste

MASK_INSET = 0.05                # p.47 "0.05 MIN ALL AROUND", solder-mask defined
LAND_R = 0.05                    # (R0.05) TYP

# ---- pins 4/5 mask opening, p.47.  Right-hand (pin 5) geometry; pin 4 mirrors X.
MB_XI, MB_XO = 0.450, 1.575      # mask body inner / outer X          (2X (1.125))
MB_YT, MB_YB = 0.030, -2.020     # mask body top / bottom Y     (0.03, 2X (2.02))
FIN_XO = 1.950                   # finger outer X                      (4X (1.95))
FIN_H = 0.250                    # finger height                       (8X (0.25))
FIN_Y = (-0.30, -0.80, -1.30, -1.80)   # 2X (0.3) then 6X (0.5) pitch

# ---- pins 4/5 paste apertures, p.48.  Right-hand geometry; pin 4 mirrors X.
# p.48 rounds the body-aperture ordinates to 2 decimals, and taken literally
# they place the apertures 0.005 mm OUTSIDE the mask body -- caught by guard 4
# below. Un-rounding against the geometry the drawing actually constructs: the
# top and bottom apertures are flush with the body's top and bottom edges, which
# makes the two inter-aperture gaps equal (0.205) and the inner edge flush with
# the body's inner edge (leaving a round 0.200 at the outer edge). The measured
# pixel values (0.927 wide at X 0.913; centres -0.229/-0.996/-1.763) fit the
# un-rounded numbers better than the printed ones.
PB_X = 0.9125                    # body aperture centre X        (3X (0.91) rounded)
PB_W = 0.925                     # body aperture width           (6X (0.93) rounded)
PB = ((-0.225, 0.510), (-0.995, 0.620), (-1.765, 0.510))   # (centre Y, height)
                                 # 2X (0.23), 2X (1), 2X (1.77) rounded; 4X (0.51), 2X (0.62)
PF_X = 1.7625                    # finger aperture centre X      ((1.76) rounded: the
                                 # aperture is exactly the finger, 1.575..1.950
PF_W, PF_H = 0.375, 0.250        # 8X (0.375), 8X (0.25); Y = FIN_Y

# -------------------------------------------------------- SNVSCS7E p.46, body
BODY_X, BODY_Y = 3.5, 4.5        # 3.6/3.4 and 4.6/4.4, centred on the land datum
BODY_Z = 2.1                     # max height, for the descr only

# --------------------------------------------------------- derived / our choices
COURTYARD_EXCESS = 0.25          # IPC-7351 "nominal" density for a no-lead package
SILK_W = 0.15
FAB_W = 0.10
CRTYD_W = 0.05


def _uuid(fp_name, *parts):
    """Stable uuid5-style id derived from the item's own identity, never a counter."""
    h = hashlib.sha1(("buck-tpsm33610/" + fp_name + "/" +
                      "/".join(str(p) for p in parts)).encode()).hexdigest()
    return f"{h[0:8]}-{h[8:12]}-5{h[13:16]}-a{h[17:20]}-{h[20:32]}"


def _k(y):
    """Datasheet Y (up) -> KiCad Y (down). The one place the flip happens."""
    return -y


def _poly(pts, layer, uid, width=0.0):
    s = ['\t(fp_poly',
         '\t\t(pts ' + ' '.join(f'(xy {x:.4f} {y:.4f})' for x, y in pts) + ')']
    if width:
        s.append(f'\t\t(stroke (width {width}) (type solid)) (fill no)')
    else:
        s.append('\t\t(stroke (width 0) (type solid)) (fill yes)')
    s.append(f'\t\t(layer "{layer}") (uuid "{uid}"))')
    return s


def _mask_outline(sign):
    """Mask opening for pin 5 (sign=+1) or pin 4 (sign=-1), in KiCad coords.

    Traced from p.47: a rectangular body with four lead fingers stepping out of
    its OUTER edge. Emitted as one closed polygon so the aperture is a single
    region no matter how the fab's CAM merges primitives.
    """
    xi, xo, xf = sign * MB_XI, sign * MB_XO, sign * FIN_XO
    yt, yb = _k(MB_YT), _k(MB_YB)          # yt < yb in KiCad coords
    pts = [(xi, yt), (xo, yt)]
    for fy in FIN_Y:                        # FIN_Y is already top-to-bottom
        ky = _k(fy)
        pts += [(xo, ky - FIN_H / 2), (xf, ky - FIN_H / 2),
                (xf, ky + FIN_H / 2), (xo, ky + FIN_H / 2)]
    pts += [(xo, yb), (xi, yb)]
    return pts


def tpsm336xx_footprint():
    name = "TPSM336xx_QFN-FCMOD-11_RDN0011B_TI"
    u = lambda *p: _uuid(name, *p)
    L = []
    A = L.append

    A(f'(footprint "{name}"')
    A('\t(version 20241229)')
    A('\t(generator "gen_fp.py")')
    A('\t(layer "F.Cu")')
    A('\t(descr "TI RDN0011B QFN-FCMOD, 11 pins, '
      f'{BODY_X}x{BODY_Y}x{BODY_Z} mm. '
      'Land per SNVSCS7E p.47 (drawing 4231197/B 08/2025), SOLDER MASK DEFINED '
      '(TI marks it PREFERRED), mask 0.05 inside metal. Pins 4 and 5 carry a '
      'lead-finger mask opening and 7 paste apertures each, per p.47 and p.48 '
      '(72% coverage of the mask opening). '
      'pinmap: Figure 5-1 TOP VIEW and the Pin Functions table, p.5 -- '
      '1 PGOOD, 2 EN, 3 VIN, 4 VOUT, 5 SW, 6 SW, 7 BOOT, 8 VCC, 9 FB, 10 GND, '
      '11 MODE/SYNC. view: top (land pattern and Fig 5-1 agree, pin 1 upper '
      'left in both; the p.46 terminal view is the mirrored bottom view and was '
      'used only to locate the body on the land datum).")')
    A('\t(tags "QFN FCMOD NoLead TPSM33610 TPSM33620 TPSM33606 TI RDN0011B power module")')
    A('\t(attr smd)')

    cx = max(FIN_XO, BODY_X / 2) + COURTYARD_EXCESS
    cy_top = max(LAND[8][3] + LAND[8][5] / 2, BODY_Y / 2) + COURTYARD_EXCESS
    cy_bot = max(-(MB_YB), BODY_Y / 2) + COURTYARD_EXCESS

    A(f'\t(property "Reference" "REF**" (at 0 {-cy_top - 0.7:.2f} 0) (unlocked yes) (layer "F.SilkS")')
    A(f'\t\t(uuid "{u("prop", "ref")}")')
    A(f'\t\t(effects (font (size 0.8 0.8) (thickness {SILK_W}))))')
    A(f'\t(property "Value" "{name}" (at 0 {cy_bot + 0.7:.2f} 0) (unlocked yes) (layer "F.Fab")')
    A(f'\t\t(uuid "{u("prop", "val")}")')
    A('\t\t(effects (font (size 0.8 0.8) (thickness 0.1))))')

    # ---- F.Fab: real body outline with a pin-1 chamfer (pin 1 is upper-left in
    #      the top view, so the chamfer goes on the upper-left corner).
    bx, by = BODY_X / 2, BODY_Y / 2
    ch = 0.6
    fab = [(-bx, -by + ch), (-bx + ch, -by), (bx, -by), (bx, by), (-bx, by)]
    A(*[]) if False else None
    for line in _poly(fab, "F.Fab", u("fab", "body"), width=FAB_W):
        A(line)

    # ---- F.CrtYd
    A(f'\t(fp_rect (start {-cx:.4f} {-cy_top:.4f}) (end {cx:.4f} {cy_bot:.4f})')
    A(f'\t\t(stroke (width {CRTYD_W}) (type solid)) (fill no) (layer "F.CrtYd") (uuid "{u("crtyd", "body")}"))')

    # ---- F.SilkS: two rules clear of every land, plus a pin-1 dot outside the
    #      courtyard. Nothing between the pads: at 0.5 mm pitch there is no room
    #      that clears Aisler's 0.125 mm silk-to-pad rule.
    # The two body rules are GONE, 2026-09-13. On this board U1 sits 0.25 mm from
    # two board edges with C3 hard against its west face: one rule ran off the
    # east edge of the outline, the other over C3's VCC pad. A package outline
    # that cannot be drawn where the package is, is not an outline -- the body is
    # on F.Fab, where assembly reads it, and the pin-1 dot below is the only
    # thing silk has to say about an 11-pad QFN at 0.5 mm pitch.
    A(f'\t(fp_circle (center {-cx - 0.30:.4f} {-cy_top + 0.20:.4f}) (end {-cx - 0.15:.4f} {-cy_top + 0.20:.4f})')
    A(f'\t\t(stroke (width {SILK_W}) (type solid)) (fill solid) (layer "F.SilkS") (uuid "{u("silk", "pin1")}"))')

    # ---- pads
    for num, pname, x, y, w, h in LAND:
        ky = _k(y)
        rr = LAND_R / min(w, h)
        if num in BIG:
            # Copper only. Mask and paste are shaped, and follow below.
            A(f'\t(pad "{num}" smd rect (at {x:.4f} {ky:.4f}) (size {w} {h})')
            A('\t\t(layers "F.Cu")')
            A(f'\t\t(zone_connect 2) (uuid "{u("pad", num)}"))')
        else:
            A(f'\t(pad "{num}" smd roundrect (at {x:.4f} {ky:.4f}) (size {w} {h})')
            A('\t\t(layers "F.Cu" "F.Mask" "F.Paste")')
            A(f'\t\t(roundrect_rratio {rr:.4f})')
            A(f'\t\t(solder_mask_margin {-MASK_INSET})')
            A(f'\t\t(solder_paste_margin {-MASK_INSET})')
            A(f'\t\t(uuid "{u("pad", num)}"))')

    # ---- pins 4 and 5: shaped mask openings and 7 paste apertures each
    for num, sign in (("4", -1), ("5", 1)):
        for line in _poly(_mask_outline(sign), "F.Mask", u("mask", num)):
            A(line)
        for i, (py, ph) in enumerate(PB):
            A(f'\t(pad "" smd roundrect (at {sign * PB_X:.4f} {_k(py):.4f}) (size {PB_W} {ph})')
            A('\t\t(layers "F.Paste")')
            A(f'\t\t(roundrect_rratio {LAND_R / min(PB_W, ph):.4f}) (uuid "{u("paste", num, "body", i)}"))')
        for i, fy in enumerate(FIN_Y):
            A(f'\t(pad "" smd roundrect (at {sign * PF_X:.4f} {_k(fy):.4f}) (size {PF_W} {PF_H})')
            A('\t\t(layers "F.Paste")')
            A(f'\t\t(roundrect_rratio {LAND_R / min(PF_W, PF_H):.4f}) (uuid "{u("paste", num, "fin", i)}"))')

    A('\t(embedded_fonts no)')
    A(')')
    return name, "\n".join(L) + "\n"


def solderpad_footprint():
    """A bare 1.0 x 1.0 mm solder / probe pad for EN, PGOOD, MODE, VOUT sense, GND.

    Named TestPad_ and not SolderPad_ for a reason that is not cosmetic: the
    stock Connector:TestPoint symbol carries ki_fp_filters "Pin* Test*", and ERC
    checks it. A SolderPad_ name failed that check on all five pads. The choices
    were to rename, to own a project copy of the symbol, or to switch the check
    off -- and switching off the one check standing between the schematic and a
    footprint for the wrong package is the worst of the three. The name is also
    accurate, and matches what the neighbouring tmp117-probe calls the same
    thing.

    No silkscreen box and no paste: the silk label belongs to the board (it says
    what the pad IS, which the library cannot know), and paste on a bare pad that
    is never reflowed to anything only feeds solder balls. Courtyard is the pad
    plus 0.05 so five of them fit in a 2.4 mm strip.
    """
    name = "TestPad_1.0x1.0mm"
    u = lambda *p: _uuid(name, *p)
    side, crt = 1.0, 0.05
    L = []
    A = L.append
    A(f'(footprint "{name}"')
    A('\t(version 20241229)')
    A('\t(generator "gen_fp.py")')
    A('\t(layer "F.Cu")')
    A(f'\t(descr "Bare {side}x{side} mm SMD solder / probe pad. No silkscreen, no paste.")')
    A('\t(tags "test point probe solder pad")')
    A('\t(attr smd exclude_from_pos_files)')
    A(f'\t(property "Reference" "REF**" (at 0 {-side / 2 - 0.7:.2f} 0) (unlocked yes) (layer "F.Fab")')
    A(f'\t\t(uuid "{u("prop", "ref")}")')
    A('\t\t(effects (font (size 0.6 0.6) (thickness 0.1))))')
    A(f'\t(property "Value" "{name}" (at 0 {side / 2 + 0.7:.2f} 0) (unlocked yes) (layer "F.Fab")')
    A(f'\t\t(uuid "{u("prop", "val")}")')
    A('\t\t(effects (font (size 0.6 0.6) (thickness 0.1))))')
    A(f'\t(fp_rect (start {-side / 2:.4f} {-side / 2:.4f}) (end {side / 2:.4f} {side / 2:.4f})')
    A(f'\t\t(stroke (width {FAB_W}) (type solid)) (fill no) (layer "F.Fab") (uuid "{u("fab", "body")}"))')
    A(f'\t(fp_rect (start {-side / 2 - crt:.4f} {-side / 2 - crt:.4f}) '
      f'(end {side / 2 + crt:.4f} {side / 2 + crt:.4f})')
    A(f'\t\t(stroke (width {CRTYD_W}) (type solid)) (fill no) (layer "F.CrtYd") (uuid "{u("crtyd", "body")}"))')
    A(f'\t(pad "1" smd rect (at 0 0) (size {side} {side})')
    A('\t\t(layers "F.Cu" "F.Mask")')
    A(f'\t\t(uuid "{u("pad", 1)}"))')
    A('\t(embedded_fonts no)')
    A(')')
    return name, "\n".join(L) + "\n"


def solderjumper_footprint():
    """A 2-pad normally-open solder jumper, sized to drop into an 0402 slot.

    Fab, 2026-09-13: "can you add solder jumper(s) for mode?" -- JP1 replaces the
    R7 land, so MODE goes from auto to FPWM with a blob of solder instead of a
    part swap.

    The name has to start "SolderJumper" and contain "Open": the stock
    Jumper:SolderJumper_2_Open symbol carries ki_fp_filters "SolderJumper*Open*"
    and this project runs the ERC footprint_filter check as an ERROR.

    Geometry: 0.80 x 0.80 mm pads on 1.00 mm pitch, so a 0.20 mm gap. KiCad's own
    SolderJumper-2_P1.3mm_* are 2.3 x 1.5 mm, which does not fit in the west
    margin this board has; 1.8 x 0.8 mm does, and it sits on the same pad centres
    the 0402 it replaces used, so not one track had to move. 0.20 mm is a gap a
    fine iron bridges in one pass and hot air will not bridge by accident.

    ONE mask opening over BOTH pads, drawn explicitly rather than left to the
    pads: two separate openings would leave a 0.20 - 2 x 0.05 = 0.10 mm dam,
    exactly on Aisler's minimum, and a dam is the thing a solder jumper least
    wants. That makes the two pads share an aperture on purpose, which is what
    `allow_soldermask_bridges` is for -- declared here, on this footprint, so it
    stays scoped to the one land where it is true.

    No paste: nothing is reflowed here, and paste on an open jumper is a coin
    toss on whether the board arrives already bridged.
    """
    name = "SolderJumper_2_P1.00mm_Open_Pad0.8x0.4mm"
    u = lambda *p: _uuid(name, *p)
    pw, ph = 0.80, 0.40   # ph is across the pitch: board X once JP1 is rotated 90.
                          # 0.40, not 0.80, only because the 9.01 mm board has no
                          # room for more -- this is the smallest bridge target on
                          # the board and the reason the west margin closes at all.
    pitch = 1.00
    crt = 0.05
    mx, my = pitch / 2 + pw / 2 + 0.05, ph / 2 + 0.05   # mask opening half-extents
    cx, cy = pitch / 2 + pw / 2 + crt, ph / 2 + crt     # courtyard half-extents
    gap = pitch - pw
    L = []
    A = L.append
    A(f'(footprint "{name}"')
    A('\t(version 20241229)')
    A('\t(generator "gen_fp.py")')
    A('\t(layer "F.Cu")')
    A(f'\t(descr "Open solder jumper, 2 pads {pw}x{ph} mm on {pitch} mm pitch '
      f'({gap:.2f} mm gap), one shared mask opening, no paste. '
      f'Drops into an 0402 slot.")')
    A('\t(tags "solder jumper open")')
    A('\t(attr smd allow_soldermask_bridges exclude_from_pos_files)')
    A(f'\t(property "Reference" "REF**" (at 0 {-cy - 0.55:.2f} 0) (unlocked yes) (layer "F.Fab")')
    A(f'\t\t(uuid "{u("prop", "ref")}")')
    A('\t\t(effects (font (size 0.6 0.6) (thickness 0.1))))')
    A(f'\t(property "Value" "{name}" (at 0 {cy + 0.55:.2f} 0) (unlocked yes) (layer "F.Fab")')
    A(f'\t\t(uuid "{u("prop", "val")}")')
    A('\t\t(effects (font (size 0.6 0.6) (thickness 0.1))))')
    A(f'\t(fp_rect (start {-mx:.4f} {-my:.4f}) (end {mx:.4f} {my:.4f})')
    A(f'\t\t(stroke (width {FAB_W}) (type solid)) (fill no) (layer "F.Fab") (uuid "{u("fab", "body")}"))')
    A(f'\t(fp_rect (start {-cx:.4f} {-cy:.4f}) (end {cx:.4f} {cy:.4f})')
    A(f'\t\t(stroke (width {CRTYD_W}) (type solid)) (fill no) (layer "F.CrtYd") (uuid "{u("crtyd", "body")}"))')
    # the single aperture, as a filled polygon on F.Mask
    L.extend(_poly([(-mx, -my), (mx, -my), (mx, my), (-mx, my)], "F.Mask", u("mask", "open")))
    for n, sx in ((1, -1), (2, +1)):
        A(f'\t(pad "{n}" smd rect (at {sx * pitch / 2:.4f} 0) (size {pw} {ph})')
        A('\t\t(layers "F.Cu")')      # F.Mask comes from the shared aperture above
        A(f'\t\t(uuid "{u("pad", n)}"))')
    A('\t(embedded_fonts no)')
    A(')')
    return name, "\n".join(L) + "\n"


# --------------------------------------------------------------- the header land
# J1's land is KiCad's own PinHeader_1x03_P2.54mm_Vertical, minus its silkscreen.
# The library outline is a 2.54 mm box round the pins: on a 9.91 mm board it
# crosses C1's and C4's pads and runs off the south edge. Stripping it on the
# BOARD instead would make every DRC run report lib_footprint_mismatch on J1 --
# the board footprint no longer matching the library it names -- so the edit
# belongs in a footprint this project owns and the schematic names.
HDR_SRC = pathlib.Path("/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints/"
                       "Connector_PinHeader_2.54mm.pretty/PinHeader_1x03_P2.54mm_Vertical.kicad_mod")
HDR_NAME = "PinHeader_1x03_P2.54mm_Vertical_NoSilk"


def _children(text):
    """(prefix, [child blocks]) of the top-level (footprint ...) form.

    A depth walk that honours quoted strings, not a regex: the source carries
    (descr "...") and (tags "...") whose contents include parentheses, and a
    brace-counting parser that does not know about quotes truncates the
    footprint silently and emits a file that still looks like a footprint.
    """
    start = text.index("(footprint")
    depth, i, in_str, esc = 0, start, False, False
    prefix_end, kids, kid_start = None, [], None
    while i < len(text):
        c = text[i]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
        elif c == '"':
            in_str = True
        elif c == "(":
            depth += 1
            if depth == 2:
                if prefix_end is None:
                    prefix_end = i
                kid_start = i
        elif c == ")":
            depth -= 1
            if depth == 1:
                kids.append(text[kid_start:i + 1])
            elif depth == 0:
                return text[start:prefix_end], kids
        i += 1
    raise SystemExit("unbalanced s-expression in " + str(HDR_SRC))


def header_footprint():
    if not HDR_SRC.exists():
        raise SystemExit(f"KiCad's {HDR_SRC.name} not found -- is KiCad installed at "
                         "/Applications/KiCad?")
    src = HDR_SRC.read_text()
    prefix, kids = _children(src)
    keep = []
    for k in kids:
        if k.lstrip("(").startswith("fp_") and '"F.SilkS"' in k:
            continue
        # The reference designator goes to F.Fab with everything else on this
        # board: at Aisler's legible minimum a refdes is wider than the part.
        if k.lstrip("(").startswith("property") and '"Reference"' in k:
            k = k.replace('(layer "F.SilkS")', '(layer "F.Fab")')
        keep.append(k)
    dropped = len(kids) - len(keep)
    if dropped == 0:
        raise SystemExit("the stock header footprint has no F.SilkS graphics to "
                         "drop -- KiCad's library changed, re-check this derivation")
    prefix = prefix.replace('"PinHeader_1x03_P2.54mm_Vertical"', f'"{HDR_NAME}"', 1)
    prefix = prefix.replace('(descr "', '(descr "KiCad Connector_PinHeader_2.54mm:'
                            'PinHeader_1x03_P2.54mm_Vertical with its F.SilkS outline '
                            'removed, generated by gen_fp.py -- ', 1)
    text = prefix + "\n\t" + "\n\t".join(keep) + "\n)\n"
    silk_graphics = [k for k in keep
                     if k.lstrip("(").split()[0].startswith(("fp_", "gr_"))
                     and '"F.SilkS"' in k]
    if silk_graphics or text.count('(pad "') != 3 or text.count("(") != text.count(")"):
        raise SystemExit(f"derived header footprint failed its own checks: "
                         f"{len(silk_graphics)} silk graphics, "
                         f"{text.count('(pad ')} pads, parens "
                         f"{text.count('(')}/{text.count(')')}")
    return HDR_NAME, text


def main():
    def need(cond, msg):
        # raise, not assert: `python3 -O` deletes assert outright, and this
        # script would then write the footprints, exit 0, and print the geometry
        # summary as though it had checked anything.
        if not cond:
            raise SystemExit(f"gen_fp: {msg}")

    # ---------------------------------------------------- guards on the geometry
    need(len(LAND) == 11, f"{len(LAND)} lands, expected 11")
    need(len({p[0] for p in LAND}) == 11, "duplicate pad numbers")

    # 1. No two copper lands may overlap, and the minimum copper gap has to clear
    #    the process. Aisler 2L is 150 um (35 um ENIG 125 um); this board is drawn
    #    to 150 um everywhere EXCEPT inside this land, which the package sets and
    #    we cannot widen -- so the real floor here is the fab's absolute minimum.
    def box(p):
        _, _, x, y, w, h = p
        return (x - w / 2, x + w / 2, y - h / 2, y + h / 2)

    worst = (9e9, None)
    for i in range(len(LAND)):
        for j in range(i + 1, len(LAND)):
            ax0, ax1, ay0, ay1 = box(LAND[i])
            bx0, bx1, by0, by1 = box(LAND[j])
            dx = max(bx0 - ax1, ax0 - bx1)
            dy = max(by0 - ay1, ay0 - by1)
            gap = max(dx, dy)
            need(gap > 0, f"lands {LAND[i][0]} and {LAND[j][0]} overlap")
            if gap < worst[0]:
                worst = (gap, f"{LAND[i][0]}-{LAND[j][0]}")
    need(worst[0] >= MIN_GAP - 1e-9,
         f"min land gap {worst[0]:.3f} mm at {worst[1]} is below MIN_GAP {MIN_GAP} mm")
    # Report the fab-rule status every run so the accepted violation stays
    # visible instead of decaying into folklore. This does NOT fail the build --
    # see the PROCESS note at the top; it is a decision, and a guard that a
    # decision keeps overriding is a guard nobody reads.
    AISLER_2L_35UM_ENIG = 0.125
    over = AISLER_2L_35UM_ENIG / worst[0]

    # 2. Mask dam between adjacent openings. Solder-mask-defined INSETS every
    #    opening, so the dam is the copper gap PLUS 2 x 0.05 -- the one place
    #    where SMD helps rather than costs.
    dam = worst[0] + 2 * MASK_INSET
    need(dam >= 0.100, f"mask dam {dam:.3f} mm is below Aisler's 100 um")

    # 3. The mask opening of pins 4/5 must stay strictly inside their copper.
    _, _, p5x, p5y, p5w, p5h = [p for p in LAND if p[0] == "5"][0]
    need(abs(p5x) - p5w / 2 <= MB_XI - MASK_INSET + 1e-9, "pin 5 mask body runs past the inner copper edge")
    need(FIN_XO + MASK_INSET <= abs(p5x) + p5w / 2 + 1e-9, "pin 5 fingers run past the outer copper edge")
    need(MB_YT + MASK_INSET <= p5y + p5h / 2 + 1e-9, "pin 5 mask runs past the top copper edge")
    need(MB_YB - MASK_INSET >= p5y - p5h / 2 - 1e-9, "pin 5 mask runs past the bottom copper edge")

    # 4. Paste apertures must stay inside the mask opening -- paste on masked
    #    copper is paste that cannot wet.
    for py, ph in PB:
        need(PB_X - PB_W / 2 >= MB_XI - 1e-9 and PB_X + PB_W / 2 <= MB_XO + 1e-9,
             "body paste aperture runs outside the mask body in X")
        need(py + ph / 2 <= MB_YT + 1e-9 and py - ph / 2 >= MB_YB - 1e-9,
             "body paste aperture runs outside the mask body in Y")
    need(PF_X - PF_W / 2 >= MB_XO - 1e-9 and PF_X + PF_W / 2 <= FIN_XO + 1e-9,
         "finger paste aperture does not sit on a finger")
    need(PF_H <= FIN_H + 1e-9, "finger paste aperture is taller than the finger")
    need(tuple(sorted(FIN_Y)) == tuple(sorted(set(FIN_Y))), "duplicate finger Y")
    pitch = {round(FIN_Y[i] - FIN_Y[i + 1], 6) for i in range(len(FIN_Y) - 1)}
    need(pitch == {0.5}, f"finger pitch {pitch} is not the drawing's 6X (0.5)")

    # 5. Paste coverage of pins 4/5, referenced to the MASK OPENING the way TI
    #    references it on p.48. Against copper the same stencil reads 55.2 % and
    #    a guard that divides by the wrong area fails a correct stencil.
    paste = sum(PB_W * ph for _, ph in PB) + len(FIN_Y) * PF_W * PF_H
    open_area = (MB_XO - MB_XI) * (MB_YT - MB_YB) + len(FIN_Y) * (FIN_XO - MB_XO) * FIN_H
    cov = paste / open_area
    need(0.65 <= cov <= 0.78, f"pin 4/5 paste coverage {cov:.1%} is not TI's 72% +/- a few points")
    cu_cov = paste / (p5w * p5h)

    # 6. Total pads emitted, counted from the emitted text, not from intent.
    OUT.mkdir(parents=True, exist_ok=True)
    written = []
    for name, text in (tpsm336xx_footprint(), solderpad_footprint(),
                       solderjumper_footprint(), header_footprint()):
        p = OUT / f"{name}.kicad_mod"
        p.write_text(text)
        written.append((p, text))
    mod = written[0][1]
    need(mod.count("(pad \"") == 11 + 2 * (len(PB) + len(FIN_Y)),
         "emitted pad count does not match 11 lands + 14 paste apertures")
    need(mod.count('(layer "F.Mask") (uuid') == 2, "expected exactly 2 F.Mask polygons")
    need(mod.count("(net ") == 0, "a net leaked into a library footprint")
    need(mod.count("(") == mod.count(")"), "unbalanced parentheses in the footprint")

    # 7. The jumper. It is the one land on this board deliberately built to be
    #    shorted, so check that it is shortABLE and that it does not arrive shorted:
    #    two pads, no paste, exactly one mask aperture, and the bridge declared.
    jname, jtext = solderjumper_footprint()
    need(jtext.count('(pad "') == 2, "the solder jumper does not have exactly 2 pads")
    need("F.Paste" not in jtext, "the solder jumper carries paste -- it would arrive bridged")
    need(jtext.count('(layer "F.Mask")') == 1, "the solder jumper needs exactly one mask aperture")
    need("allow_soldermask_bridges" in jtext,
         "the shared aperture is not declared -- DRC would read it as a mask bridge")
    need(jname.startswith("SolderJumper") and "Open" in jname,
         f"{jname} does not match the symbol's ki_fp_filters SolderJumper*Open*")
    need(jtext.count("(") == jtext.count(")"), "unbalanced parentheses in the solder jumper")

    print(f"min land-to-land copper gap  {worst[0]:.3f} mm  ({worst[1]}, package-set)")
    if over > 1.0:
        print(f"  ACCEPTED RULE BREAK        {over:.2f}x under Aisler 2L 35um ENIG "
              f"({AISLER_2L_35UM_ENIG*1000:.0f} um), confined to this footprint "
              f"-- see the PROCESS note in gen_fp.py")
    print(f"resulting mask dam           {dam:.3f} mm  (SMD inset helps here)")
    print(f"pin 4/5 paste coverage       {cov:.1%} of the mask opening  (TI: 72%)")
    print(f"                             {cu_cov:.1%} of the copper     (TI does NOT mean this)")
    for p, _ in written:
        print(f"wrote {p.relative_to(pathlib.Path(__file__).resolve().parent)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
