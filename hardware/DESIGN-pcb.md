# DESIGN — Custom PCB (BLE IR remote)

**Status:** GATE 2 PASSED 2026-07-21 — decisions below are final. Schematic in progress.
**Created:** 2026-07-21 · Traceable to `docs/CC-BRIEF-pcb.md`
**Target:** 2-layer, **30 × 58mm**, hand-solderable (0603 min), ESP32-S3-WROOM-1-N8.

> ### ⚠️ Approved deviation from the brief: 30 × 58mm, not ≤ 30 × 50mm
> Approved at Gate 3, 2026-07-21. **Reason: the antenna keepout is
> non-negotiable.** The ESP32-S3-WROOM-1 footprint declares 15 keepout rule
> areas around its antenna, and Espressif's layout guide requires that clearance
> for the radio to work at all. At 30 × 50mm, DRC put R13, SW1, SW4 and SW6
> *inside* those keepout areas, with 15 further courtyard overlaps between the
> button block and the module — 36 violations that were all one symptom: the
> outline was too small for the module + 7 buttons + 2 THT IR LEDs + USB-C +
> JST. Nudging parts could not fix it.
> +8mm on the long axis buys ~4mm between the buttons and the module and clears
> every part out of the antenna zone. The board is still pocketable and still
> sized for the 503035 cell. **Shrinking the board would mean degrading the
> antenna — that trade was refused.**

**Product constraint: BLE only. WiFi is permanently disabled in firmware.**
Not merely unused — never initialised. This is what lets a 500mA LDO carry the
MCU with margin (WiFi TX peaks ~355mA; BLE TX peaks ~130mA) and it keeps ADC2
off the table permanently, which is why VBAT_SENSE lives on ADC1 (§2).

Everything here is a paper design. **No claim in this document has been
validated on hardware.** Current figures are datasheet-typical and flagged
where I have not personally confirmed them against a datasheet PDF.

---

## 1. Decisions taken at Gate 2

### 1.1 LDO: HT7833 (SOT-89) — replaces the briefed AP2112K

The brief specified both `AP2112K-3.3 (~55µA IQ)` and `deep-sleep budget < 20µA`.
**The regulator alone was ~3× the entire budget** — the two could not both hold.
Tyler's call: **HT7833**, 500mA, SOT-89.

| LDO | IQ (typ) | Iout | Pkg | Sleep total |
|---|---|---|---|---|
| AP2112K-3.3 (as briefed) | ~55µA | 600mA | SOT-23-5 | ~65µA ✗ |
| **HT7833 (chosen)** | **4µA** | **500mA** | **SOT-89** | **~14.5µA ✓** |

500mA of headroom keeps the BLE TX peak (~130mA) comfortable, and SOT-89 is a
larger, easier hand-solder package than SOT-23 with far better thermals
(θJA 200°C/W vs 500°C/W).

#### ⚠️ Pinout: web sources are wrong about this part — verify against the PDF

Two independent web searches both reported HT7833 SOT-89 as **pin2=VOUT,
pin3=VIN**, and both claimed an input range of **"4.5V to 8V"** (which would have
disqualified the part for a 3.0–4.2V LiPo outright). **Both claims are false.**

Confirmed against the Holtek HT78xx series datasheet **Rev. 1.50, 2019-04-03**,
Pin Description table:

| SOT-89 pin | Name | | Spec | Datasheet value |
|---|---|---|---|---|
| **1** | **GND** | | VIN max | 8V (abs max supply 8.5V) |
| **2** | **VIN** | | VIN min | **none specified** — LiPo range is fine |
| **3** | **VOUT** | | IQ (IO=0mA) | 4µA typ / **7µA max** |
| — | *(no CE pin in SOT-89)* | | Dropout @3.3V | 500mV typ / 650mV max **at 500mA** |
| | | | Current limit | 500mA min |

Because the real pinout is GND/VIN/VOUT, the stdlib symbol
**`Regulator_Linear:HT75xx-1-SOT89`** (same Holtek TinyPower family, identical
package and pin order) is an exact match. **No generic symbol or hand-made part
is needed** — the Gate 2 fallback plan turned out to be unnecessary.

