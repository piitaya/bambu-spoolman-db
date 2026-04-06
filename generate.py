#!/usr/bin/env python3
"""Generate bambu_variants.json mapping Bambu Lab RFID variant IDs to SpoolmanDB filament IDs."""

import json
import re
import urllib.request

RFID_URL = "https://raw.githubusercontent.com/queengooborg/Bambu-Lab-RFID-Library/main/README.md"
SPOOLMAN_URL = "https://donkie.github.io/SpoolmanDB/filaments.json"
BAMBU_COLORS_URL = "https://raw.githubusercontent.com/bambulab/BambuStudio/master/resources/profiles/BBL/filament/filaments_color_codes.json"

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


def parse_spoolman(filaments: list[dict]) -> dict[str, list[dict]]:
    """Build index: material -> [bambulab entries]."""
    index: dict[str, list[dict]] = {}
    for f in filaments:
        if f.get("id", "").startswith("bambulab_"):
            index.setdefault(f["material"], []).append(f)
    return index


def parse_bambu_colors(data: dict) -> dict[str, dict]:
    """Build index: filament_code -> {name, color_hex}."""
    index = {}
    for e in data.get("data", []):
        code = e.get("fila_color_code", "")
        name = e.get("fila_color_name", {}).get("en", "")
        if not code or not name:
            continue
        colors = e.get("fila_color", [])
        color_hex = colors[0][1:7] if colors and len(colors[0]) >= 7 else None
        index[code] = {"name": name, "color_hex": color_hex}
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


def find_spoolman_match(section: str, color: str, spoolman: dict) -> tuple[str | None, str | None, str | None]:
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

    return None, None, None


# --- Main ---


def main():
    print("Downloading sources...")
    rfid_entries = parse_rfid_readme(download(RFID_URL))
    spoolman = parse_spoolman(json.loads(download(SPOOLMAN_URL)))
    bambu_names = parse_bambu_colors(json.loads(download(BAMBU_COLORS_URL)))

    spoolman_count = sum(len(v) for v in spoolman.values())
    print(f"\nParsed {len(rfid_entries)} RFID entries, "
          f"{spoolman_count} SpoolmanDB entries, "
          f"{len(bambu_names)} BambuStudio colors")

    # Track unknown sections
    unknown_sections = {e["section"] for e in rfid_entries if e["section"] not in MATERIAL_MAP}

    # Match and build results
    results = []
    seen = set()

    for entry in rfid_entries:
        if entry["variant_id"] in seen:
            continue
        seen.add(entry["variant_id"])

        spoolman_id, spoolman_name, spoolman_hex = find_spoolman_match(entry["section"], entry["color"], spoolman)

        # Name priority: BambuStudio official > SpoolmanDB > constructed
        bambu_info = bambu_names.get(entry["code"])
        color_name = (
            (bambu_info["name"] if bambu_info else None)
            or spoolman_name
            or build_display_name(entry["section"], entry["color"])
        )

        # Hex priority: BambuStudio official > SpoolmanDB
        color_hex = (bambu_info["color_hex"] if bambu_info else None) or spoolman_hex

        result = {
            "id": entry["variant_id"],
            "code": entry["code"],
            "material": entry["section"],
            "color_name": color_name,
        }
        if color_hex:
            result["color_hex"] = color_hex
        result["spoolman_id"] = spoolman_id
        results.append(result)

    # Write output
    results.sort(key=lambda x: x["id"])
    with open("bambu_variants.json", "w") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
        f.write("\n")

    # Stats
    matched = [r for r in results if r["spoolman_id"]]
    unmatched = [r for r in results if not r["spoolman_id"]]

    print(f"\n{'=' * 50}")
    print(f"Total: {len(results)} | Matched: {len(matched)} | Unmatched: {len(unmatched)}")
    print(f"{'=' * 50}")

    if unknown_sections:
        print(f"\nUnknown RFID sections (not in MATERIAL_MAP):")
        for s in sorted(unknown_sections):
            print(f"  - {s}")

    if unmatched:
        print(f"\nUnmatched entries:")
        by_mat: dict[str, list] = {}
        for r in unmatched:
            by_mat.setdefault(r["material"], []).append(r)
        for mat in sorted(by_mat):
            names = ", ".join(f'{r["color_name"]} ({r["id"]})' for r in by_mat[mat])
            print(f"  {mat}: {names}")

    print(f"\nWrote bambu_variants.json")


if __name__ == "__main__":
    main()
