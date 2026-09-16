#!/usr/bin/env python3
"""Own the design settings in <variant>.kicad_pro.

WHY THIS FILE EXISTS. `pcbnew.LoadBoard()` / `BOARD.Save()` rewrite the adjacent
.kicad_pro wholesale from KiCad's in-memory defaults. Every value below gets
silently replaced -- clearances to 0.0, net classes deleted, and a fistful of DRC
rules flipped to "ignore". A DRC run after that reports "0 violations" while
being unable to see any of them, and checking the file BEFORE the board is built
does not catch it, because the clobber happens after.

So: KiCad's own writer produces the schema-correct file, this module patches our
values back on top of it, idempotently, AFTER every pcbnew save, and verify()
re-reads FROM DISK and fails the build if anything did not stick. Never assert on
the copy you wrote from memory.

The ignore-sweep at the bottom of apply() is the fail-closed half: any rule this
file does not name explicitly, but which KiCad left at "ignore", is promoted to
"warning". A green DRC/ERC has to be a statement about the board, not about how
much of the rule set was switched off.
"""

import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import variants   # noqa: E402


def prj_path(variant_key="base"):
    return HERE / f"{variants.VARIANTS[variant_key]['name']}.kicad_pro"


P = variants.PROCESS

# --------------------------------------------------------------------------- our values
# Aisler 2-layer, 35 um copper, ENIG. Their published minimums for that stack are
# 125 um track and space, 0.3 mm via drill with 200 um annular, 0.5 mm PTH drill
# with 300 um annular, 300 um copper-to-edge. The numbers below are the DESIGN
# minimums and sit ABOVE the process ones on purpose, so a marginal feature shows
# up as a DRC violation here rather than as a yield problem there.
#
# The one exception is the module land itself, which is 0.100 mm and cannot be
# widened -- see buck-tpsm33610.kicad_dru, where that exception is scoped to U1
# by name rather than by relaxing the global rule.
RULES = {
    # The board-wide FLOOR, not the working clearance. KiCad treats
    # min_clearance as an absolute limit that no custom rule may go below, so
    # leaving it at 0.15 silently defeated buck-tpsm33610.kicad_dru's 0.09 mm
    # exception for U1's own land gaps. The working number is unchanged: every
    # net sits in a class whose clearance is P["clearance_mm"], and the .dru
    # exception is scoped to two U1 pads.
    "min_clearance": 0.09,
    "min_track_width": P["track_mm"],
    "min_copper_edge_clearance": P["edge_clearance_mm"],
    "min_silk_clearance": P["silk_to_pad_mm"],
    "min_hole_clearance": 0.25,
    "min_hole_to_hole": 0.25,
    "min_through_hole_diameter": P["via_drill_mm"],
    "min_via_diameter": P["via_pad_mm"],
    # 0.125, not Aisler's published 0.20: the via itself is already a declared
    # rule break (0.25 drill / 0.50 pad, because a 0.70 mm via pad does not fit
    # beside a 0.35 mm land at 0.5 mm pitch -- see variants.PROCESS). Leaving
    # the ring rule at 0.20 would have failed every via on the board while the
    # via SIZE decision sat unchallenged, which is a rule reporting the wrong
    # thing rather than a board being wrong.
    "min_via_annular_width": 0.125,
    "min_text_height": P["silk_height_mm"],
    "min_text_thickness": P["silk_thickness_mm"],
    "min_resolved_spokes": 2,
}

DRC_SEVERITY = {
    "clearance": "error",
    "copper_edge_clearance": "error",
    "track_width": "error",
    "annular_width": "error",
    "hole_clearance": "error",
    "hole_to_hole": "error",
    "shorting_items": "error",
    "unconnected_items": "error",
    "items_not_allowed": "error",
    "invalid_outline": "error",
    "malformed_courtyard": "error",
    "missing_courtyard": "error",
    "npth_inside_courtyard": "error",
    "pth_inside_courtyard": "error",
    "footprint_filters_mismatch": "error",
    "footprint_type_mismatch": "error",
    "footprint_symbol_mismatch": "error",
    "lib_footprint_mismatch": "error",
    "solder_mask_bridge": "error",
    "silk_over_copper": "error",
    "text_height": "error",
    "text_thickness": "error",
    "starved_thermal": "error",
    "isolated_copper": "error",
    "copper_sliver": "warning",
    # A two-layer board with a solid bottom pour and a top pour will legitimately
    # put the two pours' courtyards over each other; courtyard overlap is
    # dispositioned per pair in DESIGN.md, not switched off here.
    "courtyards_overlap": "warning",
    "footprint_symbol_field_mismatch": "warning",
}

ERC_SEVERITY = {
    "power_pin_not_driven": "error",
    "pin_not_driven": "error",
    "pin_not_connected": "error",
    "label_dangling": "error",
    "no_connect_dangling": "error",
    "no_connect_connected": "error",
    "endpoint_off_grid": "error",
    "duplicate_reference": "error",
    "lib_symbol_mismatch": "error",
    "lib_symbol_issues": "error",
    # This board has four legitimate four-way junctions (the EN, MODE, FB and
    # PGOOD nodes, each of which really does join a pin, two straps and a test
    # pad). KiCad defaults the check to "ignore"; it is a style check, not a
    # defect check, so it is a warning here -- visible, not disabled.
    "four_way_junction": "warning",
    # Enabled, not ignored: U1's symbol carries ki_fp_filters "TPSM*RDN0011B*",
    # which is the only thing standing between the schematic and a footprint for
    # a different package.
    "footprint_filter": "error",
    "simulation_model_issue": "warning",
    # KiCad does not write this key at all until it is changed, so the
    # ignore-sweep below cannot reach it: it has to be named. This board uses no
    # global labels, so the check cannot fire -- but "cannot fire" and
    # "switched off" have to be different states.
    "single_global_label": "warning",
}

