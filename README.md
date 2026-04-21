# Bambu Filaments

A catalog of Bambu Lab filaments, keyed by RFID variant ID with official color names, hex codes, and cross-references to other filament databases.

## What is a variant ID?

Every Bambu Lab spool has an RFID tag containing a **variant ID** (e.g. `A01-B6`) that uniquely identifies the filament product (material + color). This ID is:

- Stored on the RFID tag (Block 1, bytes 0-7)
- Available via MQTT as `tray_id_name`

This catalog lets you look up full metadata for a scanned spool, and cross-reference into [SpoolmanDB](https://github.com/Donkie/SpoolmanDB) (and other integrations in the future) when you need data like density and temperatures.

## JSON format

Each entry in [`filaments.json`](filaments.json):

```json
{
  "id": "A01-B6",
  "code": "11602",
  "material": "PLA Matte",
  "color_name": "Dark Blue",
  "color_hex": "042F56",
  "integrations": {
    "spoolman": "bambulab_pla_mattedarkblue_1000_175_n"
  }
}
```

| Field | Description |
| ----- | ----------- |
| `id` | Variant ID from the RFID tag / MQTT `tray_id_name` |
| `code` | Bambu Lab 5-digit product code |
| `material` | Material type (e.g. PLA Basic, PLA Matte, PETG HF) |
| `color_name` | Official Bambu Lab color name |
| `color_hex` | Hex color code (absent if unknown) |
| `integrations.spoolman` | SpoolmanDB filament ID (`null` if not yet in SpoolmanDB) |

## Regenerate

```bash
python3 generate.py
```

Python 3.10+, no external dependencies.

The script downloads three sources, cross-references them, and outputs `filaments.json`.

## Data sources

| Source | What it provides |
| ------ | ---------------- |
| [queengooborg/Bambu-Lab-RFID-Library](https://github.com/queengooborg/Bambu-Lab-RFID-Library) | Variant IDs, filament codes, material types (crowd-sourced from RFID scans) |
| [bambulab/BambuStudio](https://github.com/bambulab/BambuStudio) | Official color names and hex codes ([`filaments_color_codes.json`](https://github.com/bambulab/BambuStudio/blob/master/resources/profiles/BBL/filament/filaments_color_codes.json)) |
| [Donkie/SpoolmanDB](https://github.com/Donkie/SpoolmanDB) | Filament IDs for Spoolman integration |

## How matching works

1. Parse the RFID library README for variant IDs, grouped by material section (PLA Matte, PETG HF, etc.)
2. Map each section to the corresponding SpoolmanDB material and construct the expected name (e.g. PLA Matte + "Dark Blue" -> "Matte Dark Blue" in SpoolmanDB)
3. Match against SpoolmanDB using: exact name, normalized name, Grey/Gray swap, match after stripping parenthesized suffixes, then hex code as a last resort
4. Color names use BambuStudio's official names when available, with SpoolmanDB as fallback
