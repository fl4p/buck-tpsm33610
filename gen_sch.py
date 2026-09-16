#!/usr/bin/env python3
"""Generate the schematic for buck-tpsm33610.

  python3 gen_sch.py                  -> buck-tpsm33610.kicad_sch
  python3 gen_sch.py --variant mini   -> buck-tpsm33610-mini.kicad_sch

GENERATED ARTEFACT -- this script is the source of truth. Editing the .kicad_sch
in Eeschema will be overwritten on the next run. Close Eeschema before running.

The circuit is identical across variants; they differ only in board outline and
header pitch (variants.py), so this file is variant-blind apart from the name.

Design intent is in DESIGN.md. In short: TI's Table 8-3 fixed-output application
(CIN + 100 nF, CVCC, one COUT, FB tied to VOUT) plus exactly three additions --
a 0 ohm RFBT that doubles as the fixed/adjustable selector, default straps for
the two pins that must not float, and a PGOOD pull-up.
"""

import hashlib
import math
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
KI = pathlib.Path("/Applications/KiCad/KiCad.app/Contents/SharedSupport/symbols")

sys.path.insert(0, str(HERE))
import variants   # noqa: E402
import gen_sym    # noqa: E402  -- for ABS_MAX; the pin table is code, not graphics

VKEY, V = variants.select()
NAME = V["name"]
OUT = HERE / f"{NAME}.kicad_sch"

GRID = 1.27
PAPER = "A4"

SRC = {
    "Device:C_Small":                  KI / "Device.kicad_sym",
    "Device:R_Small":                  KI / "Device.kicad_sym",
    "Connector_Generic:Conn_01x03":    KI / "Connector_Generic.kicad_sym",
    "Connector:TestPoint":             KI / "Connector.kicad_sym",
    "Jumper:SolderJumper_2_Open":      KI / "Jumper.kicad_sym",
    "power:GND":                       KI / "power.kicad_sym",
    "power:PWR_FLAG":                  KI / "power.kicad_sym",
    "buck-tpsm33610:TPSM33610S3Q":     HERE / "lib" / "buck-tpsm33610.kicad_sym",
}
NO_PINS = {}

# ---------------------------------------------------------------- net voltage ceilings
# The maximum each net can reach IN THIS CIRCUIT, checked pin-by-pin against
# gen_sym.ABS_MAX (SNVSCS7E p.6) by check_abs_max(). This is the audit that
# catches the mistake this part invites: MODE/SYNC sits two pins from VIN in the
# pinout and is rated 5.5 V where VIN is rated 40 V.
NET_VMAX = {
    "VIN":   36.0,   # recommended operating maximum, p.6
    "GND":    0.0,
    "VOUT":   7.0,   # 3.3 as built; 7.0 is the adjustable ceiling the DNP divider allows
    "VCC":    3.5,   # internal LDO, EC table p.7: 3.1 / 3.3 / 3.5 V -- NOT 5 V
    "EN":    36.0,   # R4 ties it to VIN
    "MODE":   3.5,   # R6 to GND, or JP1 bridged to VCC. Never VIN -- that is the point.
    "PGOOD":  3.5,   # R3 pulls up to VCC (3.1-3.5 V), not to VIN
    "FB":     7.0,
    "SW":    36.0,
}
# Pins deliberately not covered, each with the reason it cannot be:
ABS_MAX_EXEMPT = {
    "7": "BOOT is rated 5.5 V to SW, not to GND, so a net-to-GND ceiling cannot "
         "express it. The capacitor is internal and the pin is a no-connect.",
}


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
    raise ValueError("unbalanced s-expression")


def load_symbol(lib_id):
    """Pull one symbol out of a library and rename it to its full lib_id.

    The rename is not cosmetic: KiCad matches lib_symbols entries by full lib_id,
    and a bare name either crashes kicad-cli or exports an EMPTY netlist at
    exit 0 -- a failure that looks exactly like success.
    """
    path = SRC[lib_id]
    name = lib_id.split(":", 1)[1]
    text = path.read_text()
    m = re.search(r'\(symbol\s+"' + re.escape(name) + r'"[\s\)]', text)
    if not m:
        raise KeyError(f"{lib_id}: symbol {name!r} not found in {path}")
    blk = _block(text, m.start())
    return blk.replace(f'(symbol "{name}"', f'(symbol "{lib_id}"', 1)


def parse_pins(blk):
    """[(number, x, y)] walking each balanced (pin ...) block.

    Deliberately not a two-field regex: pairing an (at ...) with a later
    (number ...) across block boundaries invents self-consistent fictional pins.
    """
    pins = []
    for m in re.finditer(r"\(pin\s", blk):
        pb = _block(blk, m.start())
        at = re.search(r"\(at\s+(-?[\d.]+)\s+(-?[\d.]+)", pb)
        num = re.search(r'\(number\s+"([^"]*)"', pb)
        if at and num:
            pins.append((num.group(1), float(at.group(1)), float(at.group(2))))
    if not pins:
        raise ValueError("parse_pins found no pins -- an empty scan is not a clean scan")
    return pins


LIBS = {lid: load_symbol(lid) for lid in SRC}
LIBPINS = {lid: ([] if lid in NO_PINS else parse_pins(blk)) for lid, blk in LIBS.items()}
for lid, pins in LIBPINS.items():
    assert pins or lid in NO_PINS, f"{lid} parsed to zero pins"

INST, BOM = {}, {}
# ref -> (dx, dy_reference, dy_value); see the emitter.
PROP_OFFSET = {
    "U1": (-12.7, -20.32, -17.78),          # above the body, not inside it
    "J1": (3.81, -8.89, -6.35),             # clear of the three pin numbers
}
_RAILS, _SEGS, _LABELS, _NOCONN = [], [], [], []
_PINNET = []      # (ref, pin, net) for the abs-max audit


def uid(*parts):
    h = hashlib.sha1((NAME + "/" + "/".join(str(p) for p in parts)).encode()).hexdigest()
    return f"{h[0:8]}-{h[8:12]}-5{h[13:16]}-a{h[17:20]}-{h[20:32]}"


def ongrid(v):
    return abs(round(v / GRID) - v / GRID) < 1e-6


def _xf(px, py, ang, mirror):
    """Symbol-local pin coords -> global offset. KiCad rotates FIRST, then mirrors."""
    x, y = px, -py
    a = math.radians(ang)
    ca, sa = round(math.cos(a)), round(math.sin(a))
    x, y = x * ca + y * sa, -x * sa + y * ca
    if mirror == "x":
        y = -y
    elif mirror == "y":
        x = -x
    return (x, y)