Dropout is specified at 500mA; we never draw that. At the ~130mA BLE peak expect
~130mV, so the 3V3 rail holds regulation down to VBAT ≈ 3.45V. Below that the
rail sags with the cell instead of regulating — benign, since the ESP32-S3 runs
to 3.0V and a 1S LiPo at 3.45V is nearly empty.

### 1.2 Charge rate: R_PROG = 4.7kΩ (212mA), cell 400–500mAh

The brief said "500mA program resistor" while also allowing a 250mAh cell — that
combination is 2C, a fire risk, not just a wear issue. Resolved by fixing the
cell size instead of the resistor.

**Cell: 503035-class LiPo, 400–500mAh, ~30 × 35 × 5mm, with integral PCM.**
At 212mA that is **0.42–0.53C** — comfortably in the 0.5C sweet spot. Charge
time ≈ 2h for 400mAh. `I_charge = 1000V / R_PROG` (MCP73831 datasheet).

The 30 × 35mm cell footprint sits under the 30 × 50mm board (§8) with the JST
lead exiting toward the bottom edge.

### 1.3 Gate resistor: 100Ω, not the briefed 1kΩ

The brief says `GPIO4 → 1kΩ → NPN/MOSFET`. 1kΩ is correct for an **NPN base**
(current-driven). I'm proposing **MOSFETs** (see §4), which are voltage-driven —
1kΩ into ~700pF Ciss gives a ~0.7µs edge on a 13µs half-cycle at 38kHz, which
smears the carrier. **100Ω series + 100kΩ pull-down** is the right MOSFET
equivalent. The pull-down is not optional: it holds the gate off while the ESP32
is in reset or deep sleep, otherwise a floating gate can half-turn-on the LED and
quietly eat the battery.

---

## 2. Pin map (FINAL — firmware depends on this)

ESP32-S3-WROOM-1-N8. All button pins are RTC-capable (GPIO 0–21) for EXT1
deep-sleep wake. Strapping pins 0/3/45/46 and USB 19/20 respected.

| Signal | GPIO | Dir | Why this pin |
|---|---|---|---|
| **IR_CH1** (room blast) | **4** | out | Unchanged from Phase 1–3 firmware. RMT-capable. |
| **IR_CH2** (long throw) | **7** | out | Per brief. RMT-capable, RTC, not strapping. |
| **BTN1** | **5** | in, pull-up | Already mapped + proven in firmware. RTC ✓ |
| **BTN2** | **2** | in, pull-up | Already mapped in firmware (GPIO6 was not broken out on the devkit). RTC ✓ |
| **BTN3** | **15** | in, pull-up | RTC ✓, exposed on WROOM-1, free |
| **BTN4** | **16** | in, pull-up | RTC ✓, exposed, free |
| **BTN5** | **17** | in, pull-up | RTC ✓, exposed, free |
| **VBAT_SENSE** | **1** | ADC | **ADC1_CH0 — must be ADC1.** ADC2 is unusable while the radio is on. |
| **BOOT** | **0** | strap | Tactile to GND + 10k pull-up. **Nothing else on this net** (see STATUS.md — a stray connection here cost a debugging session). |
| **RESET** | **EN** | — | Tactile to GND + 10k pull-up + 1µF |
| **USB D−** | **19** | — | Native USB only |
| **USB D+** | **20** | — | Native USB only |

Buttons wire `GPIO → switch → GND`, `INPUT_PULLUP`, pressed = LOW — identical to
the breadboard, so Phase 3 firmware moves over with only the BTN3–5 additions.

**Deliberately unused:** 3/45/46 (strapping), 26–37 (flash), 38–48 (no need).

**EXT1 wake mask** = GPIO 2, 5, 15, 16, 17 → `ext1_wakeup(mask, ANY_LOW)`.

---

## 3. Power tree

