# CC Brief — Phase 1: flash the IR transmit test (ESP32-S3)

You are working in `~/dev/ir-remote`. Read `PLAN.md` and `STATUS.md` first.

Hardware state (already done by Tyler, do not re-verify):
- Salvaged IR LED wired directly: GPIO4 → 150Ω → IR LED → GND (no transistor, Phase 1 low-power proof)
- ESP32-S3 devkit plugged into the Mac via USB

Your job: get `firmware/phase1_ir_test/phase1_ir_test.ino` compiled, flashed, and
confirmed running. **This brief has 6 steps. Do not stop early; do not continue past step 6.**

## Step 1 — Toolchain
Check for `arduino-cli` (`which arduino-cli`); if missing, `brew install arduino-cli`.

## Step 2 — ESP32 core + library
```
arduino-cli config init --overwrite --additional-urls https://espressif.github.io/arduino-esp32/package_esp32_index.json
arduino-cli core update-index
arduino-cli core install esp32:esp32
arduino-cli lib install IRremoteESP8266
```
Verify the installed esp32 core is 3.x and IRremoteESP8266 is ≥ 2.9.0 (S3 support landed in 2.9.0).

## Step 3 — Find the board
`ls /dev/cu.usbmodem* /dev/cu.usbserial*` — pick the port that appears/disappears
with the board plugged in if ambiguous (ask Tyler rather than guessing between two ports).

## Step 4 — Compile + flash
```
arduino-cli compile --fqbn esp32:esp32:esp32s3:CDCOnBoot=cdc firmware/phase1_ir_test
arduino-cli upload -p <PORT> --fqbn esp32:esp32:esp32s3:CDCOnBoot=cdc firmware/phase1_ir_test
```
Known gotchas:
- If upload fails to connect, tell Tyler to hold BOOT, tap RESET, release BOOT, then retry.
- `CDCOnBoot=cdc` is required for Serial over the S3's native USB port. If Tyler is on
  the UART port instead and gets no output, retry without the flag.

## Step 5 — Verify
`arduino-cli monitor -p <PORT> -c baudrate=115200`
Success = `sent` printed every ~3 seconds. Capture ~15s of output.
Then STOP and tell Tyler to check the LED with his phone's selfie camera (purple flashes).
The sketch sends Samsung TV power `0xE0E040BF` (`sendSAMSUNG`) — the test target is
the Samsung TV in the room. Final pass gate: Tyler points the LED at the TV and it
toggles power. ⚠️ Warn Tyler before he tests: it fires every 3s, so the TV will keep
toggling on/off until he unplugs the board or points it away.

## Step 6 — Chapter close
Update `STATUS.md`: Phase 1 firmware flashed and verified (or blocked on X).
Next step becomes "Phase 2: BLE GATT + Bluefy web app". Do NOT start Phase 2.
Do not git-init or commit unless Tyler asks.

END OF BRIEF
