# CC Brief — Phase 2: BLE GATT + programmable buttons via web app

Working dir `~/dev/ir-remote`. Read `PLAN.md` and `STATUS.md` first. Phase 1 is
complete (IR path proven against the Samsung TV). **This brief has 7 steps. Do not
stop early; do not continue past step 7.**

## Step 1 — Toolchain cleanup (arduino.cc is reachable again)
Restore `~/Library/Arduino15/package_esp32_index.json` from the `.bak`, then run
`arduino-cli core update-index` and `arduino-cli lib update-index`. Verify
`arduino-cli core install esp32:esp32` succeeds cleanly (dfu-util no longer needs
the patch). Confirm IRremoteESP8266 still resolves at ≥ 2.9.0. Remove the `.bak`
once verified. Update the stale "arduino.cc is blocked" note in STATUS.md.

## Step 2 — Make it a repo
`git init`, add a `.gitignore` (build artifacts, `.DS_Store`), initial commit of
everything (plan, briefs, firmware, STATUS). Then ASK TYLER to create
`Koontzie/ir-remote` on GitHub (public — GitHub Pages on a free account requires
it; repo contains no secrets by design) and push. Don't create the remote repo
yourself unless `gh` is installed and Tyler says go.

## Step 3 — Firmware: `firmware/remote_ble/remote_ble.ino`
New sketch, keeps Phase 1's IR send (GPIO4, IRremoteESP8266). Add:
- **NimBLE-Arduino** (install via `arduino-cli lib install NimBLE-Arduino`)
- One GATT service, three characteristics (128-bit custom UUIDs, generate once
  and hardcode):
  - `config` (WRITE): JSON `{"slot":1,"proto":"SAMSUNG","code":"0xE0E040BF","bits":32}`
    → persist to NVS via Preferences. Slots 1–5. Protocols: NEC, SAMSUNG, SONY.
  - `trigger` (WRITE): JSON `{"slot":1}` → load slot from NVS, send IR.
  - `status` (NOTIFY): short ack strings ("saved:1", "sent:1", "err:...").
- Serial-log every BLE event at 115200. Device name: `IR-Remote`.
- Buttons are Phase 3 — do NOT wire GPIO5/6 handling yet.

## Step 4 — Flash + smoke test
Compile/upload with the known-good FQBN (`esp32:esp32:esp32s3:CDCOnBoot=cdc`).
⚠️ Port number drifts between replugs — `arduino-cli board list` first.
Verify over serial: boots, advertises, no crash loop.

## Step 5 — Web app: `app/index.html`
Single self-contained HTML file (vanilla JS, no build step): Connect button
(Web Bluetooth, filter by device name), editor for slots 1–5 (protocol dropdown,
hex code, bits), Save → writes `config`, Test → writes `trigger`, status line fed
by notifications. Mobile-friendly layout. Pre-fill slot 1 with the Samsung power
code.

## Step 6 — End-to-end verification with Tyler
Desktop Chrome on the Mac supports Web Bluetooth, and `http://localhost` counts as
a secure context — so BEFORE any GitHub Pages setup: `python3 -m http.server` in
`app/`, have Tyler open `localhost:8000` in Chrome, connect, save slot 1, hit
Test with the LED aimed at the TV (inches away — no transistor yet).
**Pass gate: TV toggles from a button in the browser.**
iPhone/Bluefy comes after the repo is on GitHub Pages — note it as follow-up if
Pages isn't set up yet; don't block on it.

## Step 7 — Chapter close
Commit. Update STATUS.md: what passed, exact UUIDs, how to run the local server,
next step = "Bluefy on iPhone via GitHub Pages, then Phase 3 buttons + NPN stage".
STOP here.

END OF BRIEF