def place(ref, lib_id, x, y, ang=0, mirror=None, **props):
    assert ongrid(x) and ongrid(y), f"{ref} placed off-grid at ({x}, {y})"
    assert ref not in INST, f"duplicate reference {ref}"
    INST[ref] = (lib_id, x, y, ang, mirror)
    BOM[ref] = props
    return ref


def pn(ref, num):
    lib_id, X, Y, ang, mir = INST[ref]
    for n, lx, ly in LIBPINS[lib_id]:
        if n == str(num):
            dx, dy = _xf(lx, ly, ang, mir)
            return (round(X + dx, 4), round(Y + dy, 4))
    raise KeyError(f"{ref} ({lib_id}) has no pin {num}")


def rail(lib_id, x, y, ang=0):
    ref = f"#FLG{len(_RAILS):03d}" if "FLAG" in lib_id else f"#PWR{len(_RAILS):03d}"
    place(ref, lib_id, x, y, ang)
    ys = [float(v) for v in re.findall(r"\(xy\s+-?[\d.]+\s+(-?[\d.]+)\)", LIBS[lib_id])]
    ys += [float(v) for v in re.findall(r"\(start\s+-?[\d.]+\s+(-?[\d.]+)\)", LIBS[lib_id])]
    ys += [float(v) for v in re.findall(r"\(end\s+-?[\d.]+\s+(-?[\d.]+)\)", LIBS[lib_id])]
    assert ys, f"{lib_id}: no graphic geometry found -- cannot derive orientation"
    graphic_down = (min(ys) < 0) and (max(ys) <= 0.01)
    if ang == 180:
        graphic_down = not graphic_down
    _RAILS.append((lib_id, x, y, graphic_down))
    return ref


def wire(p1, p2):
    (x1, y1), (x2, y2) = p1, p2
    for v in (x1, y1, x2, y2):
        assert ongrid(v), f"off-grid wire endpoint {(x1, y1, x2, y2)}"
    assert x1 == x2 or y1 == y2, f"diagonal wire {(x1, y1, x2, y2)}"
    assert (x1, y1) != (x2, y2), f"zero-length wire at {(x1, y1)}"
    _SEGS.append((x1, y1, x2, y2))


def label(text, p, ang=0):
    assert ongrid(p[0]) and ongrid(p[1]), f"off-grid label {text} at {p}"
    _LABELS.append((text, p[0], p[1], ang))


def noconn(p):
    _NOCONN.append(p)


_NC_PINS = []     # (ref, pin) deliberately left unconnected


def noconn_pin(ref, pin):
    """No-connect a pin BY NAME, and record which pin it was.

    The bare point is what KiCad needs; the (ref, pin) is what check_netlist.py
    needs in order to confirm that the `unconnected-*` net KiCad invents belongs
    to the pin we meant, and not to one we forgot to wire.
    """
    noconn(pn(ref, pin))
    _NC_PINS.append((ref, str(pin)))


def net(ref, pin, name):
    """Declare which net a pin belongs to, for check_abs_max().

    Declared rather than extracted: extracting connectivity from the geometry
    here would make the audit agree with the drawing by construction, and an
    audit that shares its input with the thing it audits checks nothing. This
    is the INTENT; --schematic-parity and the netlist diff in DESIGN.md are what
    confirm the drawing matches it.
    """
    _PINNET.append((ref, str(pin), name))


def stub(p, dx=0.0, dy=0.0):
    """Wire from a pin to an offset point and return that point."""
    q = (round(p[0] + dx, 4), round(p[1] + dy, 4))
    wire(p, q)
    return q


# =============================================================================== sheet
#
#   C2 C1 | JP1 R6  R4 R5 |  U1  | R3 TP2 | R1 R2 C6 | C4
#   CIN     MODE     EN            PGOOD    FB div     COUT
#                                  VCC: C3 to the far right
#   J1 header far left; SW/BOOT/GND under U1.
#
# Lane discipline: every fan-out net owns one vertical x lane and every stub
# leaves U1 on its own horizontal y, so no wire ever crosses another net's lane.
# The y slots come from the symbol (gen_sym.PINS), not from eyeballing.

UX, UY = 152.4, 101.6

place("U1", "buck-tpsm33610:TPSM33610S3Q", UX, UY,
      Value="TPSM33610S3Q",
      Footprint="buck-tpsm33610:TPSM336xx_QFN-FCMOD-11_RDN0011B_TI",
      MPN="TPSM33610S3QRDNRQ1", Manufacturer="Texas Instruments",
      Spec="3-36 V in, 3.3 V fixed +/-1 % out, 1 A, 2.2 MHz, DRSS, "
           "QFN-FCMOD-11 RDN0011B. SNVSCS7E rev E.",
      DNP="no")

# --- VIN into the module ------------------------------------------------------------
_vin = stub(pn("U1", "3"), dx=-7.62); label("VIN", _vin, 180); net("U1", 3, "VIN")

# --- CIN. Table 8-3 asks for 4.7 uF + 100 nF, and Table 8-5's reference parts are
#     4.7 uF 50 V X7R 1210 (nameplate values, footnote 2). C1 is sized to match
#     that reference at the bus voltage, not its nameplate. Vendor DC-bias curves
#     (25 C), effective uF at 12 / 24 / 36 V, fetched 2026-09-13:
#       Samsung CL32B475KBUYNNE  4.7u 1210 X7R (TI reference class)  4.15 / 3.10 / 2.22
#       TDK CGA5L1X7R1H106K160AC 10u 1206 X7R  (this part)           6.95 / 3.70 / 2.21
#       Samsung CL31B106KBHNNNE  10u 1206 X7R                         4.65 / 2.11 / 1.27
#       Murata GRM21BR61H106KE43 10u 0805 X5R                         2.72 / 1.35 / 0.88
#     Not every 1206 10 uF is equal: the Samsung loses a third against the TDK at
#     24 V, and 0805 falls to ~40 % of the reference. The previous MPN here,
#     GRM32ER71H226ME15L, is unknown to both DigiKey and Murata SimSurfing.
place("C1", "Device:C_Small", 96.52, 88.9,
      Value="10u", MPN="CGA5L1X7R1H106K160AC", Manufacturer="TDK",
      Spec="10 uF 50 V X7R 1206 AEC-Q200 -- CIN bulk. 3.7 uF effective at 24 V, "
           "2.2 uF at 36 V: equal to TI's 4.7 uF 1210 reference (Table 8-5) at bias.",
      Footprint="Capacitor_SMD:C_1206_3216Metric", DNP="no")
