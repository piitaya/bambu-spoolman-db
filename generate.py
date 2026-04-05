#!/usr/bin/env python3
"""Generate bambu_variants.json mapping Bambu Lab RFID variant IDs to SpoolmanDB filament IDs."""

import json
import re
import sys
import urllib.request

RFID_URL = "https://raw.githubusercontent.com/queengooborg/Bambu-Lab-RFID-Library/main/README.md"
SPOOLMAN_URL = "https://donkie.github.io/SpoolmanDB/filaments.json"
BAMBU_COLORS_URL = "https://raw.githubusercontent.com/bambulab/BambuStudio/master/resources/profiles/BBL/filament/filaments_color_codes.json"

# Map RFID section name -> (spoolmandb_material, prefix, suffix)
# None means no SpoolmanDB equivalent
MATERIAL_MAP = {
    # PLA variants
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
    # PETG variants
    "PETG Basic": ("PETG", "", ""),
    "PETG HF": ("PETG", "HF ", ""),
    "PETG Translucent": ("PETG", "", ""),
    "PETG-CF": ("PETG-CF", "", ""),
    # ABS variants
    "ABS": ("ABS", "", ""),
    "ABS-GF": ("ABS-GF", "", ""),
    # ASA variants
    "ASA": ("ASA", "", ""),
    "ASA Aero": ("ASA", "", " Aero"),
    "ASA-CF": ("ASA-CF", "", ""),
    # PC variants
    "PC": ("PC", "", ""),
    "PC FR": ("PC", "FR ", ""),
    # TPU variants
    "TPU for AMS": ("TPU", "For AMS ", ""),
    # PA variants
    "PAHT-CF": ("PAHT-CF", "", ""),
    "PA6-GF": ("PA6-GF", "", ""),
    "PA6-CF": ("PA6-CF", "", ""),
    # Support materials
    "Support for PLA/PETG": ("PLA", "Support for PLA/PETG ", ""),
    "Support for PLA (New Version)": ("PLA", "Support for PLA ", ""),
    "Support for ABS": ("ABS", "Support for ABS", ""),
    "Support for PA/PET": ("PA", "Support for PA/PET", ""),
    "PVA": ("PVA", "", ""),
}

SUPPORT_NO_COLOR = {"Support for ABS", "Support for PA/PET"}

SECTION_RE = re.compile(r"^####\s+\[([^\]]+)\]", re.MULTILINE)
ROW_RE = re.compile(
    r"\|\s*\[([^\]]+)\]\([^)]*\)\s*\|"
    r"\s*(\d+)\s*\|"
    r"\s*([^|]+?)\s*\|"
    r"\s*([^|]*?)\s*\|"
)
VARIANT_ID_RE = re.compile(r"[A-Z]\d+-\w+")
SLASH_RE = re.compile(r"([A-Z]\d+-)(\w+)/(\w+)")


