#!/usr/bin/env python3
"""Flipper .ir -> IRremoteESP8266 JSON.

Two modes:

  Library scrape (the one you want):
      python3 tools/flipper_ir_convert.py --scrape <irdb-root> --out data/db
    -> writes data/db/<category>/<brand>.json, data/db/index.json,
       data/db/search.json, data/sweep-<type>.json, and an unmapped-name report.

  Single-file (convert an arbitrary Flipper .ir you supply yourself):
      python3 tools/flipper_ir_convert.py mystuff/somedevice.ir
    -> writes <path>.json next to each input.

Everything the repo ships is derived from Lucaslhm/Flipper-IRDB (CC0-1.0), which
is what <irdb-root> should point at. The sweep lists used to be built from the
Flipper Unleashed universal lists (GPL-3.0); those source files were removed when
the project went MIT, and the sweeps are now derived from the CC0 database — see
build_sweep_from_db below and data/README.md.

Flipper stores LSB-first byte values; IRremoteESP8266 wants MSB-first codes, so
each byte is bit-reversed and the frame assembled per protocol. That math is
bench-validated: it reproduces SAMSUNG 0xE0E040BF, the code physically verified
against the test TV.
"""

import argparse
import json
import os
import re
import sys
from collections import Counter, defaultdict

# ── conversion ──────────────────────────────────────────────────────────────

def rev(b):
    """Bit-reverse one byte (Flipper is LSB-first, IRremoteESP8266 is MSB-first)."""
    return int(f"{b:08b}"[::-1], 2)


def parse_ir(path):
    """Parse a Flipper .ir file into a list of raw field dicts."""
    entries, cur = [], {}
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.lower().startswith("name:"):
                if cur.get("name"):
                    entries.append(cur)
                cur = {"name": line.split(":", 1)[1].strip()}
            elif ":" in line and cur:
                k, v = line.split(":", 1)
                cur[k.strip()] = v.strip()
    if cur.get("name"):
        entries.append(cur)
    return entries


def _bytes(field):
    return [int(x, 16) for x in field.split()]


def convert(e):
    """Return {proto, code, bits} / RAW dict / TODO marker, or None if unusable."""
    if e.get("type") == "raw":
        try:
            return {
                "proto": "RAW",
                "freq": int(e.get("frequency", 38000)),
                "data": [int(x) for x in e["data"].split()],
            }
        except (KeyError, ValueError):
            return None

    proto = e.get("protocol")
    if not proto:
        return None
    try:
        ab, cb = _bytes(e["address"]), _bytes(e["command"])
    except (KeyError, ValueError):
        return None
    if not ab or not cb:
        return None
    a, c = ab[0], cb[0]

    if proto == "NEC":
        code = (rev(a) << 24) | (rev(a ^ 0xFF) << 16) | (rev(c) << 8) | rev(c ^ 0xFF)
        return {"proto": "NEC", "code": f"0x{code:08X}", "bits": 32}

    if proto == "NECext":                      # 16-bit address, cmd + inverted cmd
        if len(ab) < 2:
            return None
        code = (rev(ab[0]) << 24) | (rev(ab[1]) << 16) | (rev(c) << 8) | rev(c ^ 0xFF)
        return {"proto": "NEC", "code": f"0x{code:08X}", "bits": 32}

    if proto == "Samsung32":
        code = (rev(a) << 24) | (rev(a) << 16) | (rev(c) << 8) | rev(c ^ 0xFF)
        return {"proto": "SAMSUNG", "code": f"0x{code:08X}", "bits": 32}

    if proto in ("SIRC", "SIRC15", "SIRC20"):
        bits = {"SIRC": 12, "SIRC15": 15, "SIRC20": 20}[proto]
        addr = ab[0] | (ab[1] << 8 if len(ab) > 1 else 0)
        code = (addr << 7) | c
        return {"proto": "SONY", "code": f"0x{code:X}", "bits": bits, "verify": True}

    if proto == "RC5":
        code = (a << 6) | c
        return {"proto": "RC5", "code": f"0x{code:X}", "bits": 12, "verify": True}

    if proto == "RC6":
        code = (a << 8) | c
        return {"proto": "RC6", "code": f"0x{code:X}", "bits": 20, "verify": True}

    return {"proto": f"TODO:{proto}", "addr": e.get("address"), "cmd": e.get("command")}


