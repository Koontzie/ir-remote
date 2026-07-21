# CC Brief — Phase 5: Code Library + Identify Mode + Favorites

Working dir `~/dev/ir-remote`. Read `PLAN.md`, `STATUS.md`, and
`docs/DESIGN-code-library.md` first — the design doc is the spec; this brief is
the execution order. **This brief has 8 steps in TWO SITTINGS. Sitting A =
steps 1–4, Sitting B = steps 5–8. STOP at the end of each sitting, commit, and
update STATUS.md — the sitting boundary is a real chapter close, not a
formality.** Do not continue past step 8. Phase 4 (battery) is separate; don't
touch power/sleep code.

Already in the repo (done in the Cowork session, uncommitted): `data/tv.json`,
`data/projectors.json`, `data/source/*.ir`, `tools/flipper_ir_convert.py`,
`docs/DESIGN-code-library.md`. The converter's math is validated (reproduces
the bench-verified `0xE0E040BF`), but it's a prototype — harden it in step 2.

## SITTING A — database + dropdowns

### Step 1 — Scrape Flipper-IRDB
Shallow-clone `Lucaslhm/Flipper-IRDB` to a temp dir (NOT into the repo).
Categories: Projectors, TVs, Monitors, Audio_and_Video_Receivers, SoundBars,
Cable_Boxes, Blu-Ray, DVD_Players. Skip `_Converted_`, ACs, and everything else.

### Step 2 — Convert to per-brand shards
Extend `tools/flipper_ir_convert.py` into a proper scraper:
- Walk category/brand folders; parse every `.ir`; carry brand + source
  filename (model) as provenance on each entry.
- **Normalize button names** — IRDB is inconsistent (`Power`/`POWER`/`Power_on`
  /`On`; `Source`/`Input`/`Hdmi_1`/`HDMI1`). Map to canonical:
  `power_toggle, power_on, power_off, source_cycle, input_hdmi1/2/3,
  input_vga, input_comp, vol_up, vol_dn, mute, menu, other:<original>`.
  Keep the original name too. Log unmapped names to a report file; don't guess.
- Dedupe within a brand by (proto, code, canonical name).
- RAW entries: include with `"proto":"RAW"` in shards (app hides them until
  raw-send exists; the data shouldn't need a re-scrape later).
- Output `data/db/<category>/<brand>.json` + `data/db/index.json`
  (category → brand → {file, entry counts by canonical name}).
- Also emit `data/sweep-projector.json` and `data/sweep-tv.json`: deduped
  parsed power codes from the universal lists (already in data/), NEC-family
  first. These drive Identify mode.
- Sanity gates: Samsung TV shard contains SAMSUNG `0xE0E040BF`; NEC projector
  shard has >0 `power_on` AND `power_off` (discrete) entries; report totals.

### Step 3 — Library dropdowns in `app/index.html`
Category → Brand → Model/keymap → Function pickers fed by the index + lazy
shard fetch. Picking a function fills the existing proto/code/bits form;
Test and Save-to-slot work unchanged. Manual hex entry stays. Keep it one
file, vanilla JS.

### Step 4 — SITTING A CLOSE
Verify dropdowns end-to-end in desktop Chrome against the bench TV (a
library-picked Samsung power code must toggle it). Commit (include the
pre-existing uncommitted data/ + docs/ files), push, update STATUS.md.
STOP — Sitting B is a separate session.

## SITTING B — Identify mode + Favorites

### Step 5 — Firmware: direct send + protocol map
`trigger` accepts `{"proto":"NEC","code":"0x...","bits":32}` (send without
touching slots). Extend the protocol switch: SONY, RC5, RC6 (all native in
IRremoteESP8266). Notify `sent:direct` per send. Flash + serial-verify.
Do not change UUIDs or slot behavior.

### Step 6 — Identify mode in the app
Per the design doc: device-type picker → START streams the sweep list
~400ms/code with progress → STOP shows the last 5 as individual re-send
buttons → confirmed hit offers: save to favorites / save to slot / **keymap
unlock** (search loaded shards for same proto+address, show that device's
full keymap as tap-to-test rows — inputs included).

### Step 7 — Favorites
Per the design doc: ☆ on every code row (library, identify results, keymap
view); named entries; big tap-pads at the top of the app; `localStorage` +
JSON export/import (export = downloadable/shareable text, import = paste or
file). A favorite can be pushed to a slot.

### Step 8 — SITTING B CLOSE
End-to-end with Tyler: Identify sweep against the bench TV — it should hit
`0xE0E040BF` and the keymap unlock should surface Samsung input codes. Star
one to favorites, verify it survives an app reload, export/import round-trip.
Commit, push, update STATUS.md (next step = Phase 4 battery, waiting on
parts). Refresh PLAN.md roadmap. STOP.

END OF BRIEF
