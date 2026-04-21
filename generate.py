#!/usr/bin/env python3
"""Generate filaments.json mapping Bambu Lab RFID variant IDs to SpoolmanDB filament IDs."""

import json
import re
import subprocess
import urllib.request
from pathlib import Path

RFID_REPO_URL = "https://github.com/queengooborg/Bambu-Lab-RFID-Library.git"
RFID_README_URL = "https://raw.githubusercontent.com/queengooborg/Bambu-Lab-RFID-Library/main/README.md"
RFID_CACHE_DIR = Path(".cache/rfid-library")
SPOOLMAN_URL = "https://donkie.github.io/SpoolmanDB/filaments.json"
BAMBU_COLORS_URL = "https://raw.githubusercontent.com/bambulab/BambuStudio/master/resources/profiles/BBL/filament/filaments_color_codes.json"
MANUAL_ADDITIONS_FILE = "manual_additions.json"

# Map RFID section -> (spoolmandb_material, name_prefix, name_suffix)
# None = no SpoolmanDB equivalent
MATERIAL_MAP = {
    "PLA Basic": ("PLA", "", ""),
    "PLA Matte": ("PLA", "Matte ", ""),
    "PLA Silk+": ("PLA", "Silk+ ", ""),
    "PLA Glow": ("PLA", "Glow ", ""),
    "PLA Translucent": ("PLA", "Translucent ", ""),
    "PLA Galaxy": ("PLA", "", " Galaxy"),
    "PLA Sparkle": ("PLA", "", ""),
    "PLA Metal": ("PLA", "", ""),
    "PLA Marble": ("PLA", "", ""),
    "PLA Basic Gradient": ("PLA", "", ""),
    "PLA Silk Multi-Color": ("PLA", "", ""),
    "PLA Tough+": ("PLA", "Tough+ ", ""),
    "PLA Wood": ("PLA+WOOD", "", ""),
    "PLA-CF": ("PLA-CF", "", ""),
    "PLA Lite": None,
    "PLA Aero": None,
    "PLA Tough": None,
    "PETG Basic": ("PETG", "", ""),
    "PETG HF": ("PETG", "HF ", ""),
    "PETG Translucent": ("PETG", "", ""),
    "PETG-CF": ("PETG-CF", "", ""),
    "ABS": ("ABS", "", ""),
    "ABS-GF": ("ABS-GF", "", ""),
    "ASA": ("ASA", "", ""),
    "ASA Aero": ("ASA", "", " Aero"),
    "ASA-CF": ("ASA-CF", "", ""),
    "PC": ("PC", "", ""),
    "PC FR": ("PC", "FR ", ""),
    "TPU for AMS": ("TPU", "For AMS ", ""),
    "PAHT-CF": ("PAHT-CF", "", ""),
    "PA6-GF": ("PA6-GF", "", ""),
    "PA6-CF": ("PA6-CF", "", ""),
    "Support for PLA/PETG": ("PLA", "Support for PLA/PETG ", ""),
    "Support for PLA (New Version)": ("PLA", "Support for PLA ", ""),
    "Support for ABS": ("ABS", "Support for ABS", ""),
    "Support for PA/PET": ("PA", "Support for PA/PET", ""),
    "PVA": ("PVA", "", ""),
}

SUPPORT_NO_COLOR = {"Support for ABS", "Support for PA/PET"}

RE_SECTION = re.compile(r"^####\s+\[([^\]]+)\]", re.MULTILINE)
RE_ROW = re.compile(
    r"\|\s*\[([^\]]+)\]\([^)]*\)\s*\|"
    r"\s*(\d+)\s*\|"
    r"\s*([^|]+?)\s*\|"
    r"\s*([^|]*?)\s*\|"
)
RE_VARIANT_ID = re.compile(r"[A-Z]\d+-\w+")
RE_SLASH_ID = re.compile(r"([A-Z]\d+-)(\w+)/(\w+)")


# --- Download ---


