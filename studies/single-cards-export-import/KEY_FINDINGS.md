# Single Card & Dashboard Export/Import - Key Findings Summary

## Quick Overview

I've completed a **comprehensive deep-dive analysis** of the Metabase migration toolkit to assess what's needed for single-card and single-dashboard export/import.

### Bottom Line
✅ **HIGHLY FEASIBLE** - Medium complexity, ~9-13 hours implementation time, ~230 lines of code

---

## THE DEPENDENCY GRAPH (What Each Item References)

### What a Card Contains & References

**Card JSON structure** (`lib/models_core.py:28-39`):
- `id`, `name`, `collection_id`, `database_id`, `archived`, `type`, `dataset`
- **CRITICAL**: `dataset_query` - the query definition

**Card dependencies** come from `dataset_query` (`lib/services/export_service.py:340-406`):
1. **MBQL v56**: `source-table: "card__123"` string references
2. **MBQL v57**: `source-card: 123` integer references in stages/joins
3. **Native SQL**: `{{#123-model-name}}` references
4. **Saved metrics**: `["metric", {...}, 123]` in aggregations
5. **Template tags**: `card-id` in template_tags

### What a Dashboard Contains & References

**Dashboard JSON contains** (`lib/services/export_service.py:604-622`):
- `dashcards[]` - the card placements
- `parameters[]` - filter definitions
- `tabs[]` - for tabbed dashboards (v57)

**Dashboard dependencies**:
1. **DashCards**: `dashcard.card_id` references
2. **Series**: `dashcard.series[].id` references
3. **Parameters**: `parameter.values_source_config.card_id` references
4. **Embedded cards**: `dashcard.card` object (for "Visualize another way")

**Key insight**: Dashboards have NO direct dependencies. ALL dependencies come through referenced cards.

---

## COLLECTIONS: The Hidden Critical Dependency

### The Problem
- Every card/dashboard has a `collection_id` pointing to its parent
- Collections are hierarchical (parent_id references)
- If exporting card in collection 5, need:
  - Collection 5 (parent of card)
  - Collection 3 (parent of 5)
  - Collection 1 (parent of 3, the root)

### The Solution: Minimal Collection Tree
Need new method `_build_minimal_collection_tree(collection_id)` that:
1. Fetches the target collection
2. Recursively fetches parent collections  
3. Creates Collection objects for the chain
4. Exports _collection.json metadata for each
5. Builds `_collection_path_map` and manifest entries

---

## IMPORT SIDE: Already Perfect for This Use Case

### Why Zero Import Changes Needed

The import service (`lib/services/import_service.py:87-361`) already:

1. **Loads arbitrary manifests** - doesn't check if full or partial
2. **Imports what's listed** - only processes `manifest.cards`, `manifest.dashboards`
3. **Handles dependencies** - CardHandler does topological sort
4. **Remaps all IDs** via IDMapper

**Import order** (`lib/services/import_service.py:340-351`):
1. Import collections (must be first)
2. Prefetch collection items (for conflict detection)
3. Import cards (topological sort ensures dependencies first)
4. Import dashboards (can reference cards now)
5. Apply permissions (if requested)

This order works **perfectly** for single card/dashboard exports.

---

## REQUIRED CODE CHANGES

### 1. lib/config.py - ADD ~50 lines

**ExportConfig class** (lines 132-207):
- Add `card_ids: list[int] | None = None`
- Add `dashboard_ids: list[int] | None = None`
- Add validators (follow pattern of `root_collection_ids` validator at lines 174-191)

**get_export_args()** (lines 288-391):
- Add `--card-ids ID1,ID2,...` argument parsing
- Add `--dashboard-ids ID1,ID2,...` argument parsing

### 2. lib/services/export_service.py - ADD ~100 lines

**New method** `_build_minimal_collection_tree(collection_id: int | None)`:
- Fetch collection via `client.get_collection(collection_id)`
- Recursively fetch parent
- Create Collection objects
- Add to manifest.collections

**New method** `run_export_single_card(card_id: int)`:
- Build minimal collection tree
- Call `_export_card_with_dependencies()`
- Fetch databases
- Write manifest

**New method** `run_export_single_dashboard(dashboard_id: int)`:
- Build minimal collection tree
- Export all cards from dashcards and parameters
- Call `_export_dashboard()`
- Fetch databases
- Write manifest

**Modify** `run_export()` (lines 82-145):
Route to appropriate method based on config

### 3. export_metabase.py - MODIFY ~5 lines

Minor routing updates

---

## ZERO CHANGES NEEDED FOR:
- `lib/handlers/card.py` - Import logic already perfect
- `lib/handlers/dashboard.py` - Import logic already perfect  
- `lib/handlers/collection.py` - Import logic already perfect
- `lib/remapping/id_mapper.py` - Works with any manifest
- `lib/remapping/query_remapper.py` - Works with any card data
- `import_metabase.py` - No changes needed

---

## COMPLEXITY ASSESSMENT

### Lines of Code Changes
- **New code**: ~150 lines (export service methods)
- **Modified code**: ~50 lines (config, CLI, routing)
- **Total net change**: +200 lines

### Backward Compatibility
✅ 100% maintained - all changes are additive

---

## ESTIMATED EFFORT

| Phase | Hours | Notes |
|-------|-------|-------|
| Config changes | 1-2 | Straightforward, pattern exists |
| Export service methods | 3-4 | Mostly reusing existing logic |
| Testing | 4-6 | Multiple scenarios |
| Code review + refinement | 1-2 | Polish, edge cases |
| **Total** | **9-14** | Medium complexity |

---

## CONCLUSION

**RECOMMENDATION: PROCEED WITH IMPLEMENTATION**

Why this is feasible:
- ✅ Dependency extraction already works correctly
- ✅ Import side can handle arbitrary manifests  
- ✅ Collection tree can be reversed into minimal form
- ✅ All ID remapping infrastructure in place
- ✅ ~70% code reuse from existing functions

**Estimated time to MVP**: 2-3 days
**Risk level**: Low (lots of code reuse)
**User value**: High (solves real use case)

---

## DETAILED ANALYSIS

For complete details, see: `single_card_dashboard_analysis.md` (988 lines, 31KB)
