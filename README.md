# bambu-spoolman-db

Mapping between Bambu Lab RFID variant IDs and [SpoolmanDB](https://github.com/Donkie/SpoolmanDB) filament IDs.

The `variant_id` is read from the RFID tag embedded in Bambu Lab spools (Block 1, bytes 0-7) and is also available via MQTT as `tray_id_name`. This mapping lets you look up the full filament metadata (material, color, temperatures, etc.) from a scanned spool.

## Usage

```bash
python3 generate.py
```

No external dependencies — Python 3.10+ stdlib only.

## Data sources

| Source | Used for |
|--------|----------|
| [queengooborg/Bambu-Lab-RFID-Library](https://github.com/queengooborg/Bambu-Lab-RFID-Library) | RFID variant IDs, filament codes, material types |
| [Donkie/SpoolmanDB](https://github.com/Donkie/SpoolmanDB) | Filament IDs, color names |
| [bambulab/BambuStudio](https://github.com/bambulab/BambuStudio) `filaments_color_codes.json` | Official color names (fallback) |

## JSON format

Each entry in `bambu_variants.json`:

```json
{
  "variant_id": "A01-B6",
  "color_name": "Matte Dark Blue",
  "material": "PLA Matte",
  "filament_code": "11602",
  "spoolmandb_id": "bambulab_pla_mattedarkblue_1000_175_n"
}
```

| Field | Description |
|-------|-------------|
| `variant_id` | RFID tag identifier (Block 1, bytes 0-7) / MQTT `tray_id_name` |
| `color_name` | Display name (from SpoolmanDB when matched, BambuStudio official otherwise) |
| `material` | Material type as listed in the RFID library |
| `filament_code` | Bambu Lab 5-digit product code |
| `spoolmandb_id` | SpoolmanDB filament ID, or `null` if not yet in SpoolmanDB |

## How matching works

1. Parse RFID library for variant IDs grouped by material section (e.g. "PLA Matte", "PETG HF")
2. Map each section to the corresponding SpoolmanDB material + name prefix (e.g. "PLA Matte" + "Dark Blue" -> "Matte Dark Blue")
3. Match against SpoolmanDB entries using: exact name -> normalized name -> Grey/Gray swap -> partial match (for multi-color names with parentheses)
4. Color names come from SpoolmanDB when matched, otherwise from BambuStudio's official `filaments_color_codes.json`, otherwise constructed from the RFID library data