def download(url: str) -> str:
    print(f"  {url}")
    req = urllib.request.Request(url, headers={"User-Agent": "bambu-spoolman-db/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8")


def parse_rfid_readme(markdown: str) -> list[dict]:
    entries = []
    current_section = None

    for line in markdown.split("\n"):
        section_match = SECTION_RE.match(line)
        if section_match:
            current_section = section_match.group(1).strip()
            continue

        if current_section is None:
            continue

        row_match = ROW_RE.search(line)
        if not row_match:
            continue

        color_name = row_match.group(1).strip()
        filament_code = row_match.group(2).strip()
        raw_variant_id = row_match.group(3).strip()

        if raw_variant_id == "?" or raw_variant_id == "":
            continue

        def add(variant_id):
            entries.append({
                "section": current_section,
                "color": color_name,
                "code": filament_code,
                "variant_id": variant_id,
            })

        # "A00-G1/G6" -> two entries
        slash_match = SLASH_RE.match(raw_variant_id)
        if slash_match:
            add(slash_match.group(1) + slash_match.group(2))
            add(slash_match.group(1) + slash_match.group(3))
            continue

        # "S02-W0 (Old: S00-W0)" -> primary + old
        primary = VARIANT_ID_RE.match(raw_variant_id)
        if primary:
            add(primary.group(0))
            old = re.search(r"Old:\s*([A-Z]\d+-\w+)", raw_variant_id)
            if old:
                add(old.group(1))

    return entries


def build_spoolman_index(filaments: list[dict]) -> dict[str, list[dict]]:
    index: dict[str, list[dict]] = {}
    for f in filaments:
        if not f.get("id", "").startswith("bambulab_"):
            continue
        index.setdefault(f["material"], []).append(f)
    return index


def build_bambu_color_index(data: dict) -> dict[str, str]:
    """filament_code -> official English color name."""
    index = {}
    for entry in data.get("data", []):
        code = entry.get("fila_color_code", "")
        name = entry.get("fila_color_name", {}).get("en", "")
        if code and name:
            index[code] = name
    return index


def normalize(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def swap_grey_gray(name: str) -> str:
    if "Grey" in name:
        return name.replace("Grey", "Gray")
    if "Gray" in name:
        return name.replace("Gray", "Grey")
    return name


def construct_display_name(section: str, color: str) -> str:
    config = MATERIAL_MAP.get(section)
    if config is None:
        return color
    _, prefix, suffix = config
    if section in SUPPORT_NO_COLOR:
        return prefix.strip()
    return f"{prefix}{color}{suffix}"


def match_spoolman(section: str, color: str, spoolman_index: dict) -> tuple[str | None, str | None]:
    """Returns (spoolmandb_id, spoolman_name) or (None, None)."""
    config = MATERIAL_MAP.get(section)
    if config is None:
        return None, None

    candidates = spoolman_index.get(config[0], [])
    if not candidates:
        return None, None

    display_name = construct_display_name(section, color)
    norm_target = normalize(display_name)

    # Phase 1: Exact match
    for c in candidates:
        if c["name"] == display_name:
            return c["id"], c["name"]

    # Phase 2: Normalized match
    for c in candidates:
        if normalize(c["name"]) == norm_target:
            return c["id"], c["name"]

    # Phase 3: Grey<->Gray swap
    swapped = swap_grey_gray(display_name)
    if swapped != display_name:
        for c in candidates:
            if c["name"] == swapped or normalize(c["name"]) == normalize(swapped):
                return c["id"], c["name"]

    # Phase 4: Partial match (strip parenthesized parts)
    for c in candidates:
        base_name = re.sub(r"\s*\([^)]*\)", "", c["name"])
        if base_name == display_name or normalize(base_name) == norm_target:
            return c["id"], c["name"]

    return None, None


def main():
    print("Downloading sources...")
    rfid_md = download(RFID_URL)
    spoolman_data = json.loads(download(SPOOLMAN_URL))
    bambu_colors_data = json.loads(download(BAMBU_COLORS_URL))

    rfid_entries = parse_rfid_readme(rfid_md)
    spoolman_index = build_spoolman_index(spoolman_data)
    bambu_names = build_bambu_color_index(bambu_colors_data)

    spoolman_count = sum(len(v) for v in spoolman_index.values())
    print(f"\nParsed {len(rfid_entries)} RFID entries, "
          f"{spoolman_count} SpoolmanDB entries, "
          f"{len(bambu_names)} BambuStudio colors")

    # Track unknown sections
    unknown_sections = set()
    for e in rfid_entries:
        if e["section"] not in MATERIAL_MAP:
            unknown_sections.add(e["section"])

    # Match and build results
    results = []
    seen = set()

    for entry in rfid_entries:
        vid = entry["variant_id"]
        if vid in seen:
            continue
        seen.add(vid)

        spoolman_id, spoolman_name = match_spoolman(
            entry["section"], entry["color"], spoolman_index
        )

        # Name priority: SpoolmanDB > BambuStudio official > constructed
        if spoolman_name:
            color_name = spoolman_name
        elif entry["code"] in bambu_names:
            color_name = bambu_names[entry["code"]]
        else:
            color_name = construct_display_name(entry["section"], entry["color"])

        results.append({
            "variant_id": vid,
            "color_name": color_name,
            "material": entry["section"],
            "filament_code": entry["code"],
            "spoolmandb_id": spoolman_id,
        })

    # Sort and write
    results.sort(key=lambda x: x["variant_id"])
    with open("bambu_variants.json", "w") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
        f.write("\n")

    # Stats
    matched = [r for r in results if r["spoolmandb_id"]]
    unmatched = [r for r in results if not r["spoolmandb_id"]]

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
            names = ", ".join(f'{r["color_name"]} ({r["variant_id"]})' for r in by_mat[mat])
            print(f"  {mat}: {names}")

    print(f"\nWrote bambu_variants.json")


if __name__ == "__main__":
    main()