# ── button-name normalisation ───────────────────────────────────────────────
# IRDB naming is wildly inconsistent (Power/POWER/Pwr/Tv_power/Standby;
# Source/Input/HDMI_1/HDMI1/Hdmi_1). Map to a canonical vocabulary, always
# keeping the original. Anything we are not confident about becomes
# other:<original> and is written to the unmapped report — we do not guess.

def _slug(name):
    """Slug for paths (categories, brands). Hyphens become underscores."""
    s = name.strip().lower()
    s = re.sub(r"[\s\-]+", "_", s)
    s = re.sub(r"_+", "_", s)
    return s.strip("_")


def _name_slug(name):
    """Slug for button names.

    Unlike _slug this preserves +/- as words, because they are the entire
    difference between VOL+ and VOL-. Folding '-' into '_' the way _slug does
    turns "VOL-" into "vol", which silently loses every volume-down code while
    volume-up keeps working — an asymmetry that is easy to miss.
    """
    s = name.strip().lower()
    s = s.replace("+", "_plus_").replace("-", "_minus_")
    s = re.sub(r"[\s]+", "_", s)
    s = re.sub(r"_+", "_", s)
    return s.strip("_")


# Ordered: first match wins, so discrete on/off beat the generic power rule.
_RULES = [
    ("power_on",     r"^(tv_|stb_|receiver_)?(power|pwr)_?on$|^on$|^standby_on$"),
    ("power_off",    r"^(tv_|stb_|receiver_)?(power|pwr)_?off$|^off$|^standby_off$"),
    ("power_toggle", r"^(tv_|stb_|receiver_|source_)?(power|pwr)\d*$|^standby$"),

    ("input_hdmi1",  r"^(input_)?hdmi_?1$"),
    ("input_hdmi2",  r"^(input_)?hdmi_?2$"),
    ("input_hdmi3",  r"^(input_)?hdmi_?3$"),
    ("input_hdmi4",  r"^(input_)?hdmi_?4$"),
    ("input_hdmi",   r"^(input_)?hdmi$"),
    ("input_vga",    r"^(input_)?vga$"),
    ("input_comp",   r"^(input_)?comp(onent)?_?\d?$"),
    ("source_cycle", r"^(tv_)?(source|input)s?$"),

    ("vol_up",       r"^vol(ume)?_?(up|plus)$|^plus_vol(ume)?$"),
    ("vol_dn",       r"^vol(ume)?_?(dn|dwn|down|minus|min)$|^minus_vol(ume)?$"),
    ("mute",         r"^mute$"),
    ("menu",         r"^menu$"),
]
_COMPILED = [(canon, re.compile(pat)) for canon, pat in _RULES]


def canonical(name):
    s = _name_slug(name)
    for canon, pat in _COMPILED:
        if pat.match(s):
            return canon
    return f"other:{name}"


# ── scrape ──────────────────────────────────────────────────────────────────

CATEGORIES = [
    "Projectors", "TVs", "Monitors", "Audio_and_Video_Receivers",
    "SoundBars", "Cable_Boxes", "Blu-Ray", "DVD_Players",
]

# A canonical code that shows up under this many distinct models within a brand
# is treated as a brand-generic ("blanket") code — the universal-remote sweet
# spot the app surfaces at the top of a brand's list.
GENERIC_MIN_MODELS = 3


def _dedupe_key(conv, canon):
    """Within-brand identity: same protocol + code + canonical function is the
    same code no matter which model file it came from. RAW has no code, so key it
    on the head of its timing array instead."""
    if conv["proto"] == "RAW":
        return (conv["proto"], str(conv["data"][:8]), canon)
    return (conv["proto"], conv.get("code") or "raw", canon)


