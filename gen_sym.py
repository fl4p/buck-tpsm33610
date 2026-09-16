#!/usr/bin/env python3
"""Generate lib/buck-tpsm33610.kicad_sym.

GENERATED ARTEFACT -- this script is the source of truth.

The symbol is generated rather than drawn because the pin table is not just
graphics on this part: three pins have absolute-maximum ratings well below VIN,
and one of them (MODE/SYNC, 5.5 V) sits next to a 40 V pin in the pinout. Having
the table in code lets gen_sch.py assert, at generation time, that no pin is
wired to a net that can exceed its rating -- see ABS_MAX below and the
check_abs_max() audit in gen_sch.py.

Source for every number here: TI SNVSCS7E rev E,
  * page 5   Figure 5-1 (TOP VIEW) and the Pin Functions table -- names, numbers
  * page 6   Absolute Maximum Ratings -- ABS_MAX
  * page 5   the three "do not" rules that the Description carries verbatim
"""

import hashlib
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
OUT = HERE / "lib" / "buck-tpsm33610.kicad_sym"

PART = "TPSM33610S3Q"
DATASHEET = "https://www.ti.com/lit/ds/symlink/tpsm33610-q1.pdf"

# ---- SNVSCS7E p.6, Absolute Maximum Ratings, volts to GND.
#      Consumed by gen_sch.py. GND is the reference and is not a limit.
ABS_MAX = {
    "1": 20.0,    # PG to GND
    "2": 40.0,    # EN to GND
    "3": 40.0,    # VIN to GND
    "4": 16.0,    # VOUT to GND
    "5": 40.0,    # SW to GND
    "6": 40.0,    # SW to GND
    "7": 5.5,     # BOOT to SW  (NOT to GND -- see the note in gen_sch.py)
    "8": 5.5,     # VCC to GND
    "9": 16.0,    # FB to GND
    "11": 5.5,    # MODE/SYNC to GND
}

# ---- SNVSCS7E p.5, Figure 5-1 and Pin Functions.
#      (number, name, side, position, electrical type)
#      "side" is where the pin sits on the drawn body; "position" is the slot
#      along that side in 2.54 mm units, measured from the body centre.
W, H = 12.7, 15.24          # body half-width, half-height
PLEN = 5.08                 # pin length

PINS = [
    ("3",  "VIN",       "L",  5, "power_in"),
    ("2",  "EN",        "L",  2, "input"),
    ("11", "MODE/SYNC", "L", -3, "input"),
    ("4",  "VOUT",      "R",  5, "power_out"),
    ("9",  "FB",        "R",  2, "input"),
    ("1",  "PGOOD",     "R", -2, "open_collector"),
    ("8",  "VCC",       "R", -5, "power_out"),
    ("5",  "SW",        "B", -4, "passive"),
    ("6",  "SW",        "B", -2, "passive"),
    ("7",  "BOOT",      "B",  0, "passive"),
    ("10", "GND",       "B",  2, "power_in"),
]

DESCR = (
    "Automotive 3-36 V input, 3.3 V fixed / 1-7 V adjustable, 1 A synchronous "
    "buck power module with integrated inductor and bootstrap capacitor, "
    "2.2 MHz, dual random spread spectrum, QFN-FCMOD-11 (RDN). "
    "SW (5,6): no external component, no signal, minimum copper. "
    "BOOT (7): capacitor is INTERNAL, leave unconnected. "
    "VCC (8): 1 uF to GND, no external load. "
    "MODE/SYNC (11) abs max 5.5 V -- never tie to VIN. "
    "EN (2) and MODE/SYNC (11) must not float. "
    "FB (9) for fixed output connects directly to VOUT (4)."
)


def uid(*parts):
    h = hashlib.sha1(("buck-tpsm33610/sym/" + "/".join(map(str, parts))).encode()).hexdigest()
    return f"{h[0:8]}-{h[8:12]}-5{h[13:16]}-a{h[17:20]}-{h[20:32]}"


def pin_geom(side, slot):
    """(x, y, rotation) of the pin's CONNECTION end. KiCad: rotation 0 means the
    pin extends to the right of its connection point, i.e. body is to the right."""
    if side == "L":
        return (-(W + PLEN), slot * 2.54, 0)
    if side == "R":
        return (W + PLEN, slot * 2.54, 180)
    if side == "B":
        return (slot * 2.54, -(H + PLEN), 90)
    raise ValueError(side)