DEFAULT_CLASS = {
    "clearance": P["clearance_mm"],
    "track_width": P["track_mm"],
    "via_diameter": P["via_pad_mm"],
    "via_drill": P["via_drill_mm"],
}

# VIN, VOUT and GND are carried by pours, but every stub and neck between a pour
# and a pad is a track, and a 0.2 mm neck on the 1 A output is exactly the defect
# the copper-capacity backstop exists to catch. Give them their own floor.
PWR_CLASS = dict(DEFAULT_CLASS, name="PWR", track_width=0.50, priority=1,
                 bus_width=12.0, diff_pair_gap=0.25, diff_pair_via_gap=0.25,
                 diff_pair_width=0.2, line_style=0, microvia_diameter=0.3,
                 microvia_drill=0.1, pcb_color="rgba(0, 0, 0, 0.000)",
                 schematic_color="rgba(0, 0, 0, 0.000)", wire_width=6.0)

NETCLASS_PATTERNS = [
    {"netclass": "PWR", "pattern": "VIN"},
    {"netclass": "PWR", "pattern": "VOUT"},
    {"netclass": "PWR", "pattern": "GND"},
]

TRACK_WIDTHS = [0.0, P["track_mm"], 0.5, 0.8]
VIA_DIMENSIONS = [{"diameter": 0.0, "drill": 0.0},
                  {"diameter": P["via_pad_mm"], "drill": P["via_drill_mm"]}]


def apply(prj):
    prj = pathlib.Path(prj)
    d = json.loads(prj.read_text())

    ds = d.setdefault("board", {}).setdefault("design_settings", {})
    ds.setdefault("rules", {}).update(RULES)
    sev = ds.setdefault("rule_severities", {})
    sev.update(DRC_SEVERITY)
    ds["track_widths"] = list(TRACK_WIDTHS)
    ds["via_dimensions"] = [dict(v) for v in VIA_DIMENSIONS]

    esev = d.setdefault("erc", {}).setdefault("rule_severities", {})
    esev.update(ERC_SEVERITY)

    # Fail closed: anything still at "ignore" that we did not name is promoted.
    for m, explicit in ((sev, DRC_SEVERITY), (esev, ERC_SEVERITY)):
        for k, v in list(m.items()):
            if v == "ignore" and k not in explicit:
                m[k] = "warning"

    ns = d.setdefault("net_settings", {})
    classes = ns.setdefault("classes", [])
    by_name = {c.get("name"): c for c in classes}
    if "Default" in by_name:
        by_name["Default"].update(DEFAULT_CLASS)
    else:
        # KiCad materialises "Default" on first load, but a file that has never
        # been opened has none -- and then every net silently inherits KiCad's
        # built-in defaults instead of the process minimums above.
        classes.insert(0, dict(PWR_CLASS, name="Default", priority=0,
                               track_width=DEFAULT_CLASS["track_width"]))
        by_name["Default"] = classes[0]
    if "PWR" in by_name:
        by_name["PWR"].update(PWR_CLASS)
    else:
        classes.append(dict(PWR_CLASS))
    ns["netclass_patterns"] = [dict(p) for p in NETCLASS_PATTERNS]

    prj.write_text(json.dumps(d, indent=2, sort_keys=True) + "\n")


def verify(prj):
    """Re-read from DISK and check every value stuck. Returns a summary line."""
    prj = pathlib.Path(prj)
    d = json.loads(prj.read_text())
    ds = d["board"]["design_settings"]
    bad = []
    for k, v in RULES.items():
        if ds["rules"].get(k) != v:
            bad.append(f"rules.{k} = {ds['rules'].get(k)!r}, want {v!r}")
    sev = ds["rule_severities"]
    for k, v in DRC_SEVERITY.items():
        if sev.get(k) != v:
            bad.append(f"drc severity.{k} = {sev.get(k)!r}, want {v!r}")
    esev = d.get("erc", {}).get("rule_severities", {})
    for k, v in ERC_SEVERITY.items():
        if esev.get(k) != v:
            bad.append(f"erc severity.{k} = {esev.get(k)!r}, want {v!r}")
    for what, m in (("DRC", sev), ("ERC", esev)):
        ig = sorted(k for k, val in m.items() if val == "ignore")
        if ig:
            bad.append(f"{what} rules at 'ignore', invisible to the check: {ig}")
    names = [c.get("name") for c in d["net_settings"]["classes"]]
    if "Default" not in names:
        bad.append(f"Default net class missing (classes: {names})")
    else:
        df = next(c for c in d["net_settings"]["classes"] if c["name"] == "Default")
        for k, v in DEFAULT_CLASS.items():
            if df.get(k) != v:
                bad.append(f"Default.{k} = {df.get(k)!r}, want {v!r}")
    if "PWR" not in names:
        bad.append(f"PWR net class missing (classes: {names})")
    else:
        pw = next(c for c in d["net_settings"]["classes"] if c["name"] == "PWR")
        if pw.get("track_width") != PWR_CLASS["track_width"]:
            bad.append(f"PWR track_width = {pw.get('track_width')!r}")
    if d["net_settings"].get("netclass_patterns") != NETCLASS_PATTERNS:
        bad.append("PWR netclass patterns missing -- the class would apply to nothing")
    if bad:
        raise SystemExit(f"{prj.name} settings did not stick:\n  " + "\n  ".join(bad))
    return (f"{len(RULES)} rules, DRC {len(sev)} severities, ERC {len(esev)} "
            f"severities, 0 ignored; net classes {names}")


if __name__ == "__main__":
    key, _ = variants.select()
    apply(prj_path(key))
    print(verify(prj_path(key)))
    sys.exit(0)