_c1 = stub(pn("C1", "1"), dy=-3.81); net("C1", 1, "VIN")
rail("power:GND", *stub(pn("C1", "2"), dy=5.08)); net("C1", 2, "GND")

place("C2", "Device:C_Small", 86.36, 88.9,
      Value="1u", MPN="CL10B105KB8NQNC", Manufacturer="Samsung Electro-Mechanics",
      Spec="1 uF 50 V X7R 0603 -- CIN HF, on F.Cu directly below the EN/VIN 0R "
           "(all SMD parts front side, Fab 2026-09-13). SHARED PART with C3 "
           "(Fab 2026-09-14, 'merge what you can'): one 0603 line serves CIN HF "
           "and CVCC. Chosen on EFFECTIVE value, from Samsung's own measured "
           "DC-bias data (weblib.samsungsem.com, read 2026-09-14): 552/251/142 nF "
           "at 12/24/36 V, against 95/76/56 nF for the 100 nF CL10B104JB8NNNC it "
           "replaces -- 2.6x more charge at the 36 V corner, same 0603 ESL. "
           "Samsung's numbers for that 100 nF part reproduce the 93/75/55 nF this "
           "field used to quote, which is the cross-check on both.",
      Footprint="Capacitor_SMD:C_0603_1608Metric", DNP="no")
_c2 = stub(pn("C2", "1"), dy=-3.81); net("C2", 1, "VIN")
# One label, not two: C1 and C2 are the same bank 10 mm apart, and the wiring
# guard is right that two labels there is soup rather than fan-out.
wire(_c2, _c1); label("VIN", _c2, 180)
rail("power:GND", *stub(pn("C2", "2"), dy=5.08)); net("C2", 2, "GND")

# --- EN: tied to VIN, liftable, and the top leg of an optional precision UVLO -------
# EN must not float (p.5) and may be tied straight to VIN: abs max 40 V equals
# VIN's own, and the leakage is 10 nA. R4 is a 0 ohm RESISTOR rather than a track
# so EN can be driven from TP1 by lifting one part, or turned into a UVLO divider
# by fitting R5 and giving R4 a value (VEN_RISE 1.23 V, VEN_FALL 0.90 V).
EN_X = 124.46
en = stub(pn("U1", "2"), dx=-(pn("U1", "2")[0] - EN_X)); net("U1", 2, "EN")
label("EN", en, 180)
place("R4", "Device:R_Small", EN_X, 90.17,
      Value="0R", MPN="RC0402JR-070RL", Manufacturer="YAGEO",
      Spec="EN pull-up to VIN. 0 ohm as fitted; becomes the TOP leg of a "
           "precision UVLO divider if R5 is fitted. EN must not float.",
      Footprint="Resistor_SMD:R_0402_1005Metric", DNP="no")
wire(pn("R4", "2"), en)
_r4 = stub(pn("R4", "1"), dy=-3.81)
wire(_r4, (_vin[0], _r4[1])); wire((_vin[0], _r4[1]), _vin)
net("R4", 1, "VIN"); net("R4", 2, "EN")
place("R5", "Device:R_Small", EN_X, 102.87,
      Value="DNP", NoMPN="not fitted -- value is the user's UVLO choice",
      Spec="EN divider BOTTOM leg, EN to GND. Not fitted. Fit with a value in "
           "R4 to set an input UVLO: Von = 1.23 V * (R4+R5)/R5.",
      Footprint="Resistor_SMD:R_0402_1005Metric", DNP="yes")
wire(pn("R5", "1"), en); rail("power:GND", *stub(pn("R5", "2"), dy=3.81))
net("R5", 1, "EN"); net("R5", 2, "GND")
# TP1 taps the U1 stub mid-run rather than joining the R4/R5 node: four wires
# meeting at one point is a four_way_junction, which KiCad ships at "ignore" and
# project_settings.py deliberately re-enables. Three-way joins everywhere.
place("TP1", "Connector:TestPoint", 129.54, 104.14, ang=0,
      Value="EN", Footprint="buck-tpsm33610:TestPad_1.0x1.0mm",
      NoMPN="bare copper solder pad, nothing to fit",
      Spec="Pull low to disable. Open-drain or a switch to GND; do not drive high "
           "against R4.", DNP="no")
_t = pn("TP1", "1"); wire(_t, (_t[0], en[1])); net("TP1", 1, "EN")

# --- MODE/SYNC: default auto/PFM, and the pin this part invites you to kill ---------
# Abs max 5.5 V. It must not float, and it must NOT be tied to VIN. Default is
# auto mode (R6 to GND, VMODE < 1 V): best light-load efficiency, 1.2 uA IQ, and
# the factory spread spectrum stays ON, which only happens on the free-running
# clock. R6 is a resistor and not 0 ohm so an external clock on TP3 can override
# it without shorting the driver.
#
# Fab, 2026-09-13 ("can you add solder jumper(s) for mode?"): FPWM used to be a
# two-part rework -- fit R7, remove R6. It is now ONE solder blob on JP1, which
# ties MODE straight to VCC (3.1-3.5 V: above VMODE_H 1.6 V, below the 5.5 V abs
# max, and the only legal on-board source -- VIN reaches 36 V).
#
# THIS is why R6 went 10k -> 100k. With JP1 bridged, R6 is no longer a strap to
# be removed, it is a load hung across VCC: 10k would draw 330 uA out of an LDO
# the datasheet says to leave unloaded, 100k draws 33 uA. MODE's own input is
# nA, so 100k still holds it at ~0 V with JP1 open, and a clock on TP3 drives a
# 100k pull-down more easily than a 10k one, not less.
#
# ONE jumper, not a 3-way selector, and not a normally-closed one to cut:
#   - all three MODE states are still reachable -- auto (open), FPWM (bridged),
#     SYNC (clock on the TP3 pad, which overrides through 100k either way);
#   - a bare 3-pad selector ships with MODE FLOATING until someone bridges it,
#     and floating is the one state this pin must never be in. R6 is fitted, so
#     an untouched board is in a defined mode by construction;
#   - the 2.3 x 1.5 mm stock jumper land does not fit the west margin. JP1 is a
#     project footprint on the 0402 pad centres R7 used, so no track moved.
# Bridging JP1 while ALSO driving TP3 shorts an external driver to VCC -- said in
# JP1's Spec field and on the pad's own line in DESIGN.md, not left to be found.
MODE_X = 111.76
MODE_Y = 127.0
# MODE dog-legs DOWN before it runs west. A straight run at the pin's own y put
# it through (124.46, 109.22) -- which is exactly where R5's ground stub ends --
# and shorted MODE to GND. ERC found it ([multiple_net_names]) the first time the
# pin moved; the jog keeps the run clear of the EN lane by construction rather
# than by the two constants happening to differ.
_m = pn("U1", "11")
_a = stub(_m, dx=-5.08)
_b = (_a[0], MODE_Y); wire(_a, _b)
mo = (MODE_X, MODE_Y); wire(_b, mo)
net("U1", 11, "MODE")
label("MODE", mo, 180)
assert _a[0] != EN_X, "the MODE jog now shares the EN lane"
place("R6", "Device:R_Small", MODE_X, 133.35,
      Value="100k", MPN="RC0402FR-07100KL", Manufacturer="YAGEO",
      Spec="MODE/SYNC pull-down -> AUTO mode with spread spectrum (Table 7-2). "
           "100k not 0R so a clock on TP3 can override without shorting it, and "
           "not 10k because JP1 bridged hangs this resistor across VCC: 33 uA, "
           "not 330 uA.",
      Footprint="Resistor_SMD:R_0402_1005Metric", DNP="no")
