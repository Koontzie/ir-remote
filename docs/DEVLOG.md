# IR-REMOTE — STATUS

**Status:** Active
**Updated:** 2026-07-26

## Where it's at
Phase 0 (salvage) done. **Phases 1, 2, 2.5 and 3 all COMPLETE** (2026-07-19).
Perf-board rebuild COMPLETE (2026-07-26). **Phase 5 Sitting A COMPLETE** (2026-07-26).

### Perf-board rebuild — ✅ COMPLETE (2026-07-26)
Circuit rebuilt from breadboard onto a perf board. Still USB power (boost/battery
not installed). **Three physical buttons now built: GPIO5 → slot 1, GPIO2 → slot 2,
GPIO7 → slot 3.** Bench session 2026-07-26 closed out every open fault from the
2026-07-21 stop; the board is a working across-the-room remote again.

- ✅ **IR range restored to across-the-room** — the pass gate is met. The
  2026-07-21 root cause (transistor E/C reversed, C→E measuring 3.4 V and only
  ~12 mA through the 33 Ω) is **fixed**: the 2N2222 was pulled, diode-tested good
  out of circuit (0.65 V leg = Emitter, 0.64 V leg = Collector), and reinstalled in
  the correct orientation. Verified 2026-07-26 with the `gpio4_on` steady-drive
  diagnostic: **both IR LEDs glow bright on a phone camera** (full ~100 mA), and a
  live walk-back range test toggled the TV at good distance. Both IR LEDs remain in
  the series loop.
- ✅ **Button 1 pin corrected: it's GPIO5, not GPIO6.** The uncommitted firmware
  had remapped button 1 to GPIO6 (on a since-disproven belief that pin 6 was wired).
  Boot printed `[btn] GPIO6 -> slot 1` cleanly, but **no press ever registered** —
  nothing is physically connected to pin 6; the wire is on GPIO5, button 1's
  original Phase 3 pin. Firmware reverted to GPIO5. All three buttons then verified
  on serial: `GPIO5 pressed -> slot 1 -> [ir] SAMSUNG 0xE0E040BF -> sent:1`, and
  buttons 2/3 correctly log `err:empty:N` for their unprogrammed slots. Clean single
  events, no chatter, no stuck-pressed signature.
  **Lesson:** a firmware pin map that prints clean at boot proves nothing about the
  wiring — a `pinMode`/label on an unconnected pin is silent, not an error. Confirm
  a button by a *press* event, not by the boot banner.
- ✅ **The "did I short something during rework" scare was transient.** A button's
  metal prong had briefly touched the board while powered. Power-off safety sweep
  (2026-07-26) came back clean: 5V↔GND and 3V3↔GND both open (the wandering
  MΩ/negative reading on the ohmmeter is the bulk cap charging, **not** a short — a
  real short sits pinned at single-digit Ω); no button line shorted to GND or 5V;
  LED path continuous with the 33 Ω correctly placed. No lasting damage. Across the
  whole session the serial showed **zero resets/brownouts/guru-meditations**.
- ✅ **33 Ω confirmed in the LED path, not the cap's branch.** The prior fault
  (33 Ω once wired in series with the bulk cap instead of the LED string) is **not**
  present — metered 5V→33Ω→LED1(+), and the cap connects rail-to-rail with plain
  wire. **Lesson:** a resistor can be physically present on the board and still not
  be in the current path; continuity to the right *node* is what matters, not that
  the part exists. (See `hardware/WIRING.md`, which encodes this.)
- ⚠️ **Intermittent BLE app disconnect — not a hardware fault, not chased down.**
  Bluefy dropped the link a couple of times mid-session but would not reproduce on
  demand; when connected, the full chain works (`config write -> nvs saved:1`,
  `trigger`/button -> `sent:1`). No board reset accompanies the drops, so it's a
  flaky BLE *link* (Web Bluetooth / Bluefy connection stability), not power or the
  IR path. Left as a known minor annoyance.
