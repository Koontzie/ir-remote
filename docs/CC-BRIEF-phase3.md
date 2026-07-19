# CC Brief — Phase 3: NPN driver stage + physical buttons

Working dir `~/dev/ir-remote`. Read `PLAN.md` and `STATUS.md` first. Phases 1–2.5
are complete (iPhone → Bluefy → BLE → IR → TV all verified). **This brief has 6
steps. Do not stop early; do not continue past step 6.** Steps 1 and 4 are Tyler's
bench work — your job there is to guide, wait, and verify, not to rush past.

Decisions already made with Tyler:
- Button N → slot N, fixed mapping (no config surface for it).
- Button presses ALSO notify `pressed:N` on the existing status characteristic.
- PLAN.md was updated after Phase 2 but is uncommitted — fold it into this
  chapter's first commit.

## Step 1 — Hardware: NPN driver stage (Tyler at the bench, you guide)
Rework the LED drive. New circuit, fed from the devkit's **5V/VBUS pin**:
```
5V ──33Ω──► IR LED1(+)─(–) [──► IR LED2(+)─(–) if Tyler's 2nd LED tested as IR] ──► COLLECTOR
GPIO4 ──1kΩ──► BASE          EMITTER ──► GND
```
~65–100mA pulses vs the old 13mA. Ask Tyler which transistor he's using and
confirm its pinout (E/B/C order differs: 2N2222 vs S8050 vs salvage) BEFORE he
wires it. ⚠️ Board unplugged while rewiring — and remember this project's history:
keep everything clear of GPIO0.
Verify: reflash nothing yet — existing `remote_ble` firmware already drives GPIO4.
Tyler tests from the app; expected result is the SAME behavior with much longer
range (aim for across-the-room). If range got worse, transistor is miswired or
LED polarity flipped.

## Step 2 — Firmware: buttons in `firmware/remote_ble/remote_ble.ino`
- Button 1 → GPIO5, Button 2 → GPIO6. `INPUT_PULLUP`, wired pin→button→GND,
  pressed = LOW. (R13-507 buttons, no polarity.)
- Debounce ~30ms, fire on press (not release), no repeat while held.
- Press → load slot N from NVS → send IR → notify `pressed:N` then `sent:N` if
  a client is connected. Empty slot → notify `err:empty:N`, log to serial.
- Keep BLE behavior otherwise untouched — do not regenerate UUIDs.

## Step 3 — Flash + serial smoke test
Known-good FQBN; check the port with `arduino-cli board list` first (it drifts).
Verify over serial: boot clean, presses log with correct slot numbers, no
chatter (debounce working), BLE still advertises.

## Step 4 — End-to-end pass gate (Tyler at the bench)
Tyler wires the two arcade buttons (jumpers clipped/soldered to the lugs).
**Pass gate: physical button 1 toggles the TV from across the room, and the
Bluefy app shows `pressed:1` while connected.** Also verify buttons work with NO
phone connected — the remote must be standalone.

## Step 5 — App: show button events
Small addition to `app/index.html`: status line already receives notifications —
surface `pressed:N` distinctly (e.g. flash the matching slot row). No redesign.

## Step 6 — Chapter close
Commit everything (including the pending PLAN.md edit) and push. Update
STATUS.md: circuit as-built (transistor part number, resistor values, one or two
LEDs), pass-gate results, next step = "Phase 4: battery + deep sleep (EXT1 wake
on GPIO5/6)". Refresh PLAN.md's roadmap to mark Phase 3 done. STOP here.

END OF BRIEF
