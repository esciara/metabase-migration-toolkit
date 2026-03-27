# Executive Summary: Export/Import Granularity Analysis

## Overview

This analysis investigates the granularity of the export/import/sync feature in the Metabase Migration Toolkit. The key finding is that the feature operates at the **collection level as its minimum scope** — you cannot export individual cards or dashboards independently.

---

## Quick Answers to Core Questions

### 1. Can you export/import a single card or dashboard?
**NO.** The minimum exportable scope is a **collection**. You cannot export just one card or one dashboard independently. All cards and dashboards within a collection are exported together.

### 2. How is the scope of export determined?
Via the `--root-collections` CLI argument, which accepts comma-separated collection IDs. If not specified, defaults to exporting all collections.

### 3. Is there a `root_collection` parameter?
**YES**, it's called `root_collection_ids` (plural):
- **Type**: `list[int] | None`
- **CLI**: `--root-collections 1,2,5` (comma-separated)
- **Default**: `None` (exports all)
- **Effect**: Filters collections before processing; all items within filtered collections are included

### 4. What's the minimum scope you can export?
A single **collection** with all of its contents. You cannot selectively export cards or dashboards within a collection.

### 5. Does the export service iterate over all collections or target individual items?
- **Collections**: Iterates over all (filtered by `root_collection_ids`)
- **Items**: Within each collection, iterates over ALL cards and dashboards
- **Per-item targeting**: ❌ Not available

### 6. Is there filtering by card ID, dashboard ID, or individual item selection?
**NO.** Only filtering mechanisms:
- Collection ID via `--root-collections`
- Item type toggles: `--include-dashboards`, `--include-archived`, `--include-permissions` (all-or-nothing)

### 7. Are there TODOs or feature requests for single-item export?
**NO.** No feature requests or planned enhancements for per-card or per-dashboard export found in the codebase.

---

## Key Findings

### Export Granularity
- **Minimum scope**: Collection
- **Filtering mechanism**: `--root-collections` (CLI argument)
- **No card-level filtering**: All cards in scoped collections are exported
- **No dashboard-level filtering**: All dashboards in scoped collections are exported (if `--include-dashboards` is set)
- **Dependency handling**: Transitive dependencies are auto-exported even if outside scope

### Import Granularity
- **Has NO scoping parameters**: Import always imports everything in the manifest
- **Cannot selectively import**: No way to exclude specific collections, cards, or dashboards
- **Conflict resolution**: Has strategies (skip/overwrite/rename) but no filtering

### Sync Behavior
- **Combines export + import**: Exports with `--root-collections`, imports everything from resulting manifest
- **Import is always full**: No way to selectively import after export

---

## Configuration Parameters Summary

### Export Parameters
| Parameter | Type | Effect | Granularity |
|-----------|------|--------|-------------|
| `--root-collections` | Collection IDs | Filters collections | ✅ Useful |
| `--include-dashboards` | Boolean toggle | Include/exclude all dashboards | 🔄 All-or-nothing |
| `--include-archived` | Boolean toggle | Include/exclude all archived items | 🔄 All-or-nothing |
| `--include-permissions` | Boolean toggle | Include/exclude all permissions | 🔄 All-or-nothing |

### Import Parameters
| Parameter | Type | Effect | Scope Control |
|-----------|------|--------|--------|
| `--conflict` | skip/overwrite/rename | Conflict resolution | N/A |
| `--dry-run` | Boolean | Simulation mode | N/A |
| `--include-archived` | Boolean toggle | Include/exclude archived items | 🔄 All-or-nothing |
| `--apply-permissions` | Boolean toggle | Include/exclude permissions | 🔄 All-or-nothing |
| **NO collection filtering** | **N/A** | **Cannot scope import** | ❌ Missing |

---

## Architecture Overview

