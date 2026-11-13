# Wiring Card — XIAO C3 battery build (canonical quick reference)

Battery-powered perf board, Seeed XIAO ESP32-C3. One glance, no archaeology.
(Previous S3 USB-powered card is in git history if ever needed.)

```
POWER CHAIN   [charger = Adafruit 4410 Micro-Lipo, USB-C. CHARGE ONLY, no boost]
  Battery ──► charger JST battery jack (polarized, just plug it in)
  Charger VBAT pad ──► boost VIN+    Charger GND pad ──► boost GND
  ⚠️ NOT the charger's "5V" pad — that is USB VBUS *input*, dead unless a
     USB-C cable is plugged in. Wiring the boost there = works on USB,
     completely dead on battery. (Cost a session 2026-08-10.)
  ⚠️ No protection IC on this charger — over-discharge cutoff lives in the
     Adafruit battery pack. A bare unprotected cell WILL be ruined by the
     boost draining it below ~2.5V.
  Boost OUT+  ──► 5V rail            Boost GND ──► GND rail
  5V rail ──►|── XIAO 5V pin         [1N5817 Schottky, band toward XIAO —
  XIAO GND ──► GND rail               REQUIRED: 5V pin ties to USB VBUS]
  470µF across the rails: (+) → 5V, (−) stripe → GND. Near the IR driver.
  (Cap is parallel — NOTHING routes through it. The 33Ω must NOT be in the
  cap's branch; that was the unlimited-current incident of 2026-07.)

POWER SWITCH (SPDT slide/toggle — gates boost EN, replaces sleep/wake)
  Middle pin ──► boost EN
  One outer  ──► boost VIN+  (= ON position)
  Other outer ──► GND        (= OFF position)
  Second pole (if present): unused, leave empty.
  Meter first: continuity middle↔one-outer per position, never both.

IR DRIVER (2N2222, TO-92)
  5V rail ──33Ω──► LED1 anode(+)
  LED1(−) ──► LED2(+)                 [series pair, both 940nm emitters]
  LED2(−) ──► COLLECTOR
  EMITTER ──► GND rail
  XIAO D2 (GPIO4) ──1kΩ──► BASE (middle leg)

  E vs C by meter (diode mode, red probe on Base, black on each outer):
  HIGHER forward drop = EMITTER → GND. Lower = COLLECTOR → LED2(−).
  Vendor leg order varies — always meter, never assume.

BUTTONS — switch half (FLM12-FJ-6: NO + C lugs, no polarity, no resistor)
  Button 1: XIAO D1 (GPIO3) ──► NO,  C ──► GND   → slot 1
  Button 2: XIAO D3 (GPIO5) ──► NO,  C ──► GND   → slot 2
  Button 3: XIAO D4 (GPIO6) ──► NO,  C ──► GND   → slot 3
  Firmware uses INPUT_PULLUP; pressed = LOW.

BUTTON LED RINGS (one 2N2222 per ring; rings 5–24V rated, internal resistor)
  Ring N: LED+ ──► 5V rail,  LED− ──► COLLECTOR,  EMITTER ──► GND rail
  Ring 1 base ◄──1kΩ── XIAO D5 (GPIO7)
  Ring 2 base ◄──1kΩ── XIAO D6 (GPIO21)
  Ring 3 base ◄──1kΩ── XIAO D7 (GPIO20)

NEVER CONNECT
  XIAO D0/D8/D9 (GPIO2/8/9) — strapping pins / BOOT button. Loading them
  can change boot mode or block bootloader entry. D10 (GPIO10) is the spare.

TWO USB-C PORTS, TWO DIFFERENT JOBS  (cost an evening 2026-08-14)
  XIAO's USB-C    = powers the chip, flashing, serial monitor.
                    Does NOT charge the battery.
  Charger's USB-C = charges the battery. Does NOT power the ESP32,
                    and does NOT feed the 5V rail on its own.
  ⚠️ On the XIAO's port alone with a flat cell you get: chip alive,
     serial fine, BLE advertising — and every LED dark and no IR,
     because the rail is fed by the boost and the 1N5817 blocks USB
     from back-feeding it. Looks exactly like a short. It isn't.
  BENCH SETUP: plug BOTH. Charger holds BAT near 4.2V so the boost
     runs and the rail is live; XIAO port gives you serial.
     (No load sharing — ignore the green LED in this mode and don't
     leave it unattended for hours.)

HEALTH CHECKS
  ⚠️ Boost alone FIRST, nothing on its output: 5.0–5.2V. 9V = the S3 killer.
  Switch ON → boost OUT 5.0–5.2V; switch OFF → ~0V.
  XIAO 5V pin with switch on: ~4.7V (5V minus Schottky drop) — normal.
  XIAO 3V3 pin: 3.3V after boot.
  Idle button GPIO→GND: ~3.3V; pressed: 0V.
  IR driver on (steady-drive test): C→E ≈ 0.2V, across 33Ω ≈ 3.3V (~100mA).
    C→E ≈ 3.4V + 33Ω ≈ 0.4V  == transistor E/C reversed (seen 2026-07-21).
  Ring driver on: ring lit bright; C→E ≈ 0.2V. Dim ring = check LED+/− polarity.
  5V↔GND unpowered: open, never ~0Ω.
  USB-C plugged in while switch on: allowed ONLY because of the 1N5817.
    If the diode was skipped, unplug the battery chain before flashing.
```
