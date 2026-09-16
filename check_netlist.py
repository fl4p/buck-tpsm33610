#!/usr/bin/env python3
"""The capture-completion gate: does the EXPORTED netlist match declared intent?

  python3 check_netlist.py [--variant base]

gen_sch.py declares, per pin, which net it belongs to (the `net()` calls). That
declaration is written by hand next to the wiring, so it is INTENT. This script
re-parses the netlist KiCad actually exported and compares the two, in both
directions. A net that exists only in the export is a wiring accident; a net that
exists only in the declaration is a wire that was never drawn.

Deliberately not shared with gen_sch's geometry: if this derived connectivity
from _SEGS it would agree with the drawing by construction and check nothing.
"""

import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))


def sexp(text):
    """Minimal s-expression reader -> nested lists of str."""
    tok, i, n = [], 0, len(text)
    while i < n:
        c = text[i]
        if c in "()":
            tok.append(c); i += 1
        elif c == '"':
            j = i + 1
            buf = []
            while text[j] != '"':
                if text[j] == "\\":
                    buf.append(text[j + 1]); j += 2
                else:
                    buf.append(text[j]); j += 1
            tok.append('"' + "".join(buf)); i = j + 1
        elif c.isspace():
            i += 1
        else:
            j = i
            while j < n and not text[j].isspace() and text[j] not in '()"':
                j += 1
            tok.append(text[i:j]); i = j
    pos = 0

    def rd():
        nonlocal pos
        t = tok[pos]; pos += 1
        if t == "(":
            out = []
            while tok[pos] != ")":
                out.append(rd())
            pos += 1
            return out
        return t
    return rd()


def find(node, key):
    return [c for c in node if isinstance(c, list) and c and c[0] == key]


def unq(s):
    return s[1:] if isinstance(s, str) and s.startswith('"') else s


def exported(path):
    root = sexp(path.read_text())
    nets = {}
    for nb in find(find(root, "nets")[0], "net"):
        name = unq(find(nb, "name")[0][1]).lstrip("/")
        nodes = set()
        for nd in find(nb, "node"):
            nodes.add((unq(find(nd, "ref")[0][1]), unq(find(nd, "pin")[0][1])))
        nets[name] = nodes
    comps = {}
    for cb in find(find(root, "components")[0], "comp"):
        ref = unq(find(cb, "ref")[0][1])
        props = {}
        for pb in find(cb, "property"):
            props[unq(find(pb, "name")[0][1])] = unq(find(pb, "value")[0][1]) \
                if find(pb, "value") else ""
        fp = find(cb, "footprint")
        props["_footprint"] = unq(fp[0][1]) if fp else ""
        comps[ref] = props
    return nets, comps


def main():
    import gen_sch
    net_path = HERE / f"{gen_sch.NAME}.net"
    if not net_path.exists():
        raise SystemExit(f"check_netlist: {net_path.name} not found -- export it first")

    got, comps = exported(net_path)
    want = {}
    for ref, pin, name in gen_sch._PINNET:
        want.setdefault(name, set()).add((ref, pin))

    nc = set(gen_sch._NC_PINS)

    problems = []
    for name in sorted(set(got)):
        if not name.startswith("unconnected-"):
            continue
        nodes = got.pop(name)
        # KiCad invents one of these per no-connect flag. Confirm it belongs to
        # a pin we DECLARED as a no-connect, so a pin that was simply forgotten
        # cannot hide behind the same naming convention.
        if nodes - nc:
            problems.append(f"{name!r} covers {sorted(nodes - nc)}, which were never "
                            f"declared as no-connects")
    for name in sorted(set(want) | set(got)):
        w, g = want.get(name, set()), got.get(name, set())
        if w == g:
            continue
        if not w:
            problems.append(f"net {name!r} exists in the export but was never declared: "
                            f"{sorted(g)}")
        elif not g:
            problems.append(f"net {name!r} was declared but never exported: {sorted(w)}")
        else:
            extra, miss = sorted(g - w), sorted(w - g)
            problems.append(f"net {name!r} differs -- exported-only {extra}, "
                            f"declared-only {miss}")

    # A single-node net is a wire that did not land. KiCad exports it happily.
    for name, nodes in sorted(got.items()):
        if name.startswith("unconnected-"):
            # KiCad's own name for a no-connect flag. One node is what it means.
            continue
        if len(nodes) == 1:
            problems.append(f"net {name!r} has ONE node {sorted(nodes)} -- "
                            f"a stub that connects to nothing")

    # Every component must carry a footprint; an empty one fails far downstream.
    for ref, props in sorted(comps.items()):
        if not props.get("_footprint"):
            problems.append(f"{ref} exported with no footprint")

    if problems:
        print("NETLIST DOES NOT MATCH DECLARED INTENT:")
        for p in problems:
            print("  " + p)
        return 1

    print(f"netlist matches intent   {len(got)} nets, "
          f"{sum(len(v) for v in got.values())} nodes, {len(comps)} components")
    for name in sorted(got, key=lambda n: (-len(got[n]), n)):
        print(f"  {name:<7} {len(got[name]):>2}  " +
              " ".join(f"{r}.{p}" for r, p in sorted(got[name])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
