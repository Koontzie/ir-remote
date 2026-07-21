# IR-REMOTE — STATUS

**Status:** Active
**Updated:** 2026-07-19

## Where it's at
Phase 0 (salvage) done. **Phases 1, 2, 2.5 and 3 all COMPLETE** (2026-07-19).

### Phase 3 — NPN driver stage + physical buttons ✅

**Circuit as built** (fed from the devkit's 5V/VBUS pin):
```
5V ──33Ω──► IR LED1 (+)─(−) ──► IR LED2 (+)─(−) ──► COLLECTOR
GPIO4 ──1kΩ──► BASE                                 EMITTER ──► GND
```
- Transistor **2N2222**, TO-92 plastic. Pinout identified empirically with a
  multimeter (diode mode) rather than assumed — E/C order varies by vendor even
  for the same part number. Middle pin is Base; of the outer two, the one reading
  the *higher* forward drop from Base is the Emitter.
- **Two salvaged IR LEDs in series** (the second tested as a genuine IR emitter on
  a selfie cam, not a red indicator). ~64mA pulses, vs ~13mA on the old direct
  GPIO drive.
- Buttons: **GPIO5 → slot 1**, **GPIO2 → slot 2**, `INPUT_PULLUP`, pin→button→GND.

**Pass-gate results:**
- ✅ **Range: ~5ft → 20–30ft.** The single biggest win of the phase.
- ✅ Physical button 1 toggles the TV from across the room.
- ✅ **Standalone** — works with Bluefy fully disconnected. It is a real remote,
  not a BLE accessory.
- ✅ Debounce verified clean at millisecond resolution: one press → exactly one
  event, no chatter. (A Samsung frame takes **109ms** to transmit — measured.)
- ✅ `pressed:1` notifies the app and flashes the matching slot row.
- ⏭️ **Button 2 not built** — no second button on hand, and GPIO6 (the originally
  planned pin) is not broken out on this devkit, hence the move to GPIO2. Firmware
  path is in place and untested on hardware.

**Phase 2 pass gate met: the TV toggled from a button in the browser.** Full chain
verified end to end — Chrome (Web Bluetooth) → BLE GATT write → JSON parse → NVS →
IR send → real device. Serial confirmed each layer:
```
[ble] config write: {"slot":1,"proto":"SAMSUNG","code":"0xE0E040BF","bits":32}
[nvs] slot 1 <- SAMSUNG 0xE0E040BF (32 bits)   [status] saved:1
[ble] trigger write: {"slot":1}
[ir]  slot 1 -> SAMSUNG 0xE0E040BF (32 bits)   [status] sent:1
```
NVS persistence proven by power-cycling: second boot skipped seeding and read
slot 1 back from flash.

**Phase 1 pass gate met** earlier the same day: the Samsung TV toggled power.
`firmware/phase1_ir_test` sends `0xE0E040BF` (`sendSAMSUNG`, 32 bits) on GPIO4
every 3s. Kept in the repo as the minimal known-good IR proof.

### Phase 2 artifacts
- `firmware/remote_ble/remote_ble.ino` — BLE GATT + IR, 5 NVS-backed slots
- `app/index.html` — self-contained Web Bluetooth app, no build step

**GATT — device name `IR-Remote`:**

| Role | UUID |
|---|---|
| service | `b457c32b-22b1-425f-8a88-4d6dc37ba4eb` |
| `config` (WRITE) | `d997012d-7d2b-47de-ae87-bae14df446ef` |
| `trigger` (WRITE) | `58397514-04a3-4265-9590-9d910c4e99d2` |
| `status` (NOTIFY) | `b8ddfe01-519f-430d-bd4e-aba0dd852e2c` |

`config` payload `{"slot":1,"proto":"SAMSUNG","code":"0xE0E040BF","bits":32}`
(slots 1–5; protocols NEC, SAMSUNG, SONY). `trigger` payload `{"slot":1}`.
`status` notifies `saved:N` / `sent:N` / `err:...`.

**Run the web app locally:**
```
cd ~/dev/ir-remote/app && python3 -m http.server 8000
```
Open `http://localhost:8000` in **desktop Chrome** — `localhost` counts as a secure
context, so Web Bluetooth works without HTTPS. Safari has no Web Bluetooth, ever.

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
**Phase 4 — battery + deep sleep.** EXT1 wake on the button pins (**GPIO5 and
GPIO2** — note GPIO2, not the GPIO6 in the original plan; both are RTC-capable on
the S3, which EXT1 requires). Wake → send → sleep.

Open questions carried in from PLAN.md's tripwires: the devkit's AMS1117 LDO wants
~4.4V+ in, and the onboard USB-UART chip leaks mA even in deep sleep — so this
likely means 2×AA + a boost converter, or moving to a bare WROOM module. The
circuit currently runs off **5V/VBUS, which only exists while USB is plugged in**;
battery power changes that rail and the 33Ω value should be rechecked against
whatever new supply voltage is chosen.

Also outstanding, small: build button 2 on GPIO2 when a second switch is on hand.

## Blocked on
Nothing. Phases 1 and 2 both fully verified, including their physical pass gates.

### RESOLVED — web app couldn't find the board over BLE
Symptom: Chrome's device chooser scanned forever, found nothing, while the board's
serial insisted it was advertising.
**Cause: BLE advertising payload overflow.** The advertisement is capped at 31
bytes; flags (3) + a 128-bit service UUID (18) + the name `IR-Remote` (11) = 32.
The name was silently dropped/truncated, so the app's `filters: [{name: ...}]`
could never match. Nothing was wrong with the Mac or the hardware.
**Fix, both sides:** firmware now puts the UUID in the advertisement and the name
in the *scan response* (its own 31 bytes) via explicit `NimBLEAdvertisementData`;
the app filters on `services: [SERVICE_UUID]` instead of the name.
**Lesson:** a 128-bit UUID leaves almost no room in an advertisement — put the name
in the scan response and filter by service UUID, never by name.

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

### ⛔ KiCad MCP gotcha — every save silently destroys board connectivity

Applies to the PCB work in `hardware/` (kicad-mcp `kicad-mixelpixx`, swig backend).

The MCP's board writer emits pad nets as `(net "GND")` — **no net index** — and
omits the top-level net declaration table entirely. KiCad **opens the file
without complaining**, which is exactly what makes this dangerous: every pad is
netless, so DRC reports a suspiciously clean board while being unable to detect
a single short, the ratsnest is empty, and gerbers would be meaningless.
`kicad-cli sch upgrade` does not fix it.

**The rule — no exceptions:**
```
<any kicad-mcp edit> → save_project → python3 hardware/fix-nets.py → kicad-cli pcb drc
```
`hardware/fix-nets.py` repairs it and is idempotent.

Two-line check when unsure:
```
grep -cE '^\t\(net [0-9]+ ' hardware/ir-remote.kicad_pcb   # must be > 0
grep -cE '^\t\t\t\(net "'   hardware/ir-remote.kicad_pcb   # must be 0
```

**Second-order trap:** because the script edits the file on disk, the MCP's next
auto-save is *refused* (mtime guard, warns `diskChangedExternally`) and your
edits then exist only in server memory until they're lost. Call `open_project`
after running the script and before further MCP edits.

Full detail, plus the freerouting and antenna-keepout traps, in
`hardware/README.md`.

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
  The block briefly returned mid-session — the Mac had been auto-joining a bad
  network — which is why NimBLE-Arduino 2.5.0 and ArduinoJson 7.4.3 were installed
  from GitHub release tags rather than `arduino-cli lib install`. Network since
  fixed; `arduino.cc` verified reachable again. GitHub and Espressif hosts were
  never affected. **Root cause was the network, never the toolchain** — if
  downloads start failing again, check the Wi-Fi before touching arduino-cli.
- **Library install fallback** (when `arduino.cc` is blocked): download the release
  zip from GitHub into `~/Documents/Arduino/libraries/<LibName>`. Verify with
  `grep '^version' <LibName>/library.properties`.
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