- ✅ **The "goes to protect" red light is solved and benign — it's capacitor
  inrush.** Tyler added a bulk/decoupling cap **across the 5V–GND rail, before the
  LED** (2026-07-21). On hot-plug the cap draws an inrush gulp that lights a
  charge/current LED, which fades as the cap charges — hence "on at plug-in, goes
  away on its own." The cap is **correctly placed and worth keeping** — it steadies
  the rail during the 64mA LED pulses. It is NOT in the 38kHz modulation path
  (GPIO4→base→transistor→LED), so it does **not** affect IR range. Chip probed
  healthy throughout (ESP32-S3 rev v0.2, 8MB PSRAM, MAC OK).
- Diagnostic sketches are regenerated per-session in the scratchpad (not the repo);
  `gpio4_on` (GPIO4 held HIGH for steady-drive metering / LED camera check) is the
  one used this session. ⚠️ It runs ~100 mA through the 33 Ω continuously — if that
  resistor is a 1/8 W part, don't leave the steady-drive sketch running long.


### Phase 5 — Code Library — Sitting A ✅ COMPLETE (2026-07-26)
Steps 1–4 of `docs/CC-BRIEF-phase5.md` (spec: `docs/DESIGN-code-library.md`).
Sitting B (steps 5–8: firmware direct-send + RC5/RC6/SONY, Identify mode,
Favorites) is a **separate session — not started**.