def download(url: str) -> str:
    print(f"  {url}")
    req = urllib.request.Request(url, headers={"User-Agent": "bambu-spoolman-db/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8")


# --- Parsing ---


def parse_rfid_readme(markdown: str) -> list[dict]:
    """Parse RFID library README into list of {section, color, code, variant_id}."""
    entries = []
    section = None

    for line in markdown.split("\n"):
        m = RE_SECTION.match(line)
        if m:
            section = m.group(1).strip()
            continue

        if section is None:
            continue

        m = RE_ROW.search(line)
        if not m:
            continue

        color = m.group(1).strip()
        code = m.group(2).strip()
        raw_id = m.group(3).strip()

        if not raw_id or raw_id == "?":
            continue

        def add(vid):
            entries.append({"section": section, "color": color, "code": code, "variant_id": vid})

        # "A00-G1/G6" -> two entries
        m = RE_SLASH_ID.match(raw_id)
        if m:
            add(m.group(1) + m.group(2))
            add(m.group(1) + m.group(3))
            continue

        # "S02-W0 (Old: S00-W0)" -> primary + old
        primary = RE_VARIANT_ID.match(raw_id)
        if primary:
            add(primary.group(0))
            old = re.search(r"Old:\s*([A-Z]\d+-\w+)", raw_id)
            if old:
                add(old.group(1))

    return entries


def fetch_rfid_repo():
    """Clone or update the RFID library locally for dump parsing."""
    if RFID_CACHE_DIR.exists():
        subprocess.run(
            ["git", "-C", str(RFID_CACHE_DIR), "pull", "--quiet", "--ff-only"],
            check=True,
        )
    else:
        RFID_CACHE_DIR.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["git", "clone", "--quiet", "--depth=1", RFID_REPO_URL, str(RFID_CACHE_DIR)],
            check=True,
        )


def _decode_string(block_hex: str) -> str:
    try:
        return bytes.fromhex(block_hex).rstrip(b"\0").decode("ascii").strip()
    except (ValueError, UnicodeDecodeError):
        return ""


def _u16_le(block: bytes, offset: int) -> int:
    if len(block) < offset + 2:
        return 0
    return int.from_bytes(block[offset:offset + 2], "little")


def parse_rfid_dumps() -> list[dict]:
    """Parse all RFID tag dumps.

    Block layout (per Bambu-Lab-RFID-Tag-Guide):
      Block 1: [0:8]=variant_id (MQTT tray_id_name)
      Block 2: material (e.g. "PLA")
      Block 4: product (e.g. "PLA Basic") — MQTT tray_sub_brands
      Block 5: [0:4]=color RRGGBBAA, [4:6]=weight u16
      Block 6: [8:10]=temp_max, [10:12]=temp_min (u16 LE nozzle temps)
      Block 16: [0:2]=format, [2:4]=color_count, [4:8]=second color (ABGR reversed)
    """
    fetch_rfid_repo()

    by_variant: dict[str, dict] = {}

    for dump_path in sorted(RFID_CACHE_DIR.rglob("hf-mf-*-dump.json")):
        try:
            data = json.loads(dump_path.read_text())
        except (json.JSONDecodeError, OSError):
            continue

        blocks = data.get("blocks", {})
        b1_hex = blocks.get("1", "")
        b4_hex = blocks.get("4", "")
        b5_hex = blocks.get("5", "")
        if len(b1_hex) < 32 or len(b4_hex) < 32 or len(b5_hex) < 32:
            continue

        variant_id = _decode_string(b1_hex[:16])
        material = _decode_string(blocks.get("2", ""))
        product = _decode_string(b4_hex)
        if not variant_id or not product:
            continue

        try:
            b5 = bytes.fromhex(b5_hex)
            b6 = bytes.fromhex(blocks.get("6", ""))
            b16 = bytes.fromhex(blocks.get("16", ""))
        except ValueError:
            continue

        color_hex = b5[:4].hex().upper() if len(b5) >= 4 else None
        weight = _u16_le(b5, 4) or None
        temp_max = _u16_le(b6, 8) or None
        temp_min = _u16_le(b6, 10) or None

        color_hexes: list[str] = []
        if color_hex:
            color_hexes.append(color_hex)
        if len(b16) >= 8:
            fmt = _u16_le(b16, 0)
            count = _u16_le(b16, 2)
            if fmt == 2 and count >= 2:
                # Second color bytes are ABGR-reversed; reverse to get RGBA
                second = b16[4:8][::-1].hex().upper()
                if second != "00000000":
                    color_hexes.append(second)

        # Folder hint for SpoolmanDB color-name matching: <product>/<color>/<tagUID>/<file>
        color_hint = dump_path.parts[-3] if len(dump_path.parts) >= 3 else ""

        by_variant.setdefault(variant_id, {
            "id": variant_id,
            "material": material or None,
            "product": product,
            "color_hex": color_hex,
            "color_hexes": color_hexes,
            "weight": weight,
            "temp_min": temp_min,
            "temp_max": temp_max,
            "_color_hint": color_hint,
        })

    return list(by_variant.values())