```
USB-C VBUS (5V) ──┬── USBLC6-2SC6 (ESD: VBUS, D+, D−)
                  │
                  └── MCP73831 VDD ──> VBAT (3.0–4.2V) ──┬── JST-PH ── LiPo 1S
                        R_PROG 4.7k                       │            (protected cell)
                        STAT ── 1k ── LED (charge)        │
                                                          ├── HT7833 (SOT-89) ──> +3V3 ──> ESP32-S3
                                                          │                                (only load)
                                                          ├── 100µF bulk
                                                          │
                                                          ├── 22Ω ── IR LED CH1 ── AO3400A ── GND
                                                          │                          ▲ GPIO4
                                                          ├── 12Ω ── IR LED CH2 ── AO3400A ── GND
                                                          │                          ▲ GPIO7
                                                          └── 2M/2M divider ──> GPIO1 (ADC1)
```

**No 5V rail exists on this board.** VBUS goes to the charger and nowhere else.

**No power-path IC.** The load hangs off the VBAT junction (the Adafruit Feather
arrangement). Known and accepted tradeoff: while charging, load current is
indistinguishable from charge current, so the MCP73831's termination is
imprecise and the cell may top-off cycle. At ~12µA sleep / ~40mA active against
212mA charge this is a non-issue in practice. A diode-OR was rejected — its
0.3V drop would break both charging and the LDO headroom.

**Battery protection is in the cell, not on the board.** Spec a pouch cell with
an integral PCM. There is no on-board over-discharge cutoff.

---

## 4. Bill of materials (with rationale)

| Ref | Part | Pkg | KiCad symbol | Why |
|---|---|---|---|---|
| U1 | ESP32-S3-WROOM-1-N8 | module | `RF_Module:ESP32-S3-WROOM-1` | Matches all existing firmware |
| U2 | **HT7833** | **SOT-89** | `Regulator_Linear:HT75xx-1-SOT89` | §1.1 — 4µA IQ makes <20µA reachable; 500mA + good thermals. **Symbol is a family match, verify pinout GND/VIN/VOUT** |
| U3 | MCP73831-2-OT | SOT-23-5 | `Battery_Management:MCP73831-2-OT` | Your call at Gate 1. Smallest 1S charger with a clean stdlib symbol |
| U4 | USBLC6-2SC6 | SOT-23-6 | `Power_Protection:USBLC6-2SC6` | ESD on D+/D−/VBUS |
| J1 | USB-C recept. USB2 16P | SMD | `Connector:USB_C_Receptacle_USB2.0_16P` | Charge + native USB programming |
| J2 | JST-PH 2-pin | TH | `Connector_Generic:Conn_01x02` | Battery. **Polarity differs by vendor — silkscreen it** |
| Q1,Q2 | **AO3400A** | SOT-23 | `Transistor_FET:AO3400A` | 30mΩ NMOS. Beats an NPN's 0.25V Vce(sat), which matters at VBAT=3.0V |
| D1,D2 | IR LED 940nm | — | `Device:LED` | D1 wide ±60°, D2 narrow ±10–15° (TSAL6100 class) |
| D3 | LED (charge status) | 0603 | `Device:LED` | On VBUS side of STAT — **zero battery drain when unplugged** |
| SW1–5 | Tactile SPST | SMD | `Switch:SW_Push` | `SW_SPST_SKQG_WithStem`, top face |
| SW6,7 | Tactile (BOOT, RESET) | SMD | `Switch:SW_Push` | The unbrick path |
| R1 | 22Ω | 0603 | | CH1 current set, §5 |
| R2 | 12Ω | 0603 | | CH2 current set, §5 |
| R3,R4 | 100Ω | 0603 | | Gate series, §1.3 |
| R5,R6 | 100kΩ | 0603 | | Gate pull-down, §1.3 |
| R7,R8 | 5.1kΩ | 0603 | | CC1/CC2 → GND, UFP device role |
| R9 | 4.7kΩ | 0603 | | R_PROG → 212mA charge, §1.2 |
| R10,R11 | 2MΩ | 0603 | | Battery divider, §6 |
| R12,R13 | 10kΩ | 0603 | | BOOT / EN pull-ups |
| R14 | 1kΩ | 0603 | | Charge LED |
| C1 | 100µF | 1210 | | **VBAT bulk beside the IR drivers** — supplies the 200mA pulses |
| C2 | 22µF | 0805 | | 3V3 bulk (Espressif module requirement) |
| C3 | 10µF | 0603 | | LDO output |
| C4 | 4.7µF | 0603 | | Charger VBAT |
| C5 | 1µF | 0603 | | EN RC reset |
| C6–C9 | 100nF | 0603 | | Decoupling + ADC reservoir (§6) |