def emit():
    L = []
    A = L.append
    A('(kicad_symbol_lib')
    A('\t(version 20241209)')
    A('\t(generator "gen_sym.py")')
    A('\t(generator_version "9.0")')
    A(f'\t(symbol "{PART}"')
    A('\t\t(pin_names (offset 0.508))')
    A('\t\t(exclude_from_sim no)')
    A('\t\t(in_bom yes)')
    A('\t\t(on_board yes)')
    A(f'\t\t(property "Reference" "U" (at {-W} {H + 2.54} 0)')
    A('\t\t\t(effects (font (size 1.27 1.27)) (justify left bottom)))')
    A(f'\t\t(property "Value" "{PART}" (at {-W} {H + 5.08} 0)')
    A('\t\t\t(effects (font (size 1.27 1.27)) (justify left bottom)))')
    A('\t\t(property "Footprint" "" (at 0 0 0)')
    A('\t\t\t(effects (font (size 1.27 1.27)) hide))')
    A(f'\t\t(property "Datasheet" "{DATASHEET}" (at 0 0 0)')
    A('\t\t\t(effects (font (size 1.27 1.27)) hide))')
    A(f'\t\t(property "Description" "{DESCR}" (at 0 0 0)')
    A('\t\t\t(effects (font (size 1.27 1.27)) hide))')
    A('\t\t(property "ki_keywords" "buck module regulator DCDC power module '
      'TPSM33610 TPSM336xx synchronous step-down automotive" (at 0 0 0)')
    A('\t\t\t(effects (font (size 1.27 1.27)) hide))')
    A('\t\t(property "ki_fp_filters" "TPSM*RDN0011B*" (at 0 0 0)')
    A('\t\t\t(effects (font (size 1.27 1.27)) hide))')

    A(f'\t\t(symbol "{PART}_0_1"')
    A(f'\t\t\t(rectangle (start {-W} {-H}) (end {W} {H})')
    A('\t\t\t\t(stroke (width 0.254) (type default))')
    A('\t\t\t\t(fill (type background)))')
    A('\t\t)')

    A(f'\t\t(symbol "{PART}_1_1"')
    for num, name, side, slot, etype in PINS:
        x, y, rot = pin_geom(side, slot)
        A(f'\t\t\t(pin {etype} line (at {x} {y} {rot}) (length {PLEN})')
        A(f'\t\t\t\t(name "{name}" (effects (font (size 1.27 1.27))))')
        A(f'\t\t\t\t(number "{num}" (effects (font (size 1.27 1.27))))')
        A('\t\t\t)')
    A('\t\t)')
    A('\t\t(embedded_fonts no)')
    A('\t)')
    A(')')
    return "\n".join(L) + "\n"


def main():
    def need(cond, msg):
        if not cond:
            raise SystemExit(f"gen_sym: {msg}")

    nums = [p[0] for p in PINS]
    need(len(PINS) == 11, f"{len(PINS)} pins, expected 11")
    need(sorted(nums, key=int) == [str(i) for i in range(1, 12)],
         f"pin numbers are not 1..11: {sorted(nums, key=int)}")
    need(len(set(nums)) == 11, "duplicate pin number")
    # No two pins may land on the same point -- KiCad would silently merge them.
    pts = [pin_geom(s, sl) for _, _, s, sl, _ in PINS]
    need(len(set((x, y) for x, y, _ in pts)) == 11, "two pins share a location")
    # Every pin with an abs-max rating must exist, and every pin except GND and
    # the BOOT special case must HAVE one, so gen_sch.py cannot silently skip a
    # pin it has no limit for.
    need(set(ABS_MAX) <= set(nums), f"ABS_MAX names a pin that does not exist")
    unrated = set(nums) - set(ABS_MAX)
    need(unrated == {"10"}, f"pins with no abs-max entry: {sorted(unrated)} (expected only GND)")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    text = emit()
    OUT.write_text(text)
    need(text.count("(") == text.count(")"), "unbalanced parentheses")
    need(text.count("(pin ") == 11, "emitted pin count is not 11")
    print(f"symbol      {PART}, 11 pins")
    print(f"abs-max     {len(ABS_MAX)} pins rated, GND is the reference")
    print(f"wrote {OUT.relative_to(HERE)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