wire(pn("R6", "1"), mo); rail("power:GND", *stub(pn("R6", "2"), dy=3.81))
net("R6", 1, "MODE"); net("R6", 2, "GND")
# ang=270, not 90: the stock jumper symbol is drawn HORIZONTALLY (pins at x
# +/-5.08) and this strap runs north-south like the R7 it replaces. At 90 pin 1
# lands SOUTH, so the VCC stub crossed pin 2's wire on its way to MODE and shorted
# VCC to MODE -- caught as ERC [multiple_net_names], the same way the MODE jog was.
place("JP1", "Jumper:SolderJumper_2_Open", MODE_X, 120.65, ang=270,
      Value="FPWM", NoMPN="solder bridge, nothing to fit",
      Spec="OPEN = auto/PFM (default, R6 holds MODE low). BRIDGE = MODE tied to "
           "VCC (3.1-3.5 V; > VMODE_H 1.6 V, < the 5.5 V abs max) -> FPWM, and "
           "R6 then draws 33 uA off VCC. Do NOT drive the MODE pad from outside "
           "while this is bridged -- that is a driver shorted to VCC.",
      Footprint="buck-tpsm33610:SolderJumper_2_P1.00mm_Open_Pad0.8x0.4mm",
      DNP="no")
wire(pn("JP1", "2"), mo); label("VCC", stub(pn("JP1", "1"), dy=-3.81), 180)
net("JP1", 1, "VCC"); net("JP1", 2, "MODE")
place("TP3", "Connector:TestPoint", 119.38, 134.62, ang=0,
      Value="MODE", Footprint="buck-tpsm33610:TestPad_1.0x1.0mm",
      NoMPN="bare copper solder pad, nothing to fit",
      Spec="Auto (low) / FPWM (>1.6 V) / external clock 1.9-2.5 MHz. "
           "ABS MAX 5.5 V -- do not drive from VIN.", DNP="no")
_t = pn("TP3", "1"); wire(_t, (_t[0], mo[1])); net("TP3", 1, "MODE")

# --- VOUT out of the module ---------------------------------------------------------
_vout = stub(pn("U1", "4"), dx=7.62); label("VOUT", _vout, 0); net("U1", 4, "VOUT")

# --- FB and the fixed/adjustable selector -------------------------------------------
# SNVSCS7E 7.3.2.1 (p.12): the module "determines whether fixed output voltage or
# adjustable output voltage is required by SENSING THE RESISTANCE OF THE FEEDBACK
# PATH during start-up". So a fitted 0 ohm RFBT is not a jumper bodge -- it is
# exactly the condition the part tests for, and the S3 fixed trim then applies.
# To go adjustable: replace R1 with the computed RFBT, fit R2 and C6.
#   RFBT = RFBB * (VOUT/1V - 1),  5k <= RFBT||RFBB <= 10k   (Eq 1-3, p.12)
#   3.3 V -> 33.2k / 14.3k     5 V -> 49.9k / 12.4k     7 V -> 69.8k / 11.5k
FB_X = 195.58
fb = stub(pn("U1", "9"), dx=FB_X - pn("U1", "9")[0]); net("U1", 9, "FB")
label("FB", fb, 0)
place("R1", "Device:R_Small", FB_X, 90.17,
      Value="0R", MPN="RC0402JR-070RL", Manufacturer="YAGEO",
      Spec="RFBT. 0 ohm = fixed 3.3 V (start-up senses the feedback path and "
           "selects the factory trim). Replace with RFBT and fit R2 + C6 for "
           "1-7 V adjustable.",
      Footprint="Resistor_SMD:R_0402_1005Metric", DNP="no")
wire(pn("R1", "2"), fb); _r1 = stub(pn("R1", "1"), dy=-3.81)
net("R1", 1, "VOUT"); net("R1", 2, "FB")
place("R2", "Device:R_Small", FB_X, 102.87,
      Value="DNP", NoMPN="not fitted -- fixed-output build",
      Spec="RFBB, FB to GND. Not fitted: with R1 = 0 ohm the part must see a "
           "SHORT feedback path, and a fitted R2 would make it a divider.",
      Footprint="Resistor_SMD:R_0402_1005Metric", DNP="yes")
wire(pn("R2", "1"), fb); rail("power:GND", *stub(pn("R2", "2"), dy=3.81))
net("R2", 1, "FB"); net("R2", 2, "GND")
place("C6", "Device:C_Small", 185.42, 90.17,
      Value="DNP", NoMPN="not fitted -- adjustable-output build only",
      Spec="CFF across RFBT, ~10 pF C0G. Table 8-1 note: adjustable output only. "
           "With R1 = 0 ohm it would be shorted.",
      Footprint="Capacitor_SMD:C_0402_1005Metric", DNP="yes")