All symbols/footprints verified present in the KiCad 10 stdlib at Gate 1.
**Nothing needs SnapEDA or a hand-drawn part.**

---

## 5. IR drive current

`I = (VBAT − Vf − Vds(on)) / R`, with AO3400A Vds ≈ 0.01V at these currents.

| | R | @3.0V (empty) | @3.7V (nominal) | @4.2V (full) |
|---|---|---|---|---|
| **CH1** wide, Vf≈1.35V | 22Ω | 75mA | 107mA | **130mA** |
| **CH2** narrow, Vf≈1.6V | 12Ω | 117mA | **175mA** | 217mA |

Both stay inside a TSAL6100-class 200mA DC / 1.5A pulsed rating, and IR carrier
duty is ~33% within a burst with bursts ~1% of wall time. Range should beat the
breadboard's 20–30ft: that was 64mA through two series LEDs off a 5V rail.

**Deliberate consequence:** brightness sags ~40% as the cell drains, because
these are resistor-set, not constant-current. Accepted — a constant-current sink
costs parts and quiescent draw, and IR range degrades gracefully.

---

## 6. Battery sense

2MΩ / 2MΩ divider → GPIO1 (ADC1_CH0). 4.2V → 2.1V, inside the 12dB-attenuation
range. Costs **1.05µA** continuous.

The ESP32 ADC wants a source impedance far below 1MΩ, so a **100nF reservoir cap
at the tap** is mandatory — it holds charge for the sample window. It stays
charged across deep sleep, so only the very first reading after a cold boot needs
a settling delay (~200ms).

A MOSFET-switched divider would drop this to ~0µA, but 1.05µA out of a 12µA
budget is not worth the part and the extra GPIO.

---

## 7. Deep-sleep current budget

Target < 20µA. **All values datasheet figures, none measured on hardware.**

| Item | Typ | Max | Confidence |
|---|---|---|---|
| ESP32-S3-WROOM-1 deep sleep (RTC mem + EXT1) | 7.0µA | 8µA | Espressif datasheet typ |
| **HT7833 quiescent** | **4.0µA** | **7.0µA** | ✅ Verified, HT78xx Rev 1.50 |
| MCP73831 battery drain, VDD floating | 2.0µA | 2.0µA | **Least certain — verify** |
| Battery-sense divider (2M+2M @ 4.2V) | 1.05µA | 1.05µA | Ohm's law, certain |
| USBLC6-2SC6 leakage | 0.2µA | 1.0µA | Datasheet max 1µA |
| AO3400A ×2, gates held low | 0.2µA | 2.0µA | Idss max 1µA ea; typ is nA |
| Charge LED (unplugged) | 0µA | 0µA | Structural — anode on VBUS |
| **TOTAL** | **≈14.5µA ✓** | **≈21µA ⚠** | |

**Typical passes with ~27% headroom. Worst-case-everything lands ~21µA, a hair
over target** — but that stacks every datasheet maximum simultaneously, which is
not a realistic operating point. Called out rather than hidden.

On a 450mAh cell at 14.5µA: **~3.5 years standby** — self-discharge, not the
circuit, becomes the limit. That is the correct place to land.

Same table with the briefed AP2112K: **65.5µA ✗**.

**The single largest unverified number is the MCP73831's reverse battery drain.**
If it turns out worse than ~2µA it is the one part that could push typical over
budget. Measure it first when boards arrive.

---

## 8. Layout intent (detail deferred to Step 4)

Board 30 × 50mm, 2-layer, 1.6mm, ground pour both sides + stitching vias.

**The one real conflict: the antenna and the USB-C both want a board edge, and
the IR LEDs want the *front* edge.** Proposed resolution:

