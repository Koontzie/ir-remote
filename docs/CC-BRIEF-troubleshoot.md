# CC Brief — Perf-board troubleshooting session (interactive)

Working dir `~/dev/ir-remote`. Read `STATUS.md` first — the perf-board section
has the full debug history, including the transistor E/C reversal found on
2026-07-21 and the measurements that identified it.

**This is an interactive bench session, not a batch job.** Tyler is at the
board with a multimeter. Your job: keep a serial monitor running, tell him
exactly what to probe, interpret the numbers, and stop when the fault is found
or the trail goes cold. **6 steps. Do not skip ahead; wait for his readings.**

## Since the last session
- Tyler suspects he may have **shorted something** during rework — treat this
  as unknown-state hardware, not a known-good board with one fault.
- Firmware `remote_ble.ino` was edited (uncommitted): button 1 = **GPIO6**,
  button 2 = GPIO2, **button 3 = GPIO7 (new)**. Slot N per button N.
- The transistor was pulled and diode-tested out of circuit: both junctions
  healthy, 0.65 V leg = Emitter, 0.64 V leg = Collector. **Transistor is good.**
- Known prior fault, may or may not still be present: 33 Ω was once wired in
  the capacitor's branch rather than the LED path.

## Step 1 — Power-off safety sweep (do this BEFORE any power)
⚠️ Board unplugged. Have Tyler meter, and report each:
- 5V rail ↔ GND: must be **open / high kΩ**, NOT ~0 Ω. A short here is the
  "did I short something" scenario and everything else waits on it.
- 3V3 ↔ GND: same expectation.
- GPIO4 ↔ GND and GPIO4 ↔ 5V: should not be near 0 Ω.
- Continuity along the intended LED path: 5V → 33 Ω → LED1(+) … LED2(−) →
  transistor collector; and separately transistor emitter → GND.
- **Confirm the 33 Ω is in the LED path and NOT in the cap's branch** — this
  was a real prior fault. The cap should connect rail-to-rail with plain wire.
If a short is found: stop, isolate it (lift one leg at a time), fix, re-verify.

## Step 2 — Serial monitor up
Find the port (`arduino-cli board list` — it drifts). Compile + upload
`firmware/remote_ble` with the FQBN in STATUS.md, then keep a monitor running
for the rest of the session (`sleep N | arduino-cli monitor ...` pattern; note
the stdin gotcha in STATUS.md). Confirm boot prints all three button lines:
GPIO6→1, GPIO2→2, GPIO7→3. Report anything unexpected (brownouts, resets,
guru meditations).

## Step 3 — Button verification
Have Tyler press each wired button. Expect `[btn] GPIOn pressed -> slot n`.
Slot 3 is unprogrammed, so button 3 should log an empty-slot error, not
silence. A button that fires once at boot then never again = the 4-leg
tactile "internally-joined pair" mistake — say so if you see that signature.

## Step 4 — Emitter path under power
Flash the steady-drive diagnostic (scratchpad `gpio4_on`, or regenerate:
GPIO4 HIGH constantly) and have Tyler meter, reporting each:
- Collector → Emitter: want **~0.2 V** (3+ V means E/C still reversed)
- Across the 33 Ω: want **~3.3 V** (≈100 mA). Low volts = low current.
- Across the LED(s): ~1.2 V per LED.
Interpret against STATUS.md's recorded fault signature. ⚠️ Do not leave the
steady-drive sketch running long if the 33 Ω is a 1/8 W part.

## Step 5 — Restore and range-test
Reflash `firmware/remote_ble`. Tyler fires slot 1 from a button and from the
Bluefy app, walking backwards from the TV. **Pass gate: 20–30 ft.** Inches
means the emitter path is still wrong — go back to step 4 rather than
guessing.

## Step 6 — Chapter close
Commit the pending firmware edits (GPIO6/GPIO7 button map) and any docs.
Update STATUS.md with what was actually found and fixed this session, in the
existing RESOLVED-section style — including the "33 Ω in the cap branch
instead of the LED path" lesson if it's not already recorded (a resistor can
be present on the board and still not be in the current path; continuity to
the right *node* is what matters, not that the part exists).

Do NOT start the code-library / search work in this session — that's
`docs/CC-BRIEF-phase5.md`, and `docs/DESIGN-code-library.md` now carries
Tyler's new requirements (search-first UI, discrete power-on preference,
generic per-brand blanket codes, show-the-code-sent in the app).

END OF BRIEF