def scrape(root, outdir):
    index = {}
    unmapped = Counter()
    totals = Counter()
    shards = {}           # (cat_slug, brand) -> entries, kept for the search index

    for category in CATEGORIES:
        cat_path = os.path.join(root, category)
        if not os.path.isdir(cat_path):
            print(f"  ! missing category {category}", file=sys.stderr)
            continue

        cat_slug = _slug(category)
        brands = {}

        for brand in sorted(os.listdir(cat_path)):
            brand_path = os.path.join(cat_path, brand)
            if not os.path.isdir(brand_path) or "_Converted_" in brand:
                continue

            # First pass: collect every convertible entry WITH its model, so the
            # model-spread of each code can be measured before deduping.
            collected = []          # (canon, conv, orig_name, model)
            for dirpath, dirnames, filenames in os.walk(brand_path):
                dirnames[:] = [d for d in dirnames if "_Converted_" not in d]
                for fn in sorted(filenames):
                    if not fn.endswith(".ir"):
                        continue
                    model = fn[:-3]
                    for raw in parse_ir(os.path.join(dirpath, fn)):
                        conv = convert(raw)
                        if not conv:
                            continue
                        if conv["proto"].startswith("TODO:"):
                            totals["todo"] += 1
                            continue
                        canon = canonical(raw["name"])
                        if canon.startswith("other:"):
                            unmapped[raw["name"]] += 1
                        collected.append((canon, conv, raw["name"], model))

            if not collected:
                continue

            # How many distinct models share each code → blanket-code detection.
            spread = defaultdict(set)
            for canon, conv, orig, model in collected:
                spread[_dedupe_key(conv, canon)].add(model)

            # Second pass: dedupe within the brand by (proto, code, canonical name),
            # annotating each survivor with its model-spread.
            entries, seen = [], set()
            for canon, conv, orig, model in collected:
                key = _dedupe_key(conv, canon)
                if key in seen:
                    totals["dupes"] += 1
                    continue
                seen.add(key)

                nmodels = len(spread[key])
                entry = {
                    "name": canon,
                    "orig": orig,
                    "brand": brand,
                    "model": model,
                    **conv,
                }
                if nmodels > 1:
                    entry["nmodels"] = nmodels
                # Promote canonical (not other:, not RAW) codes shared across many
                # models to brand-generic. Toggle beside discrete on/off is fine —
                # they are distinct canonical names and each promotes on its own.
                if (nmodels >= GENERIC_MIN_MODELS
                        and conv["proto"] != "RAW"
                        and not canon.startswith("other:")):
                    entry["generic"] = True
                entries.append(entry)
                totals["raw" if conv["proto"] == "RAW" else "parsed"] += 1

            brand_slug = _slug(brand)
            rel = f"{cat_slug}/{brand_slug}.json"
            dest = os.path.join(outdir, rel)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with open(dest, "w", encoding="utf-8") as fh:
                json.dump(entries, fh, separators=(",", ":"))

            shards[(cat_slug, brand)] = entries
            counts = Counter(e["name"] for e in entries)
            brands[brand] = {
                "file": rel,
                "total": len(entries),
                "generic": sum(1 for e in entries if e.get("generic")),
                "counts": {k: v for k, v in sorted(counts.items())
                           if not k.startswith("other:")},
            }

        if brands:
            index[cat_slug] = {"label": category.replace("_", " "), "brands": brands}
            print(f"  {category}: {len(brands)} brands, "
                  f"{sum(b['total'] for b in brands.values())} entries, "
                  f"{sum(b['generic'] for b in brands.values())} generic")

    os.makedirs(outdir, exist_ok=True)
    with open(os.path.join(outdir, "index.json"), "w", encoding="utf-8") as fh:
        json.dump(index, fh, separators=(",", ":"))

    return index, shards, unmapped, totals


# ── search index ─────────────────────────────────────────────────────────────
# Field feedback: on a ladder, browsing four dropdowns is too slow — the front
# door should be a search box. This emits one compact record per brand (brand +
# category + canonical functions + model strings) so the app can match "epson",
# "hdmi", or a model number live. Shards themselves still lazy-load on selection.

