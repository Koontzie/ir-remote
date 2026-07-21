# CC Brief — Custom PCB (KiCad): compact BLE IR remote

Working dir `~/dev/ir-remote`. Read `PLAN.md`, `STATUS.md` first — the breadboard
prototype this board is based on is fully documented there (Phase 3 "as built").
**This brief has 7 steps. STOP at each ⛔ TYLER GATE and wait for his review.**
Do not order boards, and do not touch the working firmware/ or app/ code.

## The product
A pocketable, USB-C-rechargeable BLE IR remote. Everything the breadboard does
(BLE GATT config, 5 slots, physical buttons, IR blast) on a board small enough
for a printed case. Target: ≤ 30×50mm, 2-layer, hand-solderable parts
(0603 minimum, no BGA/QFN-under-body unless unavoidable).

## Electrical spec (decided — don't relitigate without flagging)

**MCU:** ESP32-S3-WROOM-1-N8 module (matches all existing firmware).
Antenna keepout at board edge per Espressif layout guide — no copper under
the antenna zone, module antenna overhangs or sits at board edge.

**Power (no boost converter — 5V rail does not exist on this board):**
- 1S LiPo 250–500mAh, JST-PH 2-pin connector.
- Charger: MCP73831 (500mA program resistor) or TP4056 — whichever has the
  better KiCad standard-lib symbol/footprint story. Charge LED.
- Regulator: AP2112K-3.3 (600mA, ~55µA IQ, low dropout — same part family as
  the LocalForge wand spec). Powers the ESP32 only.
- IR drivers fed DIRECTLY from VBAT (3.0–4.2V), not the LDO.
- USB-C VBUS → charger only. Board runs while charging (power-path: simple
  diode-OR or charger-with-power-path if lib support is clean).
- Deep-sleep budget: < 20µA total. That constrains every always-on part:
  no UART bridge chip (native USB only), low-IQ LDO, no LEDs on quiet rails,
  voltage-divider battery sense switched or very high impedance.

**USB-C (charge + native USB programming):**
- USB2-only 16-pin USB-C receptacle. CC1/CC2 → 5.1kΩ to GND (device role).
- D+/D− → ESP32-S3 GPIO19/GPIO20 (native USB — this is how it's programmed
  and how Serial works; CDCOnBoot=cdc already proven on the devkit).
- ESD array on D+/D−/VBUS (USBLC6-2SC6 class).
- BOOT (GPIO0) and RESET (EN) tactile switches on-board — the unbrick path.
  Respect the strapping-pin history in STATUS.md: nothing else on GPIO0.

**IR output — two channels, both 940nm, driven from VBAT:**
- CH1 "room blast": wide-angle LED (±60° class), ~100mA pulses.
  GPIO4 → 1kΩ → NPN/MOSFET low-side; resistor ≈ 22Ω from VBAT.
- CH2 "long throw": narrow-beam LED (±10–15° class, e.g. TSAL6100-type),
  ~150–200mA pulses. GPIO7 → driver; resistor ≈ 12Ω.
- Drivers: S8050/2N2222-class NPN or small NMOS (AO3400-class) — pick per
  lib availability; note the choice. Bulk cap (≥100µF ceramic/tantalum or
  electrolytic) on VBAT near the drivers.
- Firmware picks a channel per send (or both); pins are independent.

**Buttons:** 5 tactile switches, all on RTC-capable GPIOs (≤21) for EXT1
deep-sleep wake: keep GPIO5 and GPIO2 (firmware already maps them), add three
more RTC-capable pins avoiding strapping pins (0/3/45/46) and USB (19/20).
Document the final pin map prominently.

**Battery sense (nice-to-have):** VBAT divider → ADC pin, high-value
resistors (≥1MΩ total) or MOSFET-switched, so the app can show battery %.

## Steps

### Step 1 — Tooling assessment (honest, before designing anything)
Check what's actually available: is a KiCad MCP configured in this
environment? (`claude mcp list` / config.) Is KiCad itself installed
(`brew list kicad` / `kicad-cli version`)? KiCad MCPs vary wildly — many only
do project inspection/DRC/BOM, not schematic authoring. Determine and REPORT:
(a) full authoring via MCP, (b) programmatic authoring via Python
(kicad-skip / SKiDL / kicad-cli), or (c) MCP for verification + manual-ish
generation. Verify the KiCad standard libs cover: ESP32-S3-WROOM-1
(RF_Module), USB-C receptacle, MCP73831/TP4056, AP2112K (or SOT-23-5
generic), USBLC6. List any missing symbols/footprints and where they'll come
from (SnapEDA/Ultra Librarian/hand-made).
⛔ TYLER GATE 1: present the tooling reality + workplan before proceeding.

### Step 2 — Design doc
`hardware/DESIGN-pcb.md`: final pin map, power tree diagram, part numbers
with 1-line rationale, deep-sleep current budget table (per-part IQ adding
to <20µA), and open questions. Keep decisions traceable to this brief.
⛔ TYLER GATE 2: pin map + BOM review before schematic work.

### Step 3 — Schematic
KiCad project in `hardware/`. Clean sheets: power / MCU / USB / IR / inputs.
ERC clean or every warning explained in the design doc.

### Step 4 — Layout
2-layer, ≤30×50mm target. Priorities: antenna keepout (module at edge),
IR LEDs at the "front" edge side-by-side, USB-C + buttons ergonomics
(buttons on top face), battery pads/connector placement for a pouch cell
under or beside the board, fat traces VBAT→IR drivers (100mA+ pulses),
ground pour both sides, stitching vias. DRC clean at JLCPCB 2-layer rules.

### Step 5 — Verification pass
Run every check the tooling allows: ERC, DRC, netlist vs design-doc pin map,
3D/board render exported as image for Tyler. Cross-check strapping pins one
final time (GPIO0/3/45/46 clean, GPIO19/20 = USB only).
⛔ TYLER GATE 3: render + reports review.

### Step 6 — Outputs
Gerbers + drill (JLCPCB naming), BOM csv with LCSC part numbers where
possible, pick-and-place file, `hardware/README.md` with fab notes
(board thickness 1.6mm, HASL fine).

### Step 7 — Chapter close
Commit + push. STATUS.md: PCB status, what's verified vs unverified (be
blunt: nothing is proven until boards arrive), next step = order boards
(Tyler's call) + interim perf-board build per PLAN. STOP.

END OF BRIEF