```
Export Flow:
  CLI: --root-collections 1,2
    ↓
  ExportConfig.root_collection_ids = [1, 2]
    ↓
  ExportService.run_export()
    ├─ Fetch all collections
    ├─ Filter: keep only [1, 2]
    └─ _traverse_collections()
        ├─ For Collection 1:
        │   ├─ _process_collection_items()
        │   │   └─ Export ALL cards and dashboards
        │   └─ Recursively process children
        └─ For Collection 2: (same)
    ↓
  Result: Manifest with Collections 1, 2 + ALL their items

Import Flow:
  CLI: (no scoping parameters)
    ↓
  ImportService.run_import()
    ├─ Load manifest.json
    └─ _perform_import()
        ├─ _import_collections() → ALL collections in manifest
        ├─ _import_cards() → ALL cards in manifest
        └─ _import_dashboards() → ALL dashboards in manifest
    ↓
  Result: Target has everything from manifest (no selective import)
```

---

## Limitations

### 1. No Per-Card Export
- Cannot export individual cards
- Cannot exclude specific cards from a collection
- Dependencies are auto-exported (may expand scope unexpectedly)

### 2. No Per-Dashboard Export
- Cannot export individual dashboards
- `--include-dashboards` is all-or-nothing toggle

### 3. No Per-Item Import
- Cannot selectively import from a manifest
- No way to exclude collections, cards, or dashboards during import
- Conflict resolution is the only control available

### 4. No Tag-Based or Name-Based Filtering
- Cannot filter by card/dashboard name
- Cannot filter by tags or other metadata

### 5. Import Cannot Scope to Subset
- Export can be scoped with `--root-collections`
- Import cannot be scoped at all
- Must either import all or manually edit manifest before import

---

## Design Rationale

The collection-level granularity reflects Metabase's architectural design:
1. **Metabase organizes content by collections**: Collections are the primary organizational unit
2. **Dependency complexity**: Cards can depend on other cards, cascading exports
3. **Manifest-driven approach**: Entire exports produce a manifest describing all items
4. **Use case alignment**: Most use cases involve exporting/importing entire departments or teams (organized as separate collections)

---

## Workarounds for Finer Granularity

### To Export Specific Cards
**Option 1: Reorganize collections**
1. Move desired cards to a dedicated collection in the source
2. Export that collection with `--root-collections <id>`
3. Import to target

**Option 2: Manual manifest editing (advanced)**
1. Export all (or relevant collections)
2. Manually edit `manifest.json` to remove unwanted items
3. Ensure dependency integrity before import
4. Import the modified manifest

### To Import Specific Cards
**Option 1: Create separate exports**
1. Export only the collection(s) you want to import
2. Import that specific export

**Option 2: Manual manifest editing (advanced)**
1. Export everything
2. Edit `manifest.json` before import
3. Ensure all dependencies are included
4. Run import

---

## Code Locations

| Purpose | File | Lines |
|---------|------|-------|
| Export configuration | lib/config.py | 132-192 |
| Import configuration | lib/config.py | 210-286 |
| Sync configuration | lib/config.py | 500-665 |
| Export entry point | lib/services/export_service.py | 82-145 |
| Collection filtering | lib/services/export_service.py | 96-103 |
| Collection traversal | lib/services/export_service.py | 189-263 |
| Collection items processing | lib/services/export_service.py | 265-300 |
| Import entry point | lib/services/import_service.py | 87-108 |
| Import execution | lib/services/import_service.py | 304-361 |
| CLI export args | lib/config.py | 288-391 |
| CLI import args | lib/config.py | 394-497 |
| CLI sync args | lib/config.py | 668-834 |

---

## Conclusion

The export/import/sync feature is designed around **collection-level granularity**. This is a deliberate architectural decision that aligns with Metabase's organizational model. There is no mechanism to export or import individual cards or dashboards, nor are there any planned enhancements for this capability.

Users who need finer-grained control must either:
1. Reorganize collections in the source before export
2. Manually edit manifest.json files (advanced)
3. Request this feature for future implementation

For most use cases involving migrating departments, teams, or projects (organized as separate collections), the current granularity is appropriate and sufficient.

---

## Related Documentation

- **EXPORT_IMPORT_GRANULARITY_ANALYSIS.md**: Complete detailed analysis with examples
- **CODE_REFERENCES.md**: Exact code locations and method signatures
- **QUICK_REFERENCE.txt**: One-page summary with examples and parameters