```
        ┌──── FRONT (points at the TV) ────┐
   30mm │   [D1 wide]      [D2 narrow]     │  IR LEDs, side by side
        │                                  │
        │   SW1  SW2  SW3  SW4  SW5        │  buttons, top face
        │                                  │
        │  ╔══════════════════════════╗    │
        │  ║  ESP32-S3-WROOM-1        ║    │  module rotated 90°,
   50mm │ ◄╢  antenna at LEFT edge    ║    │  antenna overhangs left
        │  ╚══════════════════════════╝    │  ← KEEPOUT: no copper
        │                                  │
        │   [JST]   [USB-C] [D3 chg LED]   │  one cutout covers both
        └────────── BOTTOM ────────────────┘

   Battery: 503035 cell (30 × 35 × 5mm) sits UNDER the board,
   lead exiting toward the bottom edge into J2.
```

Rotating the module puts the antenna on a long edge, which frees the bottom edge
for USB-C (the ergonomic place for a charge port) and keeps the connector's metal
shell well away from the radiating element. Antenna keepout: no copper on either
layer, no pour, under and beyond the antenna region.

Fat traces (≥1mm) VBAT → C1 → IR drivers for the 200mA pulses. USB D+/D− routed
as a loose differential pair, short, no stubs.

---

## 9. Gate 2 resolutions (all closed 2026-07-21)

| # | Question | Decision |
|---|---|---|
| 1 | LDO | **HT7833 SOT-89.** Not MCP1700 — do not substitute for lib convenience. ≥22µF bulk on 3V3 regardless. |
| 2 | Charge rate / cell | **R_PROG 4.7kΩ (212mA)**, 503035-class 400–500mAh, ~0.5C |
| 3 | Edges | **Approved** — IR LEDs top/front, USB-C bottom, antenna overhang left |
| 4 | Charge LED | **Keep**, placed adjacent to USB-C so one enclosure cutout covers both |
| 5 | BOOT/RESET | **Top-face tactiles** |
| — | Drivers, sense, pin map | AO3400 + 100Ω/100kΩ, GPIO1 ADC1, pin map as tabled — all approved |

**Still unverified and carried forward:** MCP73831 reverse battery drain (§7),
and every current figure in this document until boards are measured.

---

## 10. ERC status (Step 3)

`ir-remote.kicad_sch` — 42 components, 27 nets.

```
** ERC messages: 35   Errors 0   Warnings 35
```

**0 errors.** No unconnected pins, no conflicting drivers, no missing power
flags. Unused ESP32 GPIOs (25 of them) and the USB SBU pins carry explicit
no-connect flags rather than being left to float through ERC.

An earlier build had 83 violations; the extra 48 were `endpoint_off_grid`,
caused by placing symbols at arbitrary mm coordinates so pins missed KiCad's
1.27mm connectivity grid. That is not cosmetic — off-grid pins produce wires
that *look* connected but fail to join during later manual editing. Fixed by
rebuilding the schematic with every component on a 2.54mm grid.

### The 35 remaining warnings are all `lib_symbol_mismatch` — explained

The MCP writes symbol definitions in KiCad 6/7 syntax (`(pin_numbers hide)`,
`(in_bom yes)`) while KiCad 10's libraries use a newer form, so every cached
symbol trips the comparison. `kicad-cli sch upgrade` reformats the file but does
not resolve it.

**Verified benign rather than assumed benign.** I compared every pin number,
name, and coordinate in the schematic's symbol cache against the on-disk library
for all 12 symbols used:

| Result | Symbols |
|---|---|
| Pin sets identical | 10 of 12 — incl. ESP32-S3 (41 pins), USB-C (17), MCP73831, USBLC6, HT7833 |
| Differ | `Device:R`, `Device:C` — **name only**, `~` vs `""` for an unnamed pin |

Pin *numbers* and *positions* match everywhere, which is what determines the
netlist and the footprint mapping. Nothing electrical rides on this warning.
In KiCad, *Tools → Update Symbols from Library* clears it.

## 11. Layout + DRC status (Steps 4–5) — GATE 3

Board 30 × 50mm, 2-layer, 1.6mm, rounded 2mm corners. All 42 footprints placed,
GND pour on both layers with an antenna notch, thermal drills corrected.

### DRC progression

| Stage | Violations | What changed |
|---|---|---|
| After netlist sync | 2016 | nothing placed, all parts stacked at origin |
| After placement + pours | 83 | real floorplan |
| After re-spacing back side | 48 | **5 shorts → 0**, edge clearance 18 → 2 |
| After drill fix | **36** | 12 drill violations → 0 |