_c6 = stub(pn("C6", "1"), dy=-3.81); net("C6", 1, "VOUT")
assert _c6[1] == _r1[1], "C6 and R1 top stubs no longer share a y"
wire(_c6, _r1)
# ...and run that bus back to U1's own VOUT stub rather than labelling it: the
# feedback tap is 9 mm from the pin it senses, which is fan-out by distance only.
wire(_c6, (_vout[0], _c6[1])); wire((_vout[0], _c6[1]), _vout)
c6b = stub(pn("C6", "2"), dy=3.81)
assert c6b[1] == fb[1], "C6 lower stub no longer lands on the FB run"
net("C6", 2, "FB")

# --- PGOOD --------------------------------------------------------------------------
# Open drain, 10k-100k (p.5). Pulled up to VCC, the module's internal 3.3 V LDO,
# which p.5 names for exactly this: "Can be used as logic supply for power-good
# flag." Never to VIN (PG abs max 20 V, VIN reaches 36).
# It was VOUT until 2026-09-13. The single-header layout turns U1 so VIN and VOUT
# face the header; PGOOD and VCC then sit on the far side together, and VOUT would
# have had to cross the module to reach R3. VCC also stays alive while VOUT is
# down, so PGOOD reads a valid LOW during a fault instead of floating with the rail.
# 100k is the top of TI's range: 33 uA when asserted.
PG_X = 177.8
pg = stub(pn("U1", "1"), dx=PG_X - pn("U1", "1")[0]); net("U1", 1, "PGOOD")
label("PGOOD", pg, 0)
place("R3", "Device:R_Small", PG_X, 100.33,
      Value="100k", MPN="RC0402FR-07100KL", Manufacturer="YAGEO",
      Spec="PGOOD pull-up to VCC (internal 3.3 V LDO, p.5 permits it). "
           "10k-100k per p.5; 100k minimises IQ. PG abs max 20 V: never to VIN.",
      Footprint="Resistor_SMD:R_0402_1005Metric", DNP="no")
wire(pn("R3", "2"), pg)
label("VCC", stub(pn("R3", "1"), dy=-3.81), 180)
net("R3", 1, "VCC"); net("R3", 2, "PGOOD")
place("TP2", "Connector:TestPoint", PG_X, 111.76, ang=180,
      Value="PGOOD", Footprint="buck-tpsm33610:TestPad_1.0x1.0mm",
      NoMPN="bare copper solder pad, nothing to fit",
      Spec="High = power good. Thresholds 108 % rising / 91 % falling of VOUT.",
      DNP="no")
wire(pg, pn("TP2", "1")); net("TP2", 1, "PGOOD")

# --- VCC: internal LDO, decoupling only --------------------------------------------
VCC_X = 208.28
vcc = stub(pn("U1", "8"), dx=VCC_X - pn("U1", "8")[0]); net("U1", 8, "VCC")
label("VCC", vcc, 180)
place("C3", "Device:C_Small", VCC_X, 120.65,
      Value="1u", MPN="CL10B105KB8NQNC", Manufacturer="Samsung Electro-Mechanics",
      Spec="CVCC 1 uF 50 V X7R 0603 -- Table 8-3. 0603 not 0402: VCC feeds the "
           "gate drivers and a 0402 X5R would hold about half of this at bias. "
           "VCC drives NO external load (p.5). SHARED PART with C2 (Fab "
           "2026-09-14, 'merge what you can'). 50 V where 25 V would do, because "
           "C2 sees 36 V and one line has to cover both; at this position's 3.3 V "
           "it holds 1.021 uF (Samsung measured DC-bias data, 2026-09-14), so the "
           "merge costs this position nothing and gains derating margin. Replaces "
           "TDK CGA3E1X7R1E105K080AC -- that was AEC-Q200 and this is not, which "
           "is the one thing the merge gives up. No TDK CGA equivalent exists at "
           "1 uF / 50 V in 0603.",
      Footprint="Capacitor_SMD:C_0603_1608Metric", DNP="no")
wire(pn("C3", "1"), vcc); rail("power:GND", *stub(pn("C3", "2"), dy=3.81))
net("C3", 1, "VCC"); net("C3", 2, "GND")

# --- COUT ---------------------------------------------------------------------------
place("C4", "Device:C_Small", 218.44, 88.9,
      Value="22u", MPN="EMK316BB7226ML-T", Manufacturer="Taiyo Yuden",
      Spec="COUT 22 uF 16 V X7R 1206 -- Table 8-3 for the 1 A part is 1 x 22 uF. "
           "16 V covers the whole 1-7 V adjustable range. In Fab's InvenTree stock "
           "(pk 379, 50 pcs, 2026-09-13); replaces GRM31CR71C226KE15L, which neither "
           "DigiKey nor Murata SimSurfing knows.",
      Footprint="Capacitor_SMD:C_1206_3216Metric", DNP="no")
_c4 = stub(pn("C4", "1"), dy=-3.81); net("C4", 1, "VOUT"); label("VOUT", _c4, 180)
rail("power:GND", *stub(pn("C4", "2"), dy=5.08)); net("C4", 2, "GND")

# C5, a second COUT position, was carried here until the floorplan review. It
# did not fit: the south band between the module land and the header row is
# 2.4 mm, and once COUT (1206) and the MODE strap are in it there is nowhere a
# second output capacitor can go that clears both. Table 8-3 asks for ONE 22 uF
# on the 1 A part; the second one is Table 8-2's, which is the 2 A part and the
# adjustable configurations. If this board is ever re-jumpered adjustable and
# wants more output capacitance, it goes on the far side of the header on the
# carrier board, not here.

# --- SW and BOOT: the two pins whose correct treatment is to do nothing -------------
# p.5, SW: "Do not place any external component on this pin or connect to any
# signal." Pins 5 and 6 are the same internal node; the schematic joins them so
# the net has two members and ERC has nothing to report, and gen_pcb.py holds
# that net to lands plus one inter-land stub. BOOT's capacitor is INTERNAL.
sw5 = stub(pn("U1", "5"), dy=5.08)
sw6 = stub(pn("U1", "6"), dy=5.08)
wire(sw5, sw6); label("SW", sw5, 0)
net("U1", 5, "SW"); net("U1", 6, "SW")
noconn_pin("U1", "7")
rail("power:GND", *stub(pn("U1", "10"), dy=5.08)); net("U1", 10, "GND")