def build_search(index, shards, out_path):
    records = []
    for (cat_slug, brand), entries in sorted(shards.items()):
        cat = index[cat_slug]
        meta = cat["brands"][brand]
        fns = sorted({e["name"] for e in entries
                      if not e["name"].startswith("other:")})
        models = sorted({e["model"] for e in entries})
        records.append({
            "c": cat_slug,          # category slug
            "cl": cat["label"],     # category label
            "b": brand,             # brand (display + shard match)
            "f": meta["file"],      # shard path for lazy fetch
            "n": meta["total"],     # sendable+raw entry count
            "g": meta["generic"],   # generic-code count
            "fn": fns,              # canonical functions present
            "m": models,            # model strings (searchable)
        })
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(records, fh, separators=(",", ":"))
    print(f"  {out_path}: {len(records)} brand records, "
          f"{os.path.getsize(out_path)//1024} KB")
    return records


# ── sweep lists ─────────────────────────────────────────────────────────────

# Try discrete power_on before toggle before power_off: an already-on device
# stays on rather than flickering off mid-sweep (field feedback).
_POWER_ORDER = {"power_on": 0, "power_toggle": 1, "power_off": 2}

# Which database categories feed each sweep type. `monitor` shares the TV list
# in the app (SWEEP_FILES in app/index.html), so monitors feed it too.
SWEEP_SETS = {
    "tv": ["tvs", "monitors"],
    "projector": ["projectors"],
}


def build_sweep_from_db(shards, cats, out_path):
    """Power codes from the CC0 database -> one sweep file.

    This is the same blanket-code idea the brand view uses, widened to the whole
    category: a power code that many distinct models share is, by definition, a
    code a universal sweep should fire early. So model-spread (summed across
    every brand in the category) is the ranking signal.

    Ordering is spread-descending *within* the power_on / power_toggle /
    power_off groups, not globally — the "don't flick an already-on device off"
    rule outranks hit rate. RAW is skipped (the BLE write can't carry a timing
    array yet), as are unsupported protocols.
    """
    spread = Counter()      # (proto, code, canonical name) -> distinct models
    rep = {}                # same key -> representative entry (for bits/orig)

    for (cat_slug, _brand), entries in shards.items():
        if cat_slug not in cats:
            continue
        for e in entries:
            if not e["name"].startswith("power_"):
                continue
            if e["proto"] == "RAW" or e["proto"].startswith("TODO:"):
                continue
            key = (e["proto"], e["code"], e["name"])
            # `nmodels` is the within-brand spread the scrape already measured;
            # absent means it came from exactly one model file.
            spread[key] += e.get("nmodels", 1)
            rep.setdefault(key, e)

    # Collapse to one record per (proto, code). A code can carry more than one
    # canonical name across brands (power_on here, power_toggle there); keep the
    # reading with the most models behind it, and sum the spread over all of them.
    best, total = {}, Counter()
    for key, n in spread.items():
        proto, code, name = key
        total[(proto, code)] += n
        cur = best.get((proto, code))
        if cur is None or (n, -_POWER_ORDER.get(name, 3)) > (
                spread[cur], -_POWER_ORDER.get(cur[2], 3)):
            best[(proto, code)] = key

    sweep = []
    for (proto, code), key in best.items():
        e = rep[key]
        sweep.append({"proto": proto, "code": code, "bits": e["bits"],
                      "name": key[2], "orig": e.get("orig")})

    sweep.sort(key=lambda x: (_POWER_ORDER.get(x["name"], 3),
                              -total[(x["proto"], x["code"])], x["code"]))
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(sweep, fh, separators=(",", ":"))

    by_proto = Counter(x["proto"] for x in sweep)
    by_name = Counter(x["name"] for x in sweep)
    widest = sorted(sweep, key=lambda x: -total[(x["proto"], x["code"])])[:3]
    top = ", ".join(f"{x['proto']} {x['code']} ({total[(x['proto'], x['code'])]} models)"
                    for x in widest)
    print(f"  {out_path}: {len(sweep)} codes from {'+'.join(cats)} "
          f"{dict(by_proto)} {dict(by_name)}")
    print(f"      widest-spread codes: {top}")
    return sweep


# ── sanity gates ────────────────────────────────────────────────────────────

