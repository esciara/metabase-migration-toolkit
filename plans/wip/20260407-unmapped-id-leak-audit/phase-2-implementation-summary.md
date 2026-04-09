# Phase 2: Tier 1 Fixes — Implementation Summary

**Status:** Complete
**Date:** 2026-04-09
**CI:** `make ci` passes — 785 passed, 81 skipped, coverage 86.90%

---

## Production code changes (`lib/remapping/query_remapper.py`)

Added import for `CardMappingError`, `FieldMappingError`, `TableMappingError` from `lib.errors`.

Added `raise` branches to **10 leak sites** across 7 methods. Each site follows the pattern:
- If `resolve_*()` returns `None` and mode is not `force` → raise specific `MappingError` subclass
- If mode is `force` → log warning and keep original ID

| Fix | Method | Error Type | Location string |
|-----|--------|------------|-----------------|
| 2.1 | `_remap_list()` | `FieldMappingError` | `v57 MBQL field reference (data[2])` |
| 2.2 | `_remap_list()` | `FieldMappingError` | `v56 MBQL field reference (data[1])` |
| 2.3 | `_remap_source_table()` | `TableMappingError` | `dataset_query source-table` |
| 2.4 | `_remap_joins()` | `TableMappingError` | `join clause source-table` |
| 2.5 | `_remap_source_table()` | `CardMappingError` | `query source-card (v57)` |
| 2.6 | `_remap_card_reference()` | `CardMappingError` | `v56 card reference '...' in ...` |
| 2.7 | `_remap_joins()` | `CardMappingError` | `join clause source-card (v57)` |
| 2.8 | `_remap_list()` | `CardMappingError` | `MBQL metric reference (data[2])` |
| 2.9 | `_remap_sql_card_references()` | `CardMappingError` | `native SQL reference '...'` |
| 2.10 | `_remap_template_tags()` | `CardMappingError` | `template-tag '...' card-id` |
| 2.11 | `remap_dashcard_parameter_mappings()` | `CardMappingError` | `dashcard parameter_mapping card_id` |

---

## New tests (`tests/test_query_remapper.py`) — 14 tests, all passing

### Raise tests (11) — verify unmapped IDs raise the correct MappingError subclass

| Test | Leak | Error Type |
|------|------|------------|
| `test_remap_list_v57_field_unmapped_raises` | 1.1 | `FieldMappingError` |
| `test_remap_list_v56_field_unmapped_raises` | 1.2 | `FieldMappingError` |
| `test_remap_source_table_unmapped_raises` | 2.2 | `TableMappingError` |
| `test_remap_joins_table_unmapped_raises` | 2.3 | `TableMappingError` |
| `test_remap_source_table_v57_card_unmapped_raises` | 3.1 | `CardMappingError` |
| `test_remap_card_reference_v56_unmapped_raises` | 3.2 | `CardMappingError` |
| `test_remap_joins_v57_card_unmapped_raises` | 3.3 | `CardMappingError` |
| `test_remap_list_metric_unmapped_raises` | 3.4 | `CardMappingError` |
| `test_remap_sql_card_ref_unmapped_raises` | 3.5 | `CardMappingError` |
| `test_remap_template_tags_card_unmapped_raises` | 3.6 | `CardMappingError` |
| `test_remap_dashcard_param_card_unmapped_raises` | 3.7 | `CardMappingError` |

### Force-mode tests (3) — verify `force` mode preserves original ID without raising

| Test | Leak |
|------|------|
| `test_remap_list_v57_field_force_mode_keeps` | 1.1 |
| `test_remap_source_table_force_mode_keeps` | 2.2 |
| `test_remap_card_reference_force_mode_keeps` | 3.2 |

---

## Existing tests updated

### `tests/test_import.py` (4 tests)

These tests had incidental unmapped IDs in their fixtures — the tests' purpose was unrelated to remapping behavior (database field setting, dataset flag preservation). Fixed by adding the missing mappings to the IDMapper.

| Test | Fix applied |
|------|-------------|
| `test_remap_card_query_always_sets_database_field` | Added `card_mapping={50: 500}` to `id_mapper` fixture |
| `test_remap_card_query_with_existing_database_field` | Same fixture fix |
| `test_import_model_preserves_dataset_field` | Added `table_map[(2,15)]=115`, `field_map[(2,20-23)]=120-123` after `_load_export_package()` |
| `test_import_question_without_dataset_field` | Added `table_map[(2,10)]=110`, `field_map[(2,3)]=103`, `field_map[(2,5)]=105` after `_load_export_package()` |

### `tests/test_native_query_remapping.py` (4 tests)

| Test | Fix applied |
|------|-------------|
| `test_remap_sql_preserves_unmapped_references` | Changed from asserting preserved reference → `pytest.raises(CardMappingError)` |
| `test_remap_template_tags_preserves_unmapped_cards` | Changed from asserting preserved tag → `pytest.raises(CardMappingError)` |
| `test_remap_mbql_v57_joins` | Added `table_map[(1,10)]=1010` to fixture for incidental `source-table: 10` |
| `test_remap_dimension_tag_unmapped_field` | Changed from asserting preserved field ID → `pytest.raises(FieldMappingError)` |

---

## TDD workflow followed

1. **RED:** Wrote all 14 tests first. Ran them: 11 failed (`DID NOT RAISE`), 3 passed (force mode already worked).
2. **GREEN:** Implemented all 11 fixes. All 14 new tests passed. Fixed 8 existing tests that relied on old "silent leak" behavior. `make ci` clean.
