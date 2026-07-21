#!/usr/bin/env python3
"""Flipper .ir -> IRremoteESP8266 JSON.

Two modes:

  Single-file (the original prototype behaviour, kept for the universal lists):
      python3 tools/flipper_ir_convert.py data/source/tv.ir ...
    -> writes <path>.json next to each input.

  Library scrape (Phase 5):
      python3 tools/flipper_ir_convert.py --scrape <irdb-root> --out data/db \
             --sweep-from data/projectors.json:projector data/tv.json:tv
    -> writes data/db/<category>/<brand>.json, data/db/index.json,
       data/sweep-<type>.json, and an unmapped-name report.

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


def scrape(root, outdir):
    index = {}
    unmapped = Counter()
    totals = Counter()

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

            entries, seen = [], set()
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

                        # Dedupe within the brand by (proto, code, canonical name).
                        key = (conv["proto"], conv.get("code") or "raw", canon)
                        if conv["proto"] == "RAW":
                            key = (conv["proto"], str(conv["data"][:8]), canon)
                        if key in seen:
                            totals["dupes"] += 1
                            continue
                        seen.add(key)

                        entry = {
                            "name": canon,
                            "orig": raw["name"],
                            "brand": brand,
                            "model": model,
                            **conv,
                        }
                        entries.append(entry)
                        totals["raw" if conv["proto"] == "RAW" else "parsed"] += 1

            if not entries:
                continue

            brand_slug = _slug(brand)
            rel = f"{cat_slug}/{brand_slug}.json"
            dest = os.path.join(outdir, rel)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with open(dest, "w", encoding="utf-8") as fh:
                json.dump(entries, fh, separators=(",", ":"))

            counts = Counter(e["name"] for e in entries)
            brands[brand] = {
                "file": rel,
                "total": len(entries),
                "counts": {k: v for k, v in sorted(counts.items())
                           if not k.startswith("other:")},
            }

        if brands:
            index[cat_slug] = {"label": category.replace("_", " "), "brands": brands}
            print(f"  {category}: {len(brands)} brands, "
                  f"{sum(b['total'] for b in brands.values())} entries")

    os.makedirs(outdir, exist_ok=True)
    with open(os.path.join(outdir, "index.json"), "w", encoding="utf-8") as fh:
        json.dump(index, fh, separators=(",", ":"))

    return index, unmapped, totals


# ── sweep lists ─────────────────────────────────────────────────────────────

# NEC-family first: highest hit rate, so a sweep finds the device soonest.
_PROTO_ORDER = {"NEC": 0, "SAMSUNG": 1, "SONY": 2, "RC5": 3, "RC6": 4}


def build_sweep(src_json, out_path):
    """Deduped, parsed power codes from a universal list -> sweep file."""
    with open(src_json, encoding="utf-8") as fh:
        data = json.load(fh)

    seen, sweep, raw_skipped = set(), [], 0
    for e in data:
        canon = canonical(e.get("name", ""))
        if not canon.startswith("power_"):
            continue
        if e.get("proto") == "RAW":
            raw_skipped += 1        # cannot send RAW until chunked writes exist
            continue
        if e.get("proto", "").startswith("TODO:"):
            continue
        key = (e["proto"], e["code"])
        if key in seen:
            continue
        seen.add(key)
        sweep.append({"proto": e["proto"], "code": e["code"],
                      "bits": e["bits"], "name": canon, "orig": e.get("name")})

    sweep.sort(key=lambda x: (_PROTO_ORDER.get(x["proto"], 9), x["code"]))
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(sweep, fh, separators=(",", ":"))

    by_proto = Counter(x["proto"] for x in sweep)
    print(f"  {out_path}: {len(sweep)} codes {dict(by_proto)} "
          f"({raw_skipped} RAW skipped)")
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

    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="*", help="single-file mode: .ir files")
    ap.add_argument("--scrape", metavar="IRDB_ROOT")
    ap.add_argument("--out", default="data/db")
    ap.add_argument("--sweep-from", nargs="*", default=[],
                    help="src.json:type pairs, e.g. data/tv.json:tv")
    ap.add_argument("--report", default="data/db/unmapped-names.txt")
    args = ap.parse_args()

    if args.scrape:
        print("Scraping Flipper-IRDB ...")
        index, unmapped, totals = scrape(args.scrape, args.out)

        print("\nSweep lists:")
        for pair in args.sweep_from:
            src, kind = pair.rsplit(":", 1)
            build_sweep(src, f"data/sweep-{kind}.json")

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
