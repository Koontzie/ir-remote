# hardware/ — BLE IR remote PCB

KiCad 10 project for the custom board. Design decisions and rationale live in
[DESIGN-pcb.md](DESIGN-pcb.md); this file is the how-to-work-on-it notes.

**Nothing here has been fabricated. Nothing is proven.**

| File | What it is |
|---|---|
| `ir-remote.kicad_sch` | Schematic — flat sheet, zoned power / MCU / USB / IR / inputs |
| `ir-remote.kicad_pcb` | Board — 2-layer, 30 × 58mm |
| `ir-remote.kicad_pro` | Project + net classes (POWER_IR, POWER_3V3, USB_DIFF) |
| `fix-nets.py` | **Required repair script — read the warning below** |
| `DESIGN-pcb.md` | Pin map, power tree, BOM, sleep budget, decisions |

---

## ⛔ Tooling gotcha: every MCP save silently destroys connectivity

**If you edit this board through the kicad-mcp server, you MUST run
`fix-nets.py` afterwards or the board has no nets at all.**

The kicad-mcp board writer (`kicad-mixelpixx`, swig backend) serialises pad nets
as:

```
(net "GND")          <- what the MCP writes
(net 2 "GND")        <- what KiCad requires
```

It writes no net *index*, and omits the top-level net declaration table
entirely. KiCad still **opens the file without complaint** — that is what makes
this dangerous. But every pad is netless, so:

- DRC cannot detect shorts or clearance violations (it reports a suspiciously
  clean board),
- the ratsnest is empty,
- routing and gerber export are meaningless.

`kicad-cli sch upgrade` does **not** fix it.

### The rule

```
  <any kicad-mcp edit>  →  save_project  →  python3 fix-nets.py  →  kicad-cli pcb drc
```

`fix-nets.py` is idempotent — running it twice is harmless, and it prints
`net table already valid` when there is nothing to do.

Verify by hand any time you are unsure:

```sh
grep -cE '^\t\(net [0-9]+ ' ir-remote.kicad_pcb   # net table entries — must be > 0
grep -cE '^\t\t\t\(net "'   ir-remote.kicad_pcb   # unindexed pad refs — must be 0
```

### Second-order trap

Because `fix-nets.py` edits the file on disk, the MCP's next auto-save is
**refused** (it guards on mtime and warns `diskChangedExternally`). Your edits
then live only in the server's memory and are lost on reload. After running the
script, call `open_project` before making further MCP edits.

---

## Verification commands

```sh
# ERC (readable output — the MCP reports violation coordinates in unusable units)
kicad-cli sch erc --output erc.rpt --severity-all ir-remote.kicad_sch

# DRC — always run fix-nets.py first, or this lies to you
python3 fix-nets.py && kicad-cli pcb drc --output drc.rpt --severity-error ir-remote.kicad_pcb

# 3D renders
kicad-cli pcb render --output layout-top.png    --side top    ir-remote.kicad_pcb
kicad-cli pcb render --output layout-bottom.png --side bottom ir-remote.kicad_pcb
```

## Autorouting

Freerouting, not the MCP's `autoroute` (it probes `/usr/bin/java`, the macOS
stub, and will not find a Homebrew JDK).

- **Freerouting 2.2.x needs Java 25** (class file v69). **Use 2.1.0** — class
  file v65, runs on Java 21.
- Java: `/opt/homebrew/opt/openjdk@21/bin/java` (keg-only, not on PATH).

```sh
java -Djava.awt.headless=true -jar ~/.kicad-mcp/freerouting.jar \
     -de ir-remote.dsn -do ir-remote.ses -mp 50 -dct 0
```

**The MCP's DSN export drops net classes** — everything comes out at 0.2mm,
including the 220mA IR paths. The DSN must be patched to add `POWER_IR` (600µm),
`POWER_3V3` (500µm) and `USB_DIFF` (250µm) classes before routing.

## Fab notes (JLCPCB, 2-layer)

| Parameter | Value |
|---|---|
| Size | 30 × 58mm, 2mm corner radius |
| Layers / thickness | 2 / 1.6mm |
| Surface finish | HASL (lead-free fine) |
| Min track / clearance | 0.127mm / 0.2mm |
| Min drill | 0.3mm |
| Copper | 1oz |

**Watch item:** the stock KiCad `ESP32-S3-WROOM-1` footprint ships 12 thermal
vias at **0.2mm drill**, under JLCPCB's 0.3mm minimum. They are enlarged to
0.3mm in this board. If the footprint is ever re-imported from the library,
that fix is lost — re-check before ordering.

## Antenna keepout — do not "optimise" this away

The ESP32-S3-WROOM-1 footprint declares a large antenna clearance area
(x < 7.75mm for the full board height in the current orientation). No copper,
no pour, no components, no stitching vias in it. The ground pours are cut back
to respect it, which is why the left strip of the board looks empty.

The MCP's `add_gnd_stitching_vias` works off the **board outline, not the pour
outline**, and will happily place vias straight through the keepout. Use the
`in_zones` strategy or place them by hand.
