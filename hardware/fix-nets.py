#!/usr/bin/env python3
r"""
Repair the net table in ir-remote.kicad_pcb.

WHY THIS EXISTS
---------------
The kicad-mcp board writer (kicad-mixelpixx, swig backend) serialises pad nets
as:

    (net "GND")

but the KiCad .kicad_pcb format requires an index *and* a name:

    (net 2 "GND")

...plus a top-level net declaration table listing every net before the first
footprint. The MCP emits neither. The result loads in KiCad but with no
connectivity: every pad is netless, so DRC cannot check shorts or clearance and
routing is impossible.

This is re-broken by EVERY MCP save (save_project / any mutating tool that
autosaves). So: run this script as the LAST step after any MCP board write, and
re-run it before DRC / gerber export.

Verify with:
    grep -cE '^\t\(net [0-9]+ ' ir-remote.kicad_pcb   # should equal net count
    grep -cE '^\t\t\t\(net "'   ir-remote.kicad_pcb   # should be 0

Idempotent: safe to run repeatedly. Exits non-zero if nothing needed fixing.
"""
import re
import sys
import pathlib

BOARD = pathlib.Path(__file__).with_name("ir-remote.kicad_pcb")

# Pad-level net refs, indented 3 tabs, missing the numeric index.
PAD_NET = re.compile(r'(\n\t\t\t\(net )"([^"]+)"(\))')
# An existing top-level net table, if a previous run already inserted one.
TOP_NET = re.compile(r'^\t\(net \d+ "[^"]*"\)\n', re.M)


def main() -> int:
    text = BOARD.read_text()

    broken = PAD_NET.findall(text)
    if not broken:
        print("net table already valid - nothing to do")
        return 1

    # Stable ordering: first appearance on a pad wins index 1, 2, 3...
    names: list[str] = []
    for _, name, _ in broken:
        if name not in names:
            names.append(name)
    index = {name: i + 1 for i, name in enumerate(names)}

    # Drop any stale table from a previous run before inserting a fresh one.
    text = TOP_NET.sub("", text)

    # 1. Give every pad reference its index.
    text = PAD_NET.sub(
        lambda m: f'{m.group(1)}{index[m.group(2)]} "{m.group(2)}"{m.group(3)}',
        text,
    )

    # 2. Insert the declaration table just before the first footprint.
    #    Net 0 is the unassigned net and must exist.
    table = '\t(net 0 "")\n' + "".join(
        f'\t(net {i} "{n}")\n' for n, i in sorted(index.items(), key=lambda kv: kv[1])
    )
    cut = text.index("\n\t(footprint ")
    text = text[: cut + 1] + table + text[cut + 1 :]

    BOARD.write_text(text)
    print(f"repaired {len(broken)} pad net refs across {len(index)} nets")
    print("  " + ", ".join(names))
    return 0


if __name__ == "__main__":
    sys.exit(main())
