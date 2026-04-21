# Bambu Filaments

A catalog of Bambu Lab filaments, keyed by RFID variant ID with official color names, hex codes, and cross-references to other filament databases.

Browse the catalog at [piitaya.github.io/bambu-filaments](https://piitaya.github.io/bambu-filaments/).

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
  "sku": "11602",
  "material": "PLA",
  "product": "PLA Matte",
  "color_name": "Dark Blue",
  "color_hex": "042F56FF",
  "color_hexes": ["042F56FF"],
  "weight": 1000,
  "temp_min": 190,
  "temp_max": 230,
  "integrations": {
    "spoolman": "bambulab_pla_mattedarkblue_1000_175_n"
  }
}
```

| Field | Description |
| ----- | ----------- |
| `id` | Variant ID from the RFID tag (AMS `tray_id_name`) |
| `sku` | Bambu Lab 5-digit product code (not on the tag, cross-referenced from BambuStudio) |
| `material` | Broad material type from tag block 2, e.g. `PLA`, `PETG` |
| `product` | Detailed product from tag block 4, e.g. `PLA Matte`, `PETG HF` |
| `color_name` | Official Bambu Lab color name (not on the tag, from BambuStudio) |
| `color_hex` | 8-char `RRGGBBAA` hex, uppercase. Alpha `FF` for opaque, lower for translucent filaments |
| `color_hexes` | Array of all colors; one entry for single-color, two for gradient/multi-color |
| `weight` | Spool weight in grams, `null` if unknown |
| `temp_min` / `temp_max` | Nozzle temperature range in °C, `null` if unknown |
| `integrations.spoolman` | SpoolmanDB filament ID (`null` if not yet in SpoolmanDB) |

## Regenerate

```bash
python3 generate.py
```

Python 3.10+, no external dependencies.

The script downloads three sources, cross-references them, and outputs `filaments.json`.

## Adding a missing filament

If a variant ID isn't in the upstream RFID library yet, add it to [`manual_additions.json`](manual_additions.json):

```json
[
  {
    "id": "A00-B9",
    "product": "PLA Basic",
    "color_hex": "0A2989FF"
  }
]
```

| Field | Required | Description |
| ----- | -------- | ----------- |
| `id` | yes | Variant ID from the RFID tag |
| `product` | yes | Detailed product name (e.g. `PLA Basic`, `PETG HF`) |
| `color_hex` | yes | 6 or 8-char hex (normalized to `RRGGBBAA`) |
| `sku`, `color_name`, `integrations.spoolman` | no | Override the auto-lookups |

Provide optional fields explicitly to override the auto-lookups (useful when the hex isn't in BambuStudio, or when SpoolmanDB matching picks the wrong entry). If upstream later adds the same variant ID, the upstream entry wins — you can then drop the manual entry.

## Data sources

| Source | What it provides |
| ------ | ---------------- |
| [queengooborg/Bambu-Lab-RFID-Library](https://github.com/queengooborg/Bambu-Lab-RFID-Library) | Variant IDs from real RFID tag dumps (block 1 = variant ID, block 4 = material, block 5 = color hex) plus a README mapping variant IDs to Bambu's 5-digit product codes |
| [bambulab/BambuStudio](https://github.com/bambulab/BambuStudio) | Official color names and hex codes ([`filaments_color_codes.json`](https://github.com/bambulab/BambuStudio/blob/master/resources/profiles/BBL/filament/filaments_color_codes.json)) |
| [Donkie/SpoolmanDB](https://github.com/Donkie/SpoolmanDB) | Filament IDs for Spoolman integration |

## How matching works

1. Clone the RFID library, walk every `*-dump.json`, extract variant ID, material and color hex from each tag (one entry per unique variant)
2. Look up the 5-digit product code from the upstream README; when a variant has multiple codes (re-released SKUs), pick the one whose BambuStudio hex matches the tag hex
3. Find the SpoolmanDB filament: exact name, normalized name, Grey/Gray swap, match after stripping parenthesized suffixes, then hex code as a last resort
4. Color names use BambuStudio's official names when available, with SpoolmanDB as fallback
