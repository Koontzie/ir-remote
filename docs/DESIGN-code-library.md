# Design — Code Library + Identify Mode (Phase 5)

**Why:** Tyler's AV work involves projectors and monitors from many brands
(Samsung, LG, NEC, +more), often unlabeled or unreachable. Today that means
digging through menus and trying every brand. This phase gives the remote a
built-in code library with dropdowns, and an **Identify mode** that sweeps
power codes across all brands until the device reacts — the Flipper Zero
universal-remote trick, on our hardware.

## Data sources (fetched 2026-07-19, in repo)

| File | Entries | What |
|---|---|---|
| `data/source/tv.ir` | 613 (295 power) | Flipper Unleashed universal TV list |
| `data/source/projectors.ir` | 302 (138 power) | Flipper Unleashed universal projector list |
| `data/tv.json`, `data/projectors.json` | converted | IRremoteESP8266-ready |

- Converter: `tools/flipper_ir_convert.py`. Flipper stores LSB-first bytes;
  IRremoteESP8266 wants MSB-first codes — each byte is bit-reversed, then
  frames assembled per protocol (NEC: addr,~addr,cmd,~cmd; Samsung32:
  addr,addr,cmd,~cmd; NECext: addr16,cmd,~cmd; SIRC: addr<<7|cmd).
- **Validated:** converter reproduces `0xE0E040BF` (SAMSUNG power) from
  Flipper's entry — the exact code physically verified on the bench TV. ✅
- Protocol coverage: NEC+NECext+Samsung32 ≈ 85% of parsed entries; SONY(SIRC),
  RC5, RC6 converted but **unverified against hardware**; Kaseikyo/RCA/
  Pioneer/NEC42/RC5X marked TODO (23 entries); ~26% of entries are RAW timing
  arrays (many projectors!) — see BLE note below.
- **Brand-attributed browsing DB** (pick brand → device → function) comes from
  Flipper-IRDB proper (`Lucaslhm/Flipper-IRDB`). **Decision 2026-07-19: scrape
  the full AV-relevant library, not a brand subset** — measured sizes make it
  trivial: Projectors 1.4MB/126 files/54 brands, TVs 2.6MB/397 files, Monitors
  64KB, plus AV Receivers, SoundBars, Cable Boxes, Blu-Ray, DVD ≈ **<10MB of
  source text total** (skip `_Converted_`, 85MB of other-ecosystem exports; skip
  ACs — stateful protocols, different beast; skip Toys/Fans/LEDs etc.).
  Output: one JSON shard per brand (`data/db/projectors/nec.json`), plus a
  small `data/db/index.json` (categories → brands → file, counts). App fetches
  the index at load and brand shards on demand — Pages serves it all statically.
- **Universal lists have NO input/source codes** (verified: power/vol/mute only).
  The two functions Tyler's AV work needs most are **power on/off and input
  switching** — so the brand-DB scrape must extract: `Power`, discrete
  `Power_on`/`Power_off`, `Source`/`Input`, discrete `HDMI1/2/...`,
  `VGA`/`Comp`, plus vol/mute as gravy. Index the scraped DB by
  (protocol, address) to power the keymap-unlock step below.

## Feature 1 — Library dropdowns in the app

Replace/augment the raw hex form: Device type → Brand → Function dropdowns,
filled from `data/*.json` (static fetch, same GitHub Pages origin). Selecting a
function fills protocol/code/bits; Save-to-slot and Test work as today. Custom
hex entry stays for codes not in the DB.

## Feature 2 — Identify mode (the brand-hunt killer)

**UX (app-driven, phone connected):**
1. Pick device type (Projector / TV / Monitor) → optional brand guess to try
   that brand's codes first.
2. Aim remote. Hit **START**. App streams power codes over BLE one at a time,
   ~400ms apart (~100ms IR transmit + gap), progress bar + current index shown.
3. Device reacts → user hits **STOP**. Reaction lags human perception, so the
   app shows the **last 5 codes sent** as individual re-send buttons —
   single-step them to pinpoint the exact one.
4. "It's this one" → name it, save to a slot, and (later) log it to a site
   inventory list.
5. **Keymap unlock:** all functions on one remote share the protocol + address;
   only the command byte differs. On a hit, the app searches the brand DB for
   entries with the same (protocol, address) and surfaces that device's full
   keymap — Source/Input/HDMI, discrete power, volume — as one-tap test
   buttons. Inputs are never swept for; they're unlocked by the power hit.
   (Device is now on, so input changes give visible confirmation.)

Sweep sizing from real data: projectors = 51 deduped parsed power codes
(~20s sweep); TVs = 130 (~52s). RAW entries add 34/156 more once chunked
writes exist. Sweep list ships as a dedicated `data/sweep-{type}.json`,
deduped by (proto,code), NEC-family first (highest hit rate).

**Firmware additions:**
- New protocols in the send switch: SONY, RC5, RC6 (IRremoteESP8266 has them
  all natively — small map extension).
- `trigger` accepts direct send `{"proto":"NEC","code":"0x...","bits":32}`
  (no slot round-trip) — the sweep uses this; slots stay for the buttons.
- Status notify per send keeps app and firmware in lockstep during sweeps.

**BLE payload wrinkle (RAW codes):** raw timing arrays are 100–250 uint16s =
up to ~1KB, far over the 23-byte default ATT MTU. NimBLE negotiates up to 517;
Web Bluetooth writes cap at 512 bytes. Plan: request MTU 517 + chunked
`config`-style transfer (seq-numbered fragments, reassemble in firmware).
Defer RAW to a second pass — parsed codes alone give 51 projector +
130 TV codes, which is already better than the menu-diving status quo.

**Discrete ON/OFF (AV gold):** many projectors (esp. NEC protocol families)
have *discrete* power-on and power-off codes, not just toggle. When the
brand DB lands, surface these distinctly — "shut down every projector in the
room without toggling the off ones back on" is a real workflow win.

## Feature 3 — Favorites (Tyler's work fleet)

The library is the ocean; Favorites is the toolbox. A named list of the codes
Tyler actually uses at work, built up as he goes:

- **Add from anywhere:** an Identify hit, a library browse, or the keymap-unlock
  view — every code row gets a ☆. Favorites are named by the user
  ("Shop 3 NEC proj — HDMI2"), optionally grouped by site/room.
- **Front and center:** favorites render as big tap-pads at the top of the app,
  above the slot editor — the daily-driver screen. Library browsing is the
  occasional path.
- **Storage:** `localStorage` (persists in Bluefy and Chrome independently) +
  one-tap **export/import as JSON** (share codes between phone and desktop, back
  up, or hand a coworker your entire site kit as a text file). Keep the format
  human-readable.
- Slots (the 5 physical-button bindings) are unchanged — a favorite can be
  pushed to a slot, which is how a work device ends up on a hardware button.

## Standalone sweep (later, pairs with Phase 4)

Long-press button 2 = sweep projector power list from flash (LittleFS or
PROGMEM, no phone needed); short-press again = stop. Requires the sweep list
baked into firmware at build time. Deferred until battery/deep-sleep phase
settles the power/wake architecture.

## Open items

- [ ] Tyler: brand/device list from work → scopes the Flipper-IRDB scrape.
- [ ] Verify RC5/RC6/SIRC conversions against a real Philips/Sony device.
- [ ] RAW chunked-write protocol (unlocks 190 more codes incl. many projectors).
- [ ] Site inventory: identified devices → named entries (JSON export?).
