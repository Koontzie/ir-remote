# IR-Remote — BLE-Programmable Universal Remote

**Goal:** Small 3–5 button universal remote. ESP32 WROOM sends IR codes; an iOS
"app" (web page opened in Bluefy) programs what each button does over BLE.
Codes sourced from Flipper-IRDB / irdb — no original remote needed.

**Created:** 2026-07-06 · **Hardware:** ESP32-S3 devkit + salvaged remote parts +
2× R13-507 16mm arcade momentary buttons (panel-mount, solder lugs — need jumper
wires soldered/clipped on for breadboarding; ideal for the final enclosure)

## Pin map (ESP32-S3)

| Signal | GPIO | Why |
|---|---|---|
| IR LED (via NPN) | 4 | Plain GPIO, RMT-capable |
| Button 1 | 5 | Physically wired to GPIO5 (bench-verified 2026-07-26). A GPIO6 firmware remap was tried but pin 6 was never actually wired, so button 1 went dead — reverted to GPIO5. RTC-capable, so EXT1 wake works |
| Button 2 | 2 | RTC-capable; GPIO5/6 also valid |
| Button 3 | 7 | RTC-capable, not a strapping pin (built on perf board 2026-07-26) |
| (Buttons 4–5 later) | 15, 16 | Same |

Avoid: 0/3/45/46 (strapping), 19/20 (USB), 26–37 (flash/PSRAM on many S3 modules).
Buttons wire GPIO→button→GND, `INPUT_PULLUP`, pressed = LOW.

⚠️ **GPIO2 is a strapping pin on the *classic* ESP32 but not on the S3** — most
"avoid these pins" lists online are written for the classic part. On the S3 the
strapping pins are only 0/3/45/46.

---

## Architecture

```
[iOS: Bluefy browser] ──Web Bluetooth──> [ESP32 BLE GATT]
                                              │ writes config to NVS (flash)
[physical buttons 3–5] ──GPIO──> [firmware] ──> [IR LED via NPN transistor]
                                              └──> TV / soundbar / etc.
```

- **Firmware:** Arduino framework + [IRremoteESP8266 v2.9.0](https://github.com/crankyoldgit/IRremoteESP8266)
  (despite the name, first-class ESP32 support; NEC/Sony/RC5/Samsung/etc.) +
  NimBLE-Arduino for BLE (lighter than Bluedroid).
- **BLE GATT design:** one service, two characteristics:
  - `config` (write): JSON like `{"btn":1,"proto":"NEC","code":"0x20DF10EF","bits":32}`
  - `status` (notify): ack / last-sent / battery
- **App:** single static HTML file using the Web Bluetooth API, opened in
  [Bluefy](https://apps.apple.com/us/app/bluefy-web-ble-browser/id1492822055) on iOS.
  Host on GitHub Pages (Web Bluetooth requires HTTPS). No Xcode, no signing.
- **Code source:** [Flipper-IRDB](https://github.com/Lucaslhm/Flipper-IRDB) —
  plain-text `.ir` files by brand/model. Paste protocol+code into the app; it
  writes to the ESP32.

## Salvage checklist (from donor remotes + devices)

| Part | Source | Notes |
|---|---|---|
| IR LED (940nm) | Any donor remote | Front of the PCB. Grab 2–3. |
| NPN transistor | Donor remote PCB | Drives the LED — ESP32 GPIO can't source enough current alone. If unsalvageable: 2N2222/S8050, pennies. |
| Tactile buttons | Remote PCB or other devices | Remote "buttons" are usually carbon-pad-on-membrane — NOT reusable as discrete switches. Salvage real tactile switches from other electronics, or use breadboard buttons. |
| Resistors | Any PCB | Need ~100–330Ω (LED current limit) + ~1kΩ (transistor base). |
| Battery contacts / holder | Donor remote shell | For Phase 4. |
| **IR receiver (TSOP38xx)** | TV / set-top box / DVD player — **NOT remotes** | Remotes only transmit. Optional: only needed to clone codes from physical remotes. Internet codes work without it. |

## Phases

**Phase 0 — Salvage audit.** ✅ Done.
**Phase 1 — IR transmit proof.** ✅ Done 2026-07-19 — Samsung TV toggled. Ran
direct GPIO drive (no NPN, ~13mA, inches of range) — transistor stage moved to Phase 3.
**Phase 2 — BLE + web app.** ✅ Done 2026-07-19 — TV toggled from a browser button.
Chrome → GATT → NVS → IR chain verified; artifacts `firmware/remote_ble/` +
`app/index.html`. GATT UUIDs and payload shapes recorded in docs/DEVLOG.md.
**Phase 2.5 — Bluefy on iPhone.** ✅ Done — iPhone → Bluefy → BLE → IR → TV verified.
**Phase 3 — NPN driver stage + physical buttons.** ✅ Done 2026-07-19. 2N2222 off
the 5V rail (33Ω, two IR LEDs in series, 1kΩ base) took range from ~5ft to
**20–30ft**. Button 1 (GPIO5) fires slot 1 standalone with no phone connected;
presses notify `pressed:N` and flash the slot in the app. Button 2 wired in
firmware on GPIO2, hardware not built yet.
**Phase 4 — Battery + deep sleep.** EXT1 wake on any button, send, sleep.
**Phase 5 — Enclosure.** Donor remote shell or printed case.

## Known tripwires

- **Phone-camera IR test:** the *front* (selfie) camera usually shows the IR LED
  flashing purple; main cameras often have IR filters and show nothing. Use the
  selfie cam before concluding the circuit is dead.
- **Never drive the IR LED straight off a GPIO.** GPIO max ~40mA absolute; decent
  IR range wants 100mA+ pulses through the transistor.
- **iOS Safari has no Web Bluetooth** — Bluefy (or WebBLE) is mandatory, not optional.
  The page must be served over HTTPS (GitHub Pages) for the API to be available.
- **AA-battery reality (Phase 4):** the devkit's AMS1117 LDO needs ~4.4V+ in, so
  3×AA works fresh but browns out as cells drain; and the devkit's USB-UART chip
  leaks mA even in deep sleep. Battery phase likely means 2×AA + boost converter,
  or a bare WROOM module. **Decision deferred — USB power through Phase 3.**
- **NVS, not EEPROM emulation** for stored codes — native, wear-leveled.

## Sources

- IRremoteESP8266 v2.9.0 (Jan 2026, ESP32 core 3.x support): https://github.com/crankyoldgit/IRremoteESP8266
- Bluefy Web BLE browser (active, v3.9.3 Jun 2026): https://apps.apple.com/us/app/bluefy-web-ble-browser/id1492822055
- Flipper-IRDB code database: https://github.com/Lucaslhm/Flipper-IRDB
- Official Flipper IRDB catalog: https://github.com/flipperdevices/IRDB