- **Scrape + convert (steps 1–2).** Re-scraped `Lucaslhm/Flipper-IRDB` fresh
  (shallow clone to a temp dir, not the repo) and hardened
  `tools/flipper_ir_convert.py`. New this sitting, per the design doc's
  field-feedback section:
    - **Search index** (`data/db/search.json`, 61 KB, 317 brand records): one
      compact record per brand (brand + category + canonical functions + model
      strings) so the app can search-first. Shards still lazy-load on selection.
    - **Generic / blanket codes.** Model-spread is measured before dedupe; a
      canonical code shared across ≥3 models in a brand is flagged `generic`
      (with `nmodels`). These are the universal-remote sweet spot. E.g. Samsung
      TV `0xE0E040BF` = power_toggle across 36 models.
    - **Sweep ordering** now prefers `power_on` before toggle before `power_off`
      (an already-on device shouldn't flicker off mid-sweep).
  DB totals: 8 categories, 317 brands, ~13.8K codes. All sanity gates pass
  (Samsung `0xE0E040BF` present; NEC projector discrete on/off; generics
  promoted; search index indexes Samsung TVs).
- **App (step 3), `app/index.html`, still one file / vanilla JS.**
    - **Search-first** is the front door (live, debounced, ranked brand hits);
      the Category→Brand→Model dropdowns are kept as a collapsible fallback.
    - Brand view shows **generic/blanket codes at the top**, then all codes
      ordered with **discrete power_on/power_off before power_toggle** (toggle is
      tagged "fallback"). Assigning a code binds the **whole brand keymap** to a
      slot; manual hex entry retained.
    - **Show-the-code-that-was-sent:** a physical press now reports
      `button N sent → <friendly name> (PROTO CODE)` in the status bar, and slot
      readouts are named when the code came from the library.
  Verified end-to-end in desktop Chrome (search → open Samsung TVs → assign
  `0xE0E040BF` → slot 1 named readout); no app JS errors.
- **Bench pass gate (step 4) MET:** a library-picked Samsung power code, saved
  from the app, toggles the bench TV at full distance.
- ⚠️ **Known follow-up — intermittent BLE disconnect.** Bluefy/Web-Bluetooth
  link drops with `reason 520` (supervision timeout); when congested, an app
  Save drags and times out mid-write, which *looks* like "save broke it." Serial
  proved the stored code + IR transmit are always correct (`SAMSUNG 0xE0E040BF`
  before and after Save) — this is a link-stability issue, **not** data or IR.
  Good candidate to investigate in Sitting B alongside the firmware work.
- Note: during enclosure fitting a button prong shorted the board twice (transient
  each time); reflash + clean boot every time. Heat-shrink insulation added.

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
  (Perf-board rebuild moved button 1 to **GPIO6** — see the perf-board section below.)

**Pass-gate results:**
- ✅ **Range: ~5ft → 20–30ft.** The single biggest win of the phase.
- ✅ Physical button 1 toggles the TV from across the room.
- ✅ **Standalone** — works with Bluefy fully disconnected. It is a real remote,
  not a BLE accessory.
- ✅ Debounce verified clean at millisecond resolution: one press → exactly one
  event, no chatter. (A Samsung frame takes **109ms** to transmit — measured.)
- ✅ `pressed:1` notifies the app and flashes the matching slot row.
- ⏭️ **Button 2 not built** — no second button on hand. (Earlier note claimed GPIO6
  wasn't broken out on this devkit and moved button 2 to GPIO2; that claim was
  **wrong** — GPIO6 is broken out and works, see perf-board section. GPIO2 remains a
  fine alternate for button 2.)

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
cd app && python3 -m http.server 8000
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
**Phase 5 Sitting B** (`docs/CC-BRIEF-phase5.md` steps 5–8) — a separate session:
firmware direct-send `{"proto","code","bits"}` + RC5/RC6/SONY in the send switch;
Identify mode (sweep power codes ~400ms apart → last-5 re-send → keymap unlock);
Favorites (☆ rows, localStorage + JSON export/import, push-to-slot). The sweep
lists (`data/sweep-*.json`) and generic/search data from Sitting A already feed it.
- While in there, investigate the **intermittent BLE disconnect** (`reason 520`
  supervision timeout — see the Phase 5 Sitting A note). Link stability, not data.

Perf-board rebuild and Phase 5 Sitting A are both done (2026-07-26).

Then **Phase 4 — battery + deep sleep.** EXT1 wake on the button pins, now
**GPIO5 + GPIO2 + GPIO7** on the perf board (all RTC-capable on the S3, which EXT1
requires). Wake → send → sleep.

Open questions carried in from PLAN.md's tripwires: the devkit's AMS1117 LDO wants
~4.4V+ in, and the onboard USB-UART chip leaks mA even in deep sleep — so this
likely means 2×AA + a boost converter, or moving to a bare WROOM module. The
circuit currently runs off **5V/VBUS, which only exists while USB is plugged in**;
battery power changes that rail and the 33Ω value should be rechecked against
whatever new supply voltage is chosen.

Buttons 1–3 are now built (GPIO5/GPIO2/GPIO7); slots 2 and 3 are unprogrammed
(they log `err:empty:N` until a code is written to them).

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

### KiCad 10 changed the board net format — don't "fix" it

Applies to the PCB work in `hardware/`. **This entry exists to stop someone
(including me, again) from repairing a non-bug.**

KiCad 10 (board format `20260206`) references nets **by name**:
```
(net "GND")        <- pads, tracks and vias, KiCad 10
```
The numeric index and the top-level `(net N "name")` declaration table that
KiCad ≤ 9 used are **gone**. `kicad-cli --save-board` — KiCad's own serialiser —
writes exactly this, and DRC resolves it correctly (`Pad 5 [BTN1]`,
`Track [BTN1]`).

I originally mistook this for a kicad-mcp bug, on the strength of
`grep '(net [0-9]'` returning zero, and wrote a script to "repair" it. The
script converted the board to the legacy format. KiCad still accepts that for
backward compatibility, so nothing visibly broke — which is what made the wrong
diagnosis look confirmed. It was deleted.

**If a net grep looks wrong, check what format this KiCad version writes before
concluding a tool is broken.** Verify with:
```
kicad-cli pcb drc --output /tmp/drc.rpt hardware/ir-remote.kicad_pcb
grep -A3 unconnected /tmp/drc.rpt      # nets appear as [GND], [BTN1] etc. when healthy
```

**Real MCP trap that does apply:** editing the board file outside the MCP makes
its next auto-save *refuse* (mtime guard, `diskChangedExternally`), so your edits
live only in server memory until they're lost. Call `open_project` to re-sync
before further MCP edits.

Freerouting and antenna-keepout traps are in `hardware/README.md`.

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
