# Export/Import Granularity Quick Reference

## Core Findings

### 1. Minimum Scope: Collections (not individual cards or dashboards)
- Cannot export: single card, single dashboard, or subset of collection
- CAN export: entire collection(s) with all their contents

### 2. Only Scoping Parameter: `root_collection_ids`
- **Type:** `list[int] | None`
- **CLI:** `--root-collections ID1,ID2,ID3`
- **Default:** `None` (exports all collections)
- **Affects:** COLLECTION level only
- **Limitation:** All cards/dashboards in scoped collections are included

### 3. Import Has No Scoping
- Import always imports everything in the manifest
- No way to selectively import subsets
- No `--root-collections` equivalent for import

### 4. Dependencies Auto-Export
- If a card depends on another card, both are exported
- Can expand scope beyond `--root-collections`
- Outside-scope dependencies go to `dependencies/` folder

### 5. No Single-Item Export Feature
- No TODOs or feature requests found
- Not planned for implementation
- Code uses "single" word only for internal processing

---

## Configuration Parameters

### Export

| Parameter | Type | Description |
|---|---|---|
| `--root-collections N,M,K` | ✅ Useful | Collection ID filtering |
| `--include-dashboards` | 🔄 Binary toggle | All-or-nothing toggle |
| `--include-archived` | 🔄 Binary toggle | All-or-nothing toggle |
| `--include-permissions` | 🔄 Binary toggle | All-or-nothing toggle |

### Import

| Parameter | Type | Description |
|---|---|---|
| `--conflict skip\|overwrite\|rename` | ✅ Useful | Conflict resolution |
| `--dry-run` | ✅ Useful | Simulation mode |
| `--include-archived` | 🔄 Binary toggle | All-or-nothing toggle |
| `--apply-permissions` | 🔄 Binary toggle | All-or-nothing toggle |
| NO scoping parameters | ❌ Missing | Not available |

### Sync

| Parameter | Type | Description |
|---|---|---|
| `--root-collections N,M,K` | ✅ Useful | Export filtering |
| `--conflict skip\|overwrite\|rename` | ✅ Useful | Import conflict resolution |
| `--dry-run` | ✅ Useful | Simulation mode |
| `--include-dashboards` | 🔄 Binary toggle | All-or-nothing toggle |
| `--include-archived` | 🔄 Binary toggle | All-or-nothing toggle |
| `--include-permissions` | 🔄 Binary toggle | All-or-nothing toggle |

> **Key:** ✅ Useful | 🔄 Binary toggle | ❌ Missing/Not available

---

## Examples

**Export single collection:**
```bash
python export_metabase.py --source-url ... --root-collections 42 --export-dir ./out
```

**Export multiple collections:**
```bash
python export_metabase.py --source-url ... --root-collections 1,2,5 --export-dir ./out
```

**Export everything:**
```bash
python export_metabase.py --source-url ... --export-dir ./out
```

**Export with dashboards:**
```bash
python export_metabase.py --source-url ... --include-dashboards --export-dir ./out
```

**Import all:**
```bash
python import_metabase.py --target-url ... --export-dir ./out --db-map db_map.json
```

**Import with dry-run:**
```bash
python import_metabase.py --target-url ... --export-dir ./out --db-map db_map.json --dry-run
```

**Sync with collection filtering:**
```bash
python sync_metabase.py --source-url ... --target-url ... --root-collections 1,2 --export-dir ./out --db-map db_map.json
```

---

## Workarounds for Finer Granularity

### To export specific cards:
1. Move cards to dedicated collection, export that collection
2. Export all, manually edit `manifest.json` to remove unwanted items
3. Request feature - currently not planned

### To import specific cards:
1. Create separate export with only desired collections
2. Manually edit `manifest.json` before import
3. Request feature - currently not implemented

---

## Key Code Locations

### Config definitions
- **ExportConfig:** `lib/config.py` lines 132-192
- **ImportConfig:** `lib/config.py` lines 210-286
- **SyncConfig:** `lib/config.py` lines 500-665

### Export service
- **run_export():** `lib/services/export_service.py` lines 82-145
- **_traverse_collections():** lines 189-263
- **_process_collection_items():** lines 265-300
- **Collection filtering:** lines 96-103

### Import service
- **run_import():** `lib/services/import_service.py` lines 87-108
- **_perform_import():** lines 304-361
- **Import all collections:** line 340
- **Import all cards:** line 347
- **Import all dashboards:** lines 348-349

### CLI arguments
- **get_export_args():** `lib/config.py` lines 288-391
- **get_import_args():** `lib/config.py` lines 394-497
- **get_sync_args():** `lib/config.py` lines 668-834

---

## Related Documents

| Document | Size | Contents |
|---|---|---|
| `tmp/EXPORT_IMPORT_GRANULARITY_ANALYSIS.md` | 19 KB | Detailed findings with code examples, import/export flows, design decisions and limitations, configuration examples |
| `tmp/CODE_REFERENCES.md` | 10 KB | Exact file locations and line numbers, method signatures, architecture summary |
| `tmp/QUICK_REFERENCE.md` | - | This file |