# hardware/ — BLE IR remote PCB

KiCad 10 project for the custom board. Design decisions and rationale live in
[DESIGN-pcb.md](DESIGN-pcb.md); this file is the how-to-work-on-it notes.

**Nothing here has been fabricated. Nothing is proven.**

| File | What it is |
|---|---|
| `ir-remote.kicad_sch` | Schematic — flat sheet, zoned power / MCU / USB / IR / inputs |
| `ir-remote.kicad_pcb` | Board — 2-layer, 30 × 58mm |
| `ir-remote.kicad_pro` | Project + net classes (POWER_IR, POWER_3V3, USB_DIFF) |
| `DESIGN-pcb.md` | Pin map, power tree, BOM, sleep budget, decisions |

---

## ⚠️ KiCad 10 net format — do not "repair" it

KiCad 10 (board format `20260206`) references nets **by name**:

```
(net "GND")        <- pads, tracks and vias, KiCad 10
(net 2 "GND")      <- KiCad <= 9 pads; the numeric index and the top-level
                      (net N "name") table no longer exist
```

`kicad-cli --save-board` — KiCad's own serialiser — writes the name-only form,
and DRC resolves it correctly (`Pad 5 [BTN1]`, `Track [BTN1]`). The kicad-mcp
writer produces the same thing, correctly.

**This tripped me once.** `grep '(net [0-9]'` returns zero on a perfectly healthy
KiCad 10 board, which looks alarming. I concluded the MCP was corrupting the
file and wrote a script to add the old index table back. It "worked" only
because KiCad still parses the legacy form — the board was never broken, and the
script eventually introduced a genuine inconsistency of its own. Deleted.

**Check what this KiCad version actually writes before concluding a tool is
broken:**

```sh
kicad-cli pcb drc --output /tmp/drc.rpt ir-remote.kicad_pcb
grep -A3 unconnected /tmp/drc.rpt     # healthy: nets show as [GND], [BTN1], ...
```

## Real MCP traps that do apply

- **External edits block the next auto-save.** Touch the `.kicad_pcb` outside the
  MCP and its next save is *refused* (mtime guard, `diskChangedExternally`);
  your changes then exist only in server memory until they're lost. Call
  `open_project` to re-sync first.
- **`assign_net_to_class` and `add_net_class` are advertised but not
  implemented** — they return `Unknown command`. Net-class assignment has to be
  written into `ir-remote.kicad_pro` (`net_settings.netclass_patterns`) directly.
- **`refill_zones` has a documented segfault risk** on the swig backend. Use
  `kicad-cli pcb drc --refill-zones --save-board` instead — it fills zones
  natively and safely.
- **ERC violation coordinates from the MCP are in unusable normalised units.**
  Use `kicad-cli sch erc` for a readable report.

---

## Verification commands

```sh
# ERC
kicad-cli sch erc --output erc.rpt --severity-all ir-remote.kicad_sch

# DRC, refilling zones first (DRC on unfilled pours is meaningless)
kicad-cli pcb drc --refill-zones --save-board --output drc.rpt --severity-error ir-remote.kicad_pcb

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

**The MCP DSN export drops net classes** — everything comes out at 0.2mm,
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