### Two real defects found and fixed

1. **Back-side parts were shorting.** I placed the power section on a 2.8mm
   pitch, but 0603 *HandSolder* pads are ~2.7mm long end-to-end, so neighbouring
   parts touched: R10/R11 (VBAT↔GND), R9/R12 (PROG↔BOOT), C9/C10 (VBUS↔GND),
   C8/R14. Re-spaced to 3.5mm.
2. **U1's thermal vias are 0.2mm drill — under JLCPCB's 0.3mm minimum.** The
   stock KiCad `ESP32-S3-WROOM-1` footprint ships 12 thermal PTH vias at 0.2mm,
   which standard 2-layer fab will not produce. Enlarged to 0.3mm in the board
   (0.15mm annular ring on the 0.6mm pad — within JLCPCB's 0.13mm minimum).
   **This is a footprint-level trap that would have come back as a fab query.**

Also caught: the stitching-via tool works off the *board outline*, not the pour
outline, and wanted to drop vias at (4.5, 28.5), (8.5, 33) and friends — **straight
through the antenna keepout.** Not used. Stitching vias are still outstanding and
must be placed zone-aware.

### Current state after routing (2026-07-21)

Board **30 × 58mm**, 2-layer. **DRC: 0 violations at JLCPCB rules.**
294 track segments, 78 vias, GND pours on both layers, 27 hand-placed
stitching vias.

| Check | Result |
|---|---|
| DRC (JLCPCB rules, zones filled) | **0 violations** |
| Antenna keepout — copper audit, independent of DRC | **0 intrusions** |
| Critical nets routed with fat traces | VBAT + IR1/IR2 at 0.6mm, 3V3/VBUS 0.5mm, USB pair 0.25mm |
| **Unconnected items** | **32 — NOT finished** |

Unconnected breakdown: **GND 32 endpoints, +3V3 8, VBUS 6, IR2_CTRL 2,
IR1_GATE 2, BTN1 2** — 26 unconnected items.

Three autorouter passes were run:

| Pass | Setup | Result |
|---|---|---|
| 1 | 50 passes, pours present | 25 of 27 nets, 114 wires |
| 2 | 100 passes, existing routing preserved | **regression** — 101 wires, net gain of 1 connection |
| 3 | 120 passes, **pours stripped so GND must route** | **did not converge; killed at ~35 min, no output** |

Pass 3 is the right approach and should be resumed with a longer budget, but it
is expensive: 59 GND pins on a dense 2-layer board is a much harder problem than
the signal nets. **The pours were restored afterwards so the board is not left
in a degraded state.**

**This board is not ready for fab.** Steps 6–7 (gerbers, BOM, CPL) remain on
hold.

#### The ground pour cannot carry GND on this board

Worth recording, because it is counter-intuitive and cost several iterations.

A ground pour on both layers plus 90 stitching vias still left ~32 GND endpoints
unconnected, and adding vias barely moved the number (44 → 42 → 38 → 34 → 32).
The cause: **the back side is too dense for the pour to weave through.** KiCad's
fill fragments into 14 pieces on F.Cu and 15 on B.Cu, and several GND pads sit in
regions the pour cannot reach at all — so no number of stitching vias helps,
because there is no pour fragment adjacent to those pads to stitch *to*.

Compounding it: **Freerouting exported the pours as planes and therefore assumed
GND was already connected**, emitting a single GND wire across two full routing
passes. The board had *zero* routed GND segments while looking plausible.

Fix: strip the zones, export DSN without them so GND becomes an ordinary
routable net (own class, 0.4mm), route, then restore the pours on top. The pours
then serve as shielding and extra copper rather than as the GND network itself.

**Lesson: on a dense 2-layer board, do not assume a pour equals connectivity.**
Check the routed-GND-segment count, not just the DRC unconnected number.

Two self-inflicted problems worth recording, both caught by verification rather
than by luck:

- **A wrong rotation transform.** I computed footprint pad positions with
  `gy = fy + px·sinθ + py·cosθ`; KiCad uses `gy = fy − px·sinθ + py·cosθ`. Every
  pad of the 90°-rotated ESP32 module was therefore checked at a mirrored
  position, so the first batch of stitching vias landed on top of U1's pads.
  Caught by DRC, fixed by deriving the transform from a pad whose true position
  KiCad had already reported.
- **An invalid token silently bricked the board file.** Adding
  `(min_resolved_spokes 1)` to the `.kicad_pcb` `(setup)` block made KiCad
  fail with a bare "Failed to load board" — no line number, no token name. That
  rule belongs in `.kicad_pro`, where setting it did work.

### ⚠️ Sizing history: 30 × 50mm was too small

The 36 remaining violations are not scattered — they are all one story:

| Count | Type | Cause |
|---|---|---|
| 15 | `courtyards_overlap` | SW4/SW5 against U1, J1 against J2/D3 |
| 13 | `items_not_allowed` | R13, SW1, SW4, SW6 sitting inside the ESP32 footprint's own **antenna keepout rule areas** |
| 6 | `clearance` | SW4/SW5 pads vs U1's top pad row |
| 2 | `copper_edge_clearance` | J1 shield pads at the edge — expected for an edge connector |

The module is 18 × 25.5mm and its antenna clearance zone (which the KiCad
footprint declares as 15 keepout areas) extends well beyond the body. Add 5
buttons, 2 unbrick buttons, 2 THT IR LEDs, USB-C and a JST on a 30 × 50mm
outline and there is simply no room left. **This is not fixable by nudging
parts — the outline has to grow.**

**Recommendation: 30 × 58mm** (+8mm on the long axis). That buys ~4mm between
the button block and the module, and moves R13/SW1/SW6 out of the antenna zone.
It still fits a shirt pocket and still suits the 503035 cell. **Tyler's call —
this deviates from the ≤30 × 50mm target in the brief.**

### Not done yet — stated plainly

- **Signal routing: 0 of 26 nets.** 107 unconnected items. Freerouting is
  unavailable on this machine (no Java 21 runtime, no Docker, no jar), so there
  is no autorouter; manual routing was not started because the outline question
  above changes every trace.
- **GND is handled by the pours**, not by routed traces — but the pours are
  unfilled (`refill_zones` carries a documented segfault risk on the SWIG
  backend and was not run).
- Stitching vias not placed (see above).
- Design rules not yet set to JLCPCB values — DRC above ran against KiCad
  defaults, which is what caught the 0.2mm drills.

**Nothing here is proven. No board has been fabricated.**

### ❌ Retracted: the "MCP destroys connectivity" finding was wrong

An earlier revision of this document claimed the kicad-mcp writer corrupted the
board's net table, and shipped a `fix-nets.py` to repair it. **That was a
misdiagnosis and both are withdrawn.**

KiCad 10 (board format `20260206`) references nets **by name** — `(net "GND")` —
having dropped the numeric index and the top-level `(net N "name")` table that
KiCad ≤ 9 used. `kicad-cli --save-board`, KiCad's own serialiser, writes exactly
that form, and DRC resolves it correctly. The MCP was right; the board was never
broken.

The false positive came from `grep '(net [0-9]'` returning zero, which looks
alarming but simply means this KiCad version no longer writes that form. The
"repair" converted the file to the legacy format, which KiCad still parses for
backward compatibility — so nothing visibly broke and the wrong diagnosis
appeared confirmed. It later introduced a real inconsistency (147 of 150 pad
refs disagreeing with its own rebuilt table), which is how it was caught.

Kept as a note because the failure mode is instructive: **a grep returning zero
is evidence about the grep, not proof about the tool.** See `README.md` for the
MCP traps that are real.

## 12. Firmware deltas this board forces

Not in scope for this brief, but recording so nothing is lost:

- Add BTN3–5 on GPIO 15/16/17 to the existing button scan.
- Add IR_CH2 on GPIO7 + a channel selector in the `trigger` GATT payload.
- Add `ext1_wakeup` with mask {2,5,15,16,17} and the sleep/send/sleep cycle.
- Add battery % from GPIO1 → report over the `status` characteristic.
- IR drive is now VBAT-referenced, not the 5V rail — the 33Ω breadboard value is
  obsolete and superseded by §5.
