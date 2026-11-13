# IR-Remote — STATUS

**Status:** Active
**Updated:** 2026-08-10

BLE-programmable universal IR remote. Seeed XIAO ESP32-C3 rev-2 perf board:
battery → charger → boost → power switch → C3, three illuminated buttons, two
IR LEDs. Firmware in `firmware/remote_ble/`, web app in `app/`. Full history and
rationale live in `docs/DEVLOG.md`; hardware in `hardware/` (`WIRING.md` and
`DESIGN-c3-board.md` are canonical for the current board).

## Where it's at
- Phases 1 / 2 / 2.5 / 3 complete; perf-board rebuild and Phase 5 Sitting A
  complete. (See `docs/DEVLOG.md`.)
- **XIAO C3 board bring-up (2026-08-10):** unmodified firmware compiles and
  flashes for `esp32:esp32:XIAO_ESP32C3`; boot serial verified (banner, buttons
  GPIO3/5/6 → slots 1–3, BLE advertising, NVS slot 1 = SAMSUNG). Button-press
  and TV-toggle confirmation still pending on the bench.
- **Button-LED signal module (2026-08-10):** non-blocking LEDC state machine
  (`ledInit`/`ledTick`/`ledSignal`) added to `remote_ble.ino` — boot cascade,
  25 % idle, press flash, sent double-pulse, empty blink, connect breathe, sweep
  chase. Compiles, flashes, boots clean (LEDC attached, no WARN; BLE still up).
  IR carrier is bit-banged (no LEDC/RMT), so no peripheral contention.

## Next step
Tyler's bench confirmation of the parts software can't see:
1. Press each button — `[btn] GPIOn pressed -> slot N` for 3/5/6, slot 1 toggles
   the TV. (A pin that never registers = wire on the wrong pin; fix the map to
   the meter, per the July GPIO5/6 incident.)
2. Watch the seven LED patterns fire.
3. Confirm IR range and BLE stability are unchanged with PWM running.
4. Meter the idle current at 25 % rings (estimate: ~26 mA @ 5 V rail /
   ~41–45 mA at the cell — matches the ~45 mA design figure).

Then Step 6 close-out is done and the board moves to enclosure work (the 12 mm
vs 16 mm button-hole rescale noted in `DESIGN-c3-board.md`).

## Blocked on
Nothing blocking. All remaining items need physical access to the board/TV/meter
— they are Tyler's to confirm, not code work.

## Notes
- FQBN is `esp32:esp32:XIAO_ESP32C3` — **not** the old S3 target.
- No deep sleep, no wake code — the power switch on the boost EN pin is the whole
  power story. Any EXT1/sleep reference is stale; do not implement it.
- Strapping pins GPIO2/8/9 (XIAO D0/D8/D9) are never assigned.
- C3 native-USB CDC buffers ~256 B while no host is attached, dropping the boot
  tail. To read a full boot: hard-reset, then attach the monitor within the 2 s
  startup delay so it streams live.
- Idle ring brightness is the single constant `kRingIdleDuty` in
  `remote_ble.ino` — the one place to dim if runtime disappoints.