# --- J1: the header. One row, three pins, power only. -----------------------------
# VIN / GND / VOUT, pin 1 = VIN. The control pins are solder pads, not header pins.
# (Until 2026-09-13 this was two identical 1x04 rows, VIN GND GND VOUT, on
# 0.4 in centres. Fab replaced them with this single 1x03: the two rows placed
# but could not route, because every rail had to reach both rows through bands
# that the straps already filled.)
place("J1", "Connector_Generic:Conn_01x03", 45.72, 96.52, ang=180,
      Value="1x03",
      Footprint="Connector_buck-tpsm33610:PinHeader_1x03_P2.54mm_Vertical_NoSilk",
      MPN="61300311121", Manufacturer="Wuerth Elektronik",
      Spec="1=VIN 2=GND 3=VOUT. VIN 3-36 V (40 V abs max, NO input protection "
           "on this board). VOUT 3.3 V, 1 A.",
      DNP="no")
for pin, nname in enumerate(variants.HDR_NETS, start=1):
    label(nname, stub(pn("J1", pin), dx=-7.62), 180)
    net("J1", pin, nname)

# --- PWR_FLAG: VIN and GND are sourced only by passive connector pins ---------------
label("VIN", (63.5, 96.52), 0)
wire((63.5, 96.52), (63.5, 99.06))
rail("power:PWR_FLAG", 63.5, 99.06, ang=180)

rail("power:PWR_FLAG", 73.66, 96.52)
rail("power:GND", 73.66, 99.06)
wire((73.66, 96.52), (73.66, 99.06))


# =============================================================================== audits
def junctions():
    """Points that need an explicit junction dot.

    Two cases, and the second is the dangerous one: KiCad connects wires that
    SHARE AN ENDPOINT, but a wire whose endpoint lands in the MIDDLE of another
    wire is connected only if a junction is there. Emitting none would leave a
    net silently split; emitting one where three collinear ends meet is
    harmless. So: >=3 endpoints at a point, or an endpoint interior to a segment.
    """
    from collections import Counter
    ends = Counter()
    for (x1, y1, x2, y2) in _SEGS:
        ends[(x1, y1)] += 1
        ends[(x2, y2)] += 1
    js = {p for p, n in ends.items() if n >= 3}
    for (px, py) in list(ends):
        for (x1, y1, x2, y2) in _SEGS:
            if (px, py) in ((x1, y1), (x2, y2)):
                continue
            if x1 == x2 == px and min(y1, y2) < py < max(y1, y2):
                js.add((px, py))
            elif y1 == y2 == py and min(x1, x2) < px < max(x1, x2):
                js.add((px, py))
    return sorted(js)


def check_rail_orientation():
    bad = []
    for lib_id, x, y, graphic_down in _RAILS:
        for (x1, y1, x2, y2) in _SEGS:
            for (ax, ay), (bx, by) in (((x1, y1), (x2, y2)), ((x2, y2), (x1, y1))):
                if (ax, ay) != (x, y) or ax != bx:
                    continue
                if (by > ay) == graphic_down:
                    bad.append(f"{lib_id} at ({x},{y}) drawn over its own wire")
    for lib_id, x, y, graphic_down in _RAILS:
        y0, y1 = (y, y + 2.54) if graphic_down else (y - 2.54, y)
        x0, x1 = x - 1.27, x + 1.27
        for (ax, ay, bx, by) in _SEGS:
            if ax == bx and x0 < ax < x1 and min(ay, by) < y1 and max(ay, by) > y0:
                bad.append(f"{lib_id} at ({x},{y}) glyph crosses vertical wire")
            elif ay == by and y0 < ay < y1 and min(ax, bx) < x1 and max(ax, bx) > x0:
                bad.append(f"{lib_id} at ({x},{y}) glyph crosses horizontal wire")
    if bad:
        raise AssertionError("rail orientation:\n  " + "\n  ".join(sorted(set(bad))))
    return len(_RAILS)


def check_labels_on_wires():
    ends = set()
    for (x1, y1, x2, y2) in _SEGS:
        ends.add((x1, y1))
        ends.add((x2, y2))
    orphan = [(t, x, y) for t, x, y, _ in _LABELS if (x, y) not in ends]
    if orphan:
        raise AssertionError("labels not on a wire endpoint: " + repr(orphan))
    return len(_LABELS)


def check_no_symbol_overlap():
    boxes = []
    for ref, (lib_id, X, Y, ang, mir) in INST.items():
        pts = [_xf(px, py, ang, mir) for _, px, py in LIBPINS[lib_id]]
        half = NO_PINS.get(lib_id, 0.0)
        xs = [X + p[0] for p in pts] or [X - half, X + half]
        ys = [Y + p[1] for p in pts] or [Y - half, Y + half]
        boxes.append((ref, min(xs) - 0.5, min(ys) - 0.5, max(xs) + 0.5, max(ys) + 0.5))
    bad = []
    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            a, b = boxes[i], boxes[j]
            if a[1] < b[3] and b[1] < a[3] and a[2] < b[4] and b[2] < a[4]:
                bad.append(f"{a[0]} overlaps {b[0]}")
    if bad:
        raise AssertionError("symbol overlap:\n  " + "\n  ".join(bad))
    return len(boxes)


def check_bom_complete():
    missing = []
    for ref, props in BOM.items():
        if ref.startswith("#"):
            continue
        if not props.get("MPN") and not props.get("NoMPN"):
            missing.append(f"{ref} (no MPN)")
        if not props.get("Footprint"):
            missing.append(f"{ref} (no Footprint)")
    if missing:
        raise AssertionError(f"incomplete BOM rows: {missing}")
    stale = [r for r in BOM if r not in INST]
    if stale:
        raise AssertionError(f"BOM rows with no placed part: {stale}")
    return len([r for r in BOM if not r.startswith("#")])


def check_abs_max():
    """No U1 pin may sit on a net that can exceed its absolute maximum rating.

    This is the audit this part needs. MODE/SYNC (5.5 V) is two pins from VIN
    (40 V) in the pinout, PGOOD (20 V) invites a pull-up to the input rail, and
    VCC (3.5 V) is an output that looks like a supply you can strap things to.
    """
    declared = {}
    for ref, pin, name in _PINNET:
        declared.setdefault(ref, {})[pin] = name
    u1 = declared.get("U1", {})
    unknown = [n for n in u1.values() if n not in NET_VMAX]
    if unknown:
        raise AssertionError(f"U1 sits on nets with no declared ceiling: {sorted(set(unknown))}")
    covered = set(u1) | set(ABS_MAX_EXEMPT)
    want = {p[0] for p in gen_sym.PINS}
    if covered != want:
        raise AssertionError(f"U1 pins neither netted nor exempt: {sorted(want - covered, key=int)}")
    bad = []
    for pin, nname in sorted(u1.items(), key=lambda kv: int(kv[0])):
        if pin in ABS_MAX_EXEMPT:
            raise AssertionError(f"pin {pin} is both netted and exempt -- pick one")
        lim = gen_sym.ABS_MAX.get(pin)
        if lim is None:
            if pin != "10":
                bad.append(f"pin {pin} has no abs-max entry")
            continue
        if NET_VMAX[nname] > lim + 1e-9:
            bad.append(f"pin {pin} on net {nname} can reach {NET_VMAX[nname]} V, "
                       f"abs max {lim} V")
    if bad:
        raise AssertionError("ABSOLUTE MAXIMUM VIOLATION:\n  " + "\n  ".join(bad))
    for ref, pins in declared.items():
        for pin, nname in pins.items():
            if nname not in NET_VMAX:
                raise AssertionError(f"{ref}.{pin} on undeclared net {nname}")
    return len(u1)


