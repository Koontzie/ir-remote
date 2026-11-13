# Design — XIAO ESP32-C3 perf board rev 2 (battery + illuminated buttons)

Rebuild after the S3 devkit was killed (9 V from a faulty boost — see STATUS.md).
MCU is a **Seeed Studio XIAO ESP32-C3**. Fresh board, pin map chosen for the
pins the XIAO actually breaks out.

## Why C3 / why XIAO
BLE 5, supported by IRremoteESP8266 ≥ 2.8.2 (we run 2.9.0), NimBLE fine, low
power. XIAO form factor is tiny (20×17.5 mm), USB-C, flashes over native USB
Serial/JTAG — so UART0 (GPIO20/21) is free for GPIO use.

## ⚠️ Power architecture decision (2026-08-09): switch, not sleep
**There is no deep sleep and no wake pin.** The slide switch on the boost
converter's EN pin is the entire power story: switch off → boost disabled →
board fully dead (only the charger's µA-level battery drain remains). Switch
on → boost runs → board cold-boots. All earlier RTC-wake constraints
("buttons must be on GPIO0–5") are void. Phase 4 deep-sleep firmware is
**not needed and should not be written.**

## ⚠️ XIAO pin reality (why the old map died)
The XIAO breaks out only 11 GPIOs: 2,3,4,5,6,7,8,9,10,20,21 (as D0–D10).
**GPIO0 and GPIO1 do not exist on the headers.** The old map's button-3-on-
GPIO1 and VBAT-sense-on-GPIO0 were unwireable. VBAT sensing is off the table
on this module (Seeed confirms no spare pin for it); check charge level with
a meter or the charger's LEDs.

C3 strapping pins: **GPIO2, GPIO8, GPIO9** (XIAO D0/D8/D9 — GPIO9 is also the
BOOT button). All three left unconnected on purpose. Anything that loads them
at boot (e.g. a driver transistor's base network) can change boot mode or
block the BOOT button from entering the bootloader.

## Pin map (XIAO silkscreen ↔ GPIO)

| Signal | Silkscreen | GPIO | Notes |
|---|---|---|---|
| Button 1 (slot 1) | D1 | 3 | INPUT_PULLUP, pressed = LOW |
| Button 2 (slot 2) | D3 | 5 | |
| Button 3 (slot 3) | D4 | 6 | |
| IR emitter base | D2 | 4 | 2N2222 low-side, unchanged from S3 build |
| Ring LED 1 | D5 | 7 | 2N2222 low-side, PWM (LEDC) |
| Ring LED 2 | D6 | 21 | UART TX pin — free, USB CDC handles serial |
| Ring LED 3 | D7 | 20 | UART RX pin — same |
| — spare — | D10 | 10 | free, safe |
| — do not use — | D0/D8/D9 | 2/8/9 | strapping / BOOT |

## Power chain

```
LiPo ──► Adafruit 4410 Micro-Lipo (charge only!) ──► boost (5V out, EN pin)
         feed the boost from the VBAT pad, NOT the "5V" pad (= USB VBUS in)
                                                        │
   slide switch: middle→EN, one outer→VIN+, other outer→GND
                                                        │
boost OUT+ ──► 5V rail ──► IR driver, LED rings
                 └──►|── XIAO 5V pin   (1N5817 Schottky, REQUIRED — the 5V
GND common everywhere   pin is tied to USB VBUS; the diode stops the boost
                        and a plugged-in USB cable from back-feeding each other)
470µF across 5V↔GND near the IR driver (parallel — nothing routes through it)
```

⚠️ **Bench the boost alone at 5.0–5.2 V before it ever touches the XIAO.**
A faulty boost at 9 V is what killed the S3. This check is mandatory on every
new/re-adjusted boost module.

## Buttons — FLM12-FJ-6 (12 mm, illuminated, self-reset)
Four lugs, two independent circuits:
- **NO + C** = the switch. GPIO → NO, C → GND. `INPUT_PULLUP`, pressed = LOW.
  No polarity, no resistor.
- **LED+ / LED−** = illumination ring, rated 5–24 V (internal resistor).
  LED+ → 5 V rail; LED− → low-side driver → GND.

⚠️ **12 mm, not 16 mm** — the enclosure was scaled for 16 mm holes (7.6 %).
It needs rescaling (~×0.75, then re-measure) or the buttons will swim.

## LED driver — 3× 2N2222, not ULN2003
Decision 2026-08-09: discrete 2N2222s (1 kΩ base resistor each, same pattern
as the IR driver). The ULN2003 the old rev suggested drops ~0.9 V at the
output, leaving the rings ~4.1 V against their 5 V minimum rating — likely
dim. A 2N2222 drops ~0.2 V. Also avoids putting a driver-input load on any
strapping pin.

All three LED pins are PWM-capable via LEDC — brightness ramps and breathing
effects available, not just on/off.

## LED feedback vocabulary (decided 2026-07-31)

All three buttons are **blue** — single colour, fixed in hardware. Meaning is
carried entirely by **pattern and brightness**, never hue.

**Core behaviour (Tyler's spec):** cascade on power-up → then hold steady dim
while on → flash bright on press and on send.

| Event | Pattern |
|---|---|
| Power-up / boot | **Cascade:** LED1→2→3 blink in sequence, ~150 ms each, then all settle to the idle level. Confirms the board is alive and which buttons exist. |
| Idle (on) | **All three steady at ~25 % PWM.** The buttons are findable in a dark AV closet — this is the point. |
| Button pressed | That button snaps to 100 % for ~80 ms, then back to idle. "I heard you." |
| IR sent OK | Same button double-pulses at 100 % after the send completes. Distinguishes registered-press from actually-transmitted. |
| Empty slot | Three fast blinks on that button, then back to idle. |
| BLE connected | Single slow breathe across all three, then idle. |
| Sweep / Identify running | Chase across all three until STOP. |
| Off | Switch off — everything dark, board unpowered. |

**Implementation note (2026-08-10) — the table is implemented as written.** Two
choices worth recording:
- **Sweep "until STOP" has no explicit stop signal** in the firmware — the sweep
  is just a rapid series of direct-send trigger writes. Realized as a
  self-terminating chase: each direct send (re)starts the chase and refreshes a
  **500 ms keep-alive** (`kSweepHoldMs`); while the sweep keeps sending, the
  chase runs continuously, and it returns to idle ~500 ms after the last send.
  A lone direct send therefore shows one brief chase step. No message-protocol
  change was needed.
- **Precedence:** whole-board animations (boot / breathe / chase) own all three
  rings while active; per-ring events (press / sent / empty) render only when no
  board animation is running. A press during the ~1.2 s connect-breathe is
  dropped for the LEDs only — the IR still fires. Rare and self-correcting.

### Power budget under the switch model
Idle draw ≈ 11 mA for rings at 25 % + ~10–15 mA C3 BLE-idle ≈ 25 mA at 5 V →
~45 mA from the cell through the boost. A 400 mAh cell gives roughly **8–9
hours switched on**. That's fine for a use-pattern of "switch on, do AV work,
switch off" — the switch replaces all sleep discipline. Keep the idle PWM
level in one constant so it's trivial to dim if runtime disappoints.

## Firmware changes needed
1. Pin constants → the table above (buttons 3/5/6; IR stays on 4). ✅ 2026-08-09
2. LED driver module: `ledSignal(event, buttonIndex)` with the pattern table,
   non-blocking (millis-based state machine — must NOT block the 38 kHz IR
   send or the BLE stack; a blocking delay() in a BLE callback is already a
   suspected cause of the `reason 520` disconnects). ✅ 2026-08-10 — `ledInit()`
   / `ledTick()` / `ledSignal()` in `remote_ble.ino`, LEDC PWM on GPIO7/21/20,
   no `delay()`, phases computed from elapsed time so the ~70 ms IR send just
   resumes cleanly. Idle brightness is the single constant `kRingIdleDuty`
   (64/255 ≈ 25 %). **Confirmed on hardware: boot, and rings PWM-init clean;
   the seven visual patterns await Tyler's eyes (see DEVLOG 2026-08-10).**
3. ~~Deep-sleep wake mask~~ — **dropped.** Power switch supersedes sleep/wake.

Everything else — GATT service, UUIDs, slot/NVS logic, the web app — is
unchanged.