def parse_spoolman(filaments: list[dict]) -> dict[str, list[dict]]:
    """Build index: material -> [bambulab entries]."""
    index: dict[str, list[dict]] = {}
    for f in filaments:
        if f.get("id", "").startswith("bambulab_"):
            index.setdefault(f["material"], []).append(f)
    return index


def parse_bambu_colors(data: dict) -> dict[str, dict]:
    """Build index: filament_code -> {name, cols: list of 8-char RRGGBBAA}."""
    index = {}
    for e in data.get("data", []):
        code = e.get("fila_color_code", "")
        name = e.get("fila_color_name", {}).get("en", "")
        if not code or not name:
            continue
        cols = []
        for c in e.get("fila_color", []):
            h = c.lstrip("#").upper()
            if len(h) == 6:
                h += "FF"
            if len(h) == 8:
                cols.append(h)
        index[code] = {"name": name, "cols": cols}
    return index


# --- Matching ---


def normalize(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def swap_grey_gray(name: str) -> str:
    if "Grey" in name:
        return name.replace("Grey", "Gray")
    if "Gray" in name:
        return name.replace("Gray", "Grey")
    return name


def build_display_name(section: str, color: str) -> str:
    """Build expected SpoolmanDB name from RFID section + color."""
    config = MATERIAL_MAP.get(section)
    if config is None:
        return color
    _, prefix, suffix = config
    if section in SUPPORT_NO_COLOR:
        return prefix.strip()
    return f"{prefix}{color}{suffix}"


def find_spoolman_match(
    section: str, color: str, spoolman: dict, bambu_hex: str | None = None
) -> tuple[str | None, str | None, str | None]:
    """Find SpoolmanDB match. Returns (id, name, color_hex) or (None, None, None)."""
    config = MATERIAL_MAP.get(section)
    if config is None:
        return None, None, None

    candidates = spoolman.get(config[0], [])
    if not candidates:
        return None, None, None

    target = build_display_name(section, color)
    norm = normalize(target)

    def _found(c):
        return c["id"], c["name"], c.get("color_hex")

    # Exact
    for c in candidates:
        if c["name"] == target:
            return _found(c)

    # Normalized
    for c in candidates:
        if normalize(c["name"]) == norm:
            return _found(c)

    # Grey<->Gray
    swapped = swap_grey_gray(target)
    if swapped != target:
        for c in candidates:
            if c["name"] == swapped or normalize(c["name"]) == normalize(swapped):
                return _found(c)

    # Partial (strip parenthesized parts for multi-color names)
    for c in candidates:
        base = re.sub(r"\s*\([^)]*\)", "", c["name"])
        if base == target or normalize(base) == norm:
            return _found(c)

    # Hex match (last resort, only within same material). Compare RGB only — SpoolmanDB mixes 6 and 8-char.
    if bambu_hex:
        bambu_rgb = bambu_hex.lower()[:6]
        for c in candidates:
            c_rgb = (c.get("color_hex") or "").lower()[:6]
            if c_rgb and c_rgb == bambu_rgb:
                return _found(c)

    return None, None, None


# --- Main ---


def load_manual_additions() -> list[dict]:
    """Load locally-curated entries for filaments not yet in the upstream RFID library."""
    try:
        with open(MANUAL_ADDITIONS_FILE) as f:
            return json.load(f)
    except FileNotFoundError:
        return []


def _normalize_color_hex(raw: str | None) -> str | None:
    """Accept 6 or 8-char hex (with or without #), return 8-char uppercase RRGGBBAA."""
    if not raw:
        return None
    h = raw.lstrip("#").upper()
    if len(h) == 6:
        h += "FF"
    return h if len(h) == 8 else None


def _infer_material(product: str | None) -> str | None:
    """Derive broad material (e.g. 'PLA') from product (e.g. 'PLA Aero', 'PLA-CF')."""
    if not product:
        return None
    return product.split(" ")[0].split("-")[0] or None


def _lookup_bambu_by_hex(
    color_hex: str | None,
    product: str,
    bambu_by_hex: dict,
    product_prefixes: dict,
) -> tuple[str | None, dict | None]:
    """Look up a BambuStudio entry by color hex, disambiguated by known product prefixes."""
    if not color_hex:
        return None, None
    candidates = bambu_by_hex.get(color_hex, [])
    prefixes = product_prefixes.get(product, set())
    filtered = [c for c in candidates if c[0][:2] in prefixes] if prefixes else []
    picked = filtered[0] if filtered else (candidates[0] if candidates else None)
    return picked if picked else (None, None)


def main():
    print("Fetching sources...")
    dump_entries = parse_rfid_dumps()
    readme_entries = parse_rfid_readme(download(RFID_README_URL))
    spoolman = parse_spoolman(json.loads(download(SPOOLMAN_URL)))
    bambu_names = parse_bambu_colors(json.loads(download(BAMBU_COLORS_URL)))
    manual = load_manual_additions()

    # README: variant -> list of SKUs (re-released variants keep all)
    skus_by_variant: dict[str, list[str]] = {}
    for e in readme_entries:
        skus_by_variant.setdefault(e["variant_id"], []).append(e["code"])

    # Product -> known BambuStudio SKU prefixes (disambiguates shared hexes like 000000)
    product_prefixes: dict[str, set[str]] = {}
    for e in readme_entries:
        if e.get("code") and e.get("section"):
            product_prefixes.setdefault(e["section"], set()).add(e["code"][:2])

    # BambuStudio RRGGBBAA -> [(sku, info), ...]
    bambu_by_hex: dict[str, list[tuple[str, dict]]] = {}
    for sku, info in bambu_names.items():
        for hex8 in info.get("cols", []):
            bambu_by_hex.setdefault(hex8, []).append((sku, info))

    # Merge: dump entries primary; add README-only variants as stubs
    dump_ids = {e["id"] for e in dump_entries}
    entries = list(dump_entries)
    for e in readme_entries:
        if e["variant_id"] not in dump_ids:
            entries.append({
                "id": e["variant_id"],
                "material": None,
                "product": e["section"],
                "color_hex": None,
                "color_hexes": [],
                "weight": None,
                "temp_min": None,
                "temp_max": None,
                "_color_hint": e["color"],
            })

    spoolman_count = sum(len(v) for v in spoolman.values())
    print(f"\nParsed {len(dump_entries)} RFID dumps, "
          f"{len(readme_entries)} README entries, "
          f"{spoolman_count} SpoolmanDB entries, "
          f"{len(bambu_names)} BambuStudio colors, "
          f"{len(manual)} manual additions")

    unknown_products = {e["product"] for e in entries if e["product"] not in MATERIAL_MAP}

    results = []
    seen = set()
    hex_mismatches = []

    for entry in entries:
        vid = entry["id"]
        if vid in seen:
            continue
        seen.add(vid)

        color_hex = entry.get("color_hex")
        product = entry["product"]

        # Look up Bambu SKU: prefer the README SKU whose BambuStudio hex matches the tag color
        sku = None
        bambu_info = None
        readme_skus = skus_by_variant.get(vid, [])
        if color_hex:
            for c in readme_skus:
                info = bambu_names.get(c)
                if info and color_hex in info.get("cols", []):
                    sku, bambu_info = c, info
                    break
        if bambu_info is None:
            for c in readme_skus:
                info = bambu_names.get(c)
                if info:
                    sku, bambu_info = c, info
                    break
        if bambu_info is None and color_hex:
            sku, bambu_info = _lookup_bambu_by_hex(color_hex, product, bambu_by_hex, product_prefixes)
        if sku is None and readme_skus:
            sku = readme_skus[0]

        bambu_cols = bambu_info.get("cols", []) if bambu_info else []

        color_hint = entry.get("_color_hint") or ""
        rgb = color_hex or (bambu_cols[0] if bambu_cols else None)
        spoolman_id, spoolman_name, spoolman_hex = find_spoolman_match(
            product, color_hint, spoolman, rgb
        )

        color_name = (
            (bambu_info["name"] if bambu_info else None)
            or spoolman_name
            or build_display_name(product, color_hint)
        )

        # Backfill color from BambuStudio when the tag didn't provide it
        if not color_hex and bambu_cols:
            color_hex = bambu_cols[0]
        color_hexes = entry.get("color_hexes") or bambu_cols

        if spoolman_id and rgb and spoolman_hex and rgb.lower()[:6] != spoolman_hex.lower()[:6]:
            hex_mismatches.append((vid, color_name, rgb, spoolman_hex, spoolman_id))

        results.append({
            "id": vid,
            "sku": sku,
            "material": entry.get("material") or _infer_material(product),
            "product": product,
            "color_name": color_name,
            "color_hex": color_hex,
            "color_hexes": color_hexes,
            "weight": entry.get("weight"),
            "temp_min": entry.get("temp_min"),
            "temp_max": entry.get("temp_max"),
            "integrations": {"spoolman": spoolman_id},
        })

    # Manual additions: same shape, fill in from BambuStudio where possible
    for m in manual:
        vid = m["id"]
        if vid in seen:
            continue
        seen.add(vid)

        product = m["product"]
        color_hex = _normalize_color_hex(m.get("color_hex"))
        sku = m.get("sku")
        color_name = m.get("color_name")

        bambu_info = None
        if sku:
            bambu_info = bambu_names.get(sku)
        if bambu_info is None and color_hex:
            sku2, bambu_info = _lookup_bambu_by_hex(color_hex, product, bambu_by_hex, product_prefixes)
            sku = sku or sku2
        if bambu_info:
            color_name = color_name or bambu_info["name"]
            if not color_hex and bambu_info.get("cols"):
                color_hex = bambu_info["cols"][0]

        color_hexes = m.get("color_hexes") or ([color_hex] if color_hex else [])

        spoolman_id = (m.get("integrations") or {}).get("spoolman")
        if spoolman_id is None:
            spoolman_id, _, _ = find_spoolman_match(product, color_name or "", spoolman, color_hex)

        results.append({
            "id": vid,
            "sku": sku,
            "material": m.get("material") or _infer_material(product),
            "product": product,
            "color_name": color_name,
            "color_hex": color_hex,
            "color_hexes": color_hexes,
            "weight": m.get("weight"),
            "temp_min": m.get("temp_min"),
            "temp_max": m.get("temp_max"),
            "integrations": {"spoolman": spoolman_id},
        })

    # Backfill weight / temp_min / temp_max from sibling variants (same product + ID prefix).
    # Pooled from tagged entries so README-only stubs inherit physical specs.
    pool: dict[tuple[str, str], dict] = {}
    for r in results:
        prefix = r["id"].split("-", 1)[0]
        key = (r["product"], prefix)
        bucket = pool.setdefault(key, {})
        for field in ("weight", "temp_min", "temp_max"):
            if bucket.get(field) is None and r.get(field) is not None:
                bucket[field] = r[field]
    for r in results:
        prefix = r["id"].split("-", 1)[0]
        bucket = pool.get((r["product"], prefix), {})
        for field in ("weight", "temp_min", "temp_max"):
            if r.get(field) is None and bucket.get(field) is not None:
                r[field] = bucket[field]

    results.sort(key=lambda x: x["id"])
    with open("filaments.json", "w") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
        f.write("\n")

    matched = [r for r in results if r["integrations"]["spoolman"]]
    unmatched = [r for r in results if not r["integrations"]["spoolman"]]

    print(f"\n{'=' * 50}")
    print(f"Total: {len(results)} | Matched: {len(matched)} | Unmatched: {len(unmatched)}")
    print(f"{'=' * 50}")

    if unknown_products:
        print(f"\nUnknown products (not in MATERIAL_MAP):")
        for s in sorted(unknown_products):
            print(f"  - {s}")

    if hex_mismatches:
        print("\nHex mismatches (tag/bambu vs SpoolmanDB):")
        for vid, name, bhex, shex, sid in hex_mismatches:
            print(f"  {vid} {name}: tag=#{bhex} spoolman=#{shex} ({sid})")

    if unmatched:
        print(f"\nUnmatched entries:")
        by_prod: dict[str, list] = {}
        for r in unmatched:
            by_prod.setdefault(r["product"], []).append(r)
        for prod in sorted(by_prod):
            names = ", ".join(f'{r["color_name"]} ({r["id"]})' for r in by_prod[prod])
            print(f"  {prod}: {names}")

    print(f"\nWrote filaments.json")


if __name__ == "__main__":
    main()