def sanity(outdir, index):
    ok = True

    def load(cat, brand_slug):
        p = os.path.join(outdir, cat, f"{brand_slug}.json")
        if not os.path.exists(p):
            return None
        with open(p, encoding="utf-8") as fh:
            return json.load(fh)

    # 1. The bench-verified Samsung TV power code must be present.
    samsung = load("tvs", "samsung")
    hit = samsung and any(e["proto"] == "SAMSUNG" and e.get("code") == "0xE0E040BF"
                          for e in samsung)
    print(f"  [{'PASS' if hit else 'FAIL'}] Samsung TV shard contains "
          f"SAMSUNG 0xE0E040BF (bench-verified)")
    ok &= bool(hit)

    # 2. NEC projectors should expose discrete power_on AND power_off.
    nec = load("projectors", "nec")
    on = sum(1 for e in nec or [] if e["name"] == "power_on")
    off = sum(1 for e in nec or [] if e["name"] == "power_off")
    good = on > 0 and off > 0
    print(f"  [{'PASS' if good else 'FAIL'}] NEC projector shard has discrete "
          f"power_on={on} power_off={off}")
    ok &= good

    # 3. Blanket-code promotion actually fired for a big brand.
    gen = sum(1 for e in samsung or [] if e.get("generic"))
    good3 = gen > 0
    print(f"  [{'PASS' if good3 else 'FAIL'}] Samsung TV shard has generic "
          f"(blanket) codes: {gen}")
    ok &= good3

    # 4. Search index exists, is non-empty, and can find Samsung TVs.
    sp = os.path.join(outdir, "search.json")
    recs = json.load(open(sp, encoding="utf-8")) if os.path.exists(sp) else []
    good4 = any(r["b"] == "Samsung" and r["c"] == "tvs" for r in recs)
    print(f"  [{'PASS' if good4 else 'FAIL'}] search.json present "
          f"({len(recs)} brand records) and indexes Samsung TVs")
    ok &= good4

    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="*", help="single-file mode: .ir files")
    ap.add_argument("--scrape", metavar="IRDB_ROOT")
    ap.add_argument("--out", default="data/db")
    ap.add_argument("--sweep-dir", default="data",
                    help="where sweep-<type>.json are written (default: data)")
    ap.add_argument("--report", default="data/db/unmapped-names.txt")
    args = ap.parse_args()

    if args.scrape:
        print("Scraping Flipper-IRDB ...")
        index, shards, unmapped, totals = scrape(args.scrape, args.out)

        print("\nSearch index:")
        build_search(index, shards, os.path.join(args.out, "search.json"))

        print("\nSweep lists (from the CC0 database, not from any external list):")
        for kind, cats in SWEEP_SETS.items():
            build_sweep_from_db(shards, cats,
                                os.path.join(args.sweep_dir, f"sweep-{kind}.json"))

        os.makedirs(os.path.dirname(args.report), exist_ok=True)
        with open(args.report, "w", encoding="utf-8") as fh:
            fh.write("# Button names with no canonical mapping (kept as other:<name>).\n")
            fh.write(f"# {len(unmapped)} distinct names, "
                     f"{sum(unmapped.values())} occurrences.\n\n")
            for name, n in unmapped.most_common():
                fh.write(f"{n:6d}  {name}\n")

        print(f"\nTotals: {totals['parsed']} parsed, {totals['raw']} RAW, "
              f"{totals['dupes']} dupes dropped, {totals['todo']} unsupported protocol")
        print(f"Unmapped names: {len(unmapped)} distinct "
              f"({sum(unmapped.values())} occurrences) -> {args.report}")

        print("\nSanity gates:")
        if not sanity(args.out, index):
            print("\nSANITY GATE FAILED", file=sys.stderr)
            return 1
        print("\nAll sanity gates passed.")
        return 0

    # single-file mode
    for path in args.paths:
        entries = parse_ir(path)
        out, skipped = [], 0
        for e in entries:
            c = convert(e)
            if c:
                out.append({"name": e["name"], **c})
            else:
                skipped += 1
        ofile = path.replace(".ir", ".json")
        with open(ofile, "w", encoding="utf-8") as fh:
            json.dump(out, fh, indent=1)
        protos = Counter(o["proto"] for o in out)
        print(f"{path}: {len(out)} converted, {skipped} skipped -> {ofile}")
        print("  ", dict(protos))
        hits = [o for o in out if o["proto"] == "SAMSUNG" and o.get("code") == "0xE0E040BF"]
        if hits:
            print(f"  SELF-CHECK PASS: Samsung 0xE0E040BF found ({len(hits)}x)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