def check_pin_coverage():
    """Every pin of every placed part must be declared on a net or no-connected.

    Counted from the symbol libraries, not from the declaration list, so a pin
    that was simply forgotten fails here rather than turning into a silent
    single-node net in the exported netlist.
    """
    ncpts = {tuple(p) for p in _NOCONN}
    declared = {(r, p) for r, p, _ in _PINNET}
    missing = []
    for ref, (lib_id, X, Y, ang, mir) in INST.items():
        if ref.startswith("#"):
            continue
        for num, _, _ in LIBPINS[lib_id]:
            if (ref, num) in declared:
                continue
            if pn(ref, num) in ncpts:
                continue
            missing.append(f"{ref}.{num}")
    if missing:
        raise AssertionError(f"pins neither netted nor no-connected: {sorted(missing)}")
    return len(declared)


def check_dnp_exclusivity():
    """Mutually exclusive fit options must not both be fitted."""
    fitted = {r for r, p in BOM.items() if p.get("DNP") != "yes" and not r.startswith("#")}
    # R6/R7 used to be an exclusive pair -- fit one OR the other. JP1 retired
    # that: R6 is now ALWAYS fitted and the jumper does the selecting, so there
    # is no fit conflict left on MODE to check. What replaced it is
    # check_mode_never_floats() below, which is the property the old pair was a
    # proxy for.
    pairs = [("R1", "R2", "R1 = 0 ohm is the FIXED selector; a fitted R2 makes it "
                          "a divider and the part would sense an adjustable path")]
    bad = [why for a, b, why in pairs if a in fitted and b in fitted]
    if bad:
        raise AssertionError("fit-option conflict:\n  " + "\n  ".join(bad))
    return len(fitted)


def check_bom_lines():
    """Count distinct purchased lines, and hold merged parts to actually being one part.

    Several positions deliberately SHARE an MPN so the order has fewer lines:
    R1/R4 (0R), R3/R6 (100k) and, since 2026-09-14, C2/C3 (1 uF 50 V 0603).
    A shared line is only real if everything about the part matches -- if someone
    retunes C2's value and leaves C3's MPN pointing at it, the BOM still shows one
    line while the board wants two different capacitors, and the error surfaces as
    a wrong part fitted rather than as anything a check would see.

    So: group fitted parts by MPN, and require Value and Footprint to agree inside
    each group. DNP positions are excluded -- they are lands, not purchases.
    """
    by_mpn = {}
    for ref, p in BOM.items():
        if ref.startswith("#") or p.get("DNP") == "yes" or not p.get("MPN"):
            continue
        by_mpn.setdefault(p["MPN"], []).append((ref, p.get("Value"), p.get("Footprint")))
    bad = []
    for mpn, items in sorted(by_mpn.items()):
        vals = {v for _, v, _ in items}
        fps = {f for _, _, f in items}
        if len(vals) > 1 or len(fps) > 1:
            bad.append(f"{mpn} is shared by {[r for r, _, _ in items]} but they disagree: "
                       f"values {sorted(vals)}, footprints {sorted(fps)}")
    if bad:
        raise AssertionError("a shared BOM line is not one part:\n  " + "\n  ".join(bad))
    shared = {m: [r for r, _, _ in i] for m, i in by_mpn.items() if len(i) > 1}
    return len(by_mpn), shared


def check_mode_never_floats():
    """MODE must sit at a defined level on an UNTOUCHED board.

    SNVSCS7E: MODE/SYNC may not float. The solder jumper makes that a live
    question rather than a settled one -- a board arrives with JP1 open, so the
    ONLY thing holding MODE is R6, and if R6 were ever made DNP (or turned into
    the pull-UP half of a divider) every unbridged board would ship with a
    floating mode pin and nothing downstream would notice.

    So: a fitted resistor from MODE to GND, and the jumper open by default.
    """
    pinnet = {(r, p): n for r, p, n in _PINNET}
    bad = []
    r6 = BOM.get("R6") or {}
    if not r6 or r6.get("DNP") == "yes":
        bad.append("R6 is not fitted -- with JP1 open, nothing holds MODE")
    if (pinnet.get(("R6", "1")), pinnet.get(("R6", "2"))) != ("MODE", "GND"):
        bad.append(f"R6 is not MODE-to-GND: {pinnet.get(('R6', '1'))} / "
                   f"{pinnet.get(('R6', '2'))}")
    if str(r6.get("Value", "")).strip() in ("0", "0R", "0 R", "0 ohm"):
        bad.append("R6 is 0 ohm -- a clock on TP3 would be shorted to GND")
    jp = BOM.get("JP1") or {}
    if "Open" not in str(jp.get("Footprint")):
        bad.append(f"JP1 is not an OPEN jumper: {jp.get('Footprint')}")
    if jp.get("DNP") == "yes":
        bad.append("JP1 is marked DNP -- a solder bridge is not a part to omit")
    if (pinnet.get(("JP1", "1")), pinnet.get(("JP1", "2"))) != ("VCC", "MODE"):
        bad.append(f"JP1 is not VCC-to-MODE: {pinnet.get(('JP1', '1'))} / "
                   f"{pinnet.get(('JP1', '2'))}")
    if bad:
        raise AssertionError("MODE could float or be mis-strapped:\n  " + "\n  ".join(bad))
    return r6["Value"]


