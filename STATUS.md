# IR-REMOTE — STATUS

**Status:** Active
**Updated:** 2026-07-19

## Where it's at
Phase 0 (salvage) done. **Phase 1 COMPLETE — pass gate met 2026-07-19: the Samsung
TV toggled power.** IR path proven end to end: firmware → GPIO4 → LED → real device.

`firmware/phase1_ir_test` sends Samsung power `0xE0E040BF` (`sendSAMSUNG`, 32 bits)
on GPIO4 every 3s; serial shows the banner then a clean 3.00s `sent` cadence.

**Range is only a few inches** — expected, not a defect. Direct GPIO drive
(GPIO4 → 150Ω → LED → GND) is ~13mA where a real remote pulses its LED at 100mA+.
The NPN stage in PLAN.md is what buys range; add it before Phase 3.

### Toolchain (macOS)
- `arduino-cli` 1.5.1 (Homebrew)
- esp32 core **3.3.10**, IRremoteESP8266 **2.9.0**
- Native USB CDC port, FQBN `esp32:esp32:esp32s3:CDCOnBoot=cdc`.
  **Port number is not stable** — seen as both `usbmodem2101` and `usbmodem1101`
  across replugs/jacks. Re-check with `arduino-cli board list` before flashing.

```
arduino-cli compile --fqbn esp32:esp32:esp32s3:CDCOnBoot=cdc firmware/phase1_ir_test
arduino-cli upload -p <PORT> --fqbn esp32:esp32:esp32s3:CDCOnBoot=cdc firmware/phase1_ir_test
sleep 20 | arduino-cli monitor -p <PORT> -c baudrate=115200
```

## Next step
Phase 2: BLE GATT (NimBLE-Arduino) + Bluefy web app — see PLAN.md.

## Blocked on
Nothing. Phase 1 fully verified including the physical pass gate.

### RESOLVED — "LED doesn't light from GPIO4"
Symptom: LED lit when wired to 3V3, appeared dead when driven from GPIO4.
**Not a fault.** The two tests aren't comparable — 3V3 is a steady glow, while the
IR send is a ~70ms burst of 38kHz-modulated pulses once every 3s, far too brief and
dim to catch by eye on a selfie cam. Confirmed by flashing a steady-drive test
(GPIO4 HIGH 3s / LOW 3s, no modulation): LED lit normally. Diagnostic sketches kept
out of the repo, in the session scratchpad.
**Reusable trick:** to test the LED/GPIO path, drive the pin steady — never judge
the drive path by watching a modulated IR burst.

### RESOLVED — board was stuck in ROM download mode
Kept for reference; this signature is easy to misread as a firmware failure.
After live-soldering, every sketch went silent. Diagnosis (2026-07-18):
- Chip is healthy: ESP32-S3 rev v0.2, 8MB flash, eFuse 3.3V, MAC reads, stub
  flasher runs. Flash image verified intact ("No changed sectors found").
- Not a brownout/LED short: a diagnostic sketch that never drives GPIO4 was
  equally silent, ruling that out.
- **Decisive test:** `esptool --before no-reset --after no-reset flash-id` synced
  successfully — the chip was *already* in the bootloader with nothing having
  reset it. It never reaches the application.
- **Cause: GPIO0 (BOOT) held LOW at reset** — the strapping pin PLAN.md warns
  about. Suspects, in order: BOOT button stuck/bridged; solder bridge onto GPIO0;
  a stray wire landed on pin 0 instead of pin 4.
- **Fix was physical** (freeing GPIO0), and it worked — board now boots the app
  normally. Reflash was never needed; flash reported "No changed sectors found"
  every time, i.e. the image was correct throughout.
- **Lesson:** silent serial + flash-verifies-clean + uploads that never need the
  BOOT/RESET dance == stuck in download mode. Test it with
  `esptool --before no-reset --after no-reset flash-id`: if it syncs with nothing
  having reset the chip, it was already parked in the bootloader. Don't reflash —
  check the strapping pins.

## Notes
- **RESOLVED 2026-07-19 — `arduino.cc` network block.** On 2026-07-18 the whole of
  `arduino.cc` was unreachable (DNS resolved, TLS reset — SNI/IP filtering, not a
  sandbox artifact), which broke `core update-index` and `lib install`. Worked
  around by patching `package_esp32_index.json` to drop the `arduino:dfu-util`
  dependency and hand-installing IRremoteESP8266 from its GitHub release tag.
  **All of that is now undone and no longer applies** — Tyler moved to a private
  network. Index restored from backup, both indexes refreshed, `esp32:esp32`
  reinstalled cleanly with `dfu-util` present, and IRremoteESP8266 2.9.0
  reinstalled through the library manager so it's properly tracked. No local
  patches remain; `core update-index` is safe to run.
- **Wiring deviates from PLAN.md on purpose:** GPIO4 → 150Ω → IR LED → GND, no NPN.
  That's ~13mA vs the 100mA+ pulses the transistor drive is for, so **range will be
  inches, not across the room.** If the TV doesn't toggle at close range, suspect the
  drive current before suspecting the code. Add the transistor stage before Phase 3.
- `arduino-cli monitor` exits instantly if stdin is closed (it forwards stdin to the
  port) — hold stdin open (`sleep 20 | arduino-cli monitor ...`) when scripting it.
- USB CDC buffers output while no host is attached, so the first several `sent` lines
  dump in a burst on connect. Timestamp the stream to read the true cadence.
- USB power through Phase 3; battery decision deferred (see tripwires in PLAN.md).
- Possibly this is the "Remote-App" slot from the master dashboard — confirm and
  give it its one-line definition there if so.