# =============================================================================== emit
def emit():
    L = []
    A = L.append
    A('(kicad_sch')
    A('\t(version 20250114)')
    A('\t(generator "gen_sch.py")')
    A('\t(generator_version "9.0")')
    A(f'\t(uuid "{uid("sheet", "root")}")')
    A(f'\t(paper "{PAPER}")')
    A('\t(title_block')
    A(f'\t\t(title "TPSM33610S3Q breakout -- {V["descr"]}")')
    A('\t\t(company "")')
    A(f'\t\t(comment 1 "GENERATED by gen_sch.py --variant {VKEY} -- do not edit in Eeschema")')
    A('\t\t(comment 2 "TI SNVSCS7E rev E, Apr 2025 rev Sep 2026; Table 8-3 fixed-output application")')
    A('\t\t(comment 3 "MODE/SYNC abs max 5.5 V and PGOOD 20 V -- neither may be tied to VIN")')
    A('\t\t(comment 4 "NO input protection: VIN abs max 40 V, EN tied to VIN. Stiff bench supply only")')
    A('\t)')

    A('\t(lib_symbols')
    for lib_id in sorted(LIBS):
        for line in LIBS[lib_id].splitlines():
            A('\t\t' + (line if line.startswith('\t') else line.strip()))
    A('\t)')

    for (x1, y1, x2, y2) in _SEGS:
        A('\t(wire')
        A(f'\t\t(pts (xy {x1} {y1}) (xy {x2} {y2}))')
        A('\t\t(stroke (width 0) (type default))')
        A(f'\t\t(uuid "{uid("wire", x1, y1, x2, y2)}")')
        A('\t)')

    for (x, y) in junctions():
        A(f'\t(junction (at {x} {y}) (diameter 0) (color 0 0 0 0) '
          f'(uuid "{uid("junction", x, y)}"))')

    for (x, y) in _NOCONN:
        A(f'\t(no_connect (at {x} {y}) (uuid "{uid("nc", x, y)}"))')

    for (text, x, y, ang) in _LABELS:
        A(f'\t(label "{text}"')
        A(f'\t\t(at {x} {y} {ang})')
        just = "right" if ang == 180 else "left"
        A(f'\t\t(effects (font (size 1.27 1.27)) (justify {just} bottom))')
        A(f'\t\t(uuid "{uid("label", text, x, y)}")')
        A('\t)')

    for ref in sorted(INST):
        lib_id, X, Y, ang, mir = INST[ref]
        props = BOM[ref]
        A('\t(symbol')
        A(f'\t\t(lib_id "{lib_id}")')
        A(f'\t\t(at {X} {Y} {ang})')
        if mir:
            A(f'\t\t(mirror {mir})')
        A('\t\t(unit 1)')
        A('\t\t(exclude_from_sim no)')
        A(f'\t\t(in_bom {"no" if props.get("InBOM") == "no" else "yes"})')
        A('\t\t(on_board yes)')
        A(f'\t\t(dnp {"yes" if props.get("DNP") == "yes" else "no"})')
        A(f'\t\t(uuid "{uid("sym", ref)}")')
        pang = 90 if ang in (90, 270) else 0
        hide_ref = ref.startswith("#")
        # Reference above, value below, both clear of the +/-3.81 mm stubs that
        # carry this sheet's net labels. The default KiCad offset (+2.54, -2.54)
        # puts both on top of those labels on every vertically-placed 2-pin part,
        # which the first render of this sheet showed on six of them.
        dx, dref, dval = PROP_OFFSET.get(ref, (1.905, -1.27, 1.27))
        A(f'\t\t(property "Reference" "{ref}"')
        A(f'\t\t\t(at {round(X + dx, 4)} {round(Y + dref, 4)} {pang})')
        A(f'\t\t\t(effects (font (size 1.27 1.27)) (justify left){" hide" if hide_ref else ""})')
        A('\t\t)')
        val = props.get("Value", lib_id.split(":", 1)[1])
        A(f'\t\t(property "Value" "{val}"')
        A(f'\t\t\t(at {round(X + dx, 4)} {round(Y + dval, 4)} {pang})')
        A(f'\t\t\t(effects (font (size 1.27 1.27)) (justify left){" hide" if hide_ref else ""})')
        A('\t\t)')
        for key in ("Footprint", "MPN", "Manufacturer", "Spec", "NoMPN", "DNP"):
            if key in props:
                v = props[key].replace('"', r'\"').replace("\n", " ")
                A(f'\t\t(property "{key}" "{v}"')
                A(f'\t\t\t(at {X} {Y} 0)')
                A('\t\t\t(effects (font (size 1.27 1.27)) hide)')
                A('\t\t)')
        for num, _, _ in LIBPINS[lib_id]:
            A(f'\t\t(pin "{num}" (uuid "{uid("pin", ref, num)}"))')
        A('\t\t(instances')
        A(f'\t\t\t(project "{NAME}"')
        A(f'\t\t\t\t(path "/{uid("sheet", "root")}" (reference "{ref}") (unit 1))')
        A('\t\t\t)')
        A('\t\t)')
        A('\t)')

    A('\t(sheet_instances')
    A('\t\t(path "/" (page "1"))')
    A('\t)')
    A('\t(embedded_fonts no)')
    A(')')
    return "\n".join(L) + "\n"


def main():
    n_rails = check_rail_orientation()
    n_labels = check_labels_on_wires()
    n_syms = check_no_symbol_overlap()
    n_bom = check_bom_complete()
    n_abs = check_abs_max()
    n_pins = check_pin_coverage()
    n_fit = check_dnp_exclusivity()
    r6_val = check_mode_never_floats()
    n_lines, shared = check_bom_lines()
    js = junctions()
    text = emit()
    assert text.count("(") == text.count(")"), "unbalanced parentheses in the schematic"
    OUT.write_text(text)
    print(f"variant                 {VKEY} -- {V['descr']}")
    print(f"symbols placed          {n_syms} ({n_bom} on the BOM, {n_fit} fitted)")
    print(f"pins netted             {n_pins} + {len(_NOCONN)} no-connect")
    print(f"U1 pins abs-max checked {n_abs} of 11 ({len(ABS_MAX_EXEMPT)} exempt, declared)")
    print(f"purchased BOM lines     {n_lines} distinct"
          f"  (shared: {', '.join('+'.join(v) for v in shared.values())})")
    print(f"MODE strap              JP1 open -> auto via R6 {r6_val} to GND; "
          f"bridged -> VCC (FPWM)")
    print(f"power symbols checked   {n_rails}")
    print(f"labels checked          {n_labels}")
    print(f"wires / junctions       {len(_SEGS)} / {len(js)}")
    print(f"wrote {OUT.relative_to(HERE)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
