# Phase 4 Progress Report — RED Phase Complete

**Date:** 2026-04-09
**Branch:** `trying-expanding-features`
**Status:** RED phase done — 8 failing tests written, ready for GREEN implementation.

## What was done

### Tests written (RED phase)

All tests follow the plan spec in `plans/wip/20260407-unmapped-id-leak-audit/phase-4-report.md`.

#### `tests/test_models_core.py` — 3 new tests added to existing `TestUnmappedIDCollectorToReportDict` class

| Test | What it asserts (fails because `to_report_dict()` returns old flat structure) |
|---|---|
| `test_unmapped_id_collector_to_report_dict_grouping` | Output has `by_type` wrapper with `count`/`items` per id_type |
| `test_unmapped_id_collector_to_report_dict_action_summary` | Output has `action_summary` with `entities_skipped`, `fields_stripped`, `total_unmapped_ids` |
| `test_unmapped_id_collector_to_report_dict_dedup` | Same source ID affecting 3 entities → 1 item with 3 `affected_entities`; entity keys use plan names (`source_id`, `name`, `action_taken`) |

#### `tests/test_id_mapper.py` — new file, 5 tests in 2 classes

| Test | What it asserts (fails because methods don't exist on IDMapper) |
|---|---|
| `test_get_source_field_context` | Returns `"table 'region_department', column 'num_dep'"` |
| `test_get_source_field_context_not_found` | Returns `None` for unknown field ID |
| `test_get_source_field_context_unknown_db` | Returns `None` for unknown database ID |
| `test_get_source_table_context` | Returns `"table 'region_department'"` |
| `test_get_source_table_context_not_found` | Returns `None` for unknown table ID |

#### `tests/test_query_remapper.py` — 1 regression test added

| Test | Status |
|---|---|
| `test_regression_field_100294_dept_filter` | ✅ **PASSES already** — regression guard for existing behavior from Phase 2 (`_remap_template_tags` → `_remap_list` → `FieldMappingError`) |

### Verification command (RED)

```bash
uv run pytest tests/test_models_core.py tests/test_id_mapper.py tests/test_query_remapper.py -v \
  -k "to_report_dict_grouping or to_report_dict_action_summary or to_report_dict_dedup or source_field_context or source_table_context or regression_field_100294" \
  --no-header --tb=short --no-cov
# Result: 8 FAILED, 1 PASSED
```

## What remains (GREEN phase)

### 4.1 — Implement `to_report_dict()` body in `lib/models_core.py`

The current implementation (lines 245-290) returns a flat dict `{"field": [...], "table": [...]}`. The plan requires:
- Wrap in `{"by_type": {...}, "action_summary": {...}}`
- Each type becomes `{"count": N, "items": [...]}`
- Entity keys change: `entity_source_id` → `source_id`, `entity_name` → `name`, `action` → `action_taken`

**Breaking change:** The existing test `test_unmapped_id_collector_to_report_dict` (line 171) asserts the old flat structure. It will break when you change `to_report_dict()`. You must update that test to match the new structure. The `_save_report()` in `import_service.py` (line 457) also calls `to_report_dict()` — no code change needed there since it just dumps the dict to JSON, but the output format changes.

### 4.2 — Console summary in `lib/services/import_service.py`

Replace the simple warning in `_log_import_summary()` (lines 434-443) with the detailed per-type breakdown from the plan (section 4.2). The new code reads `report_dict["by_type"]` and `report_dict["action_summary"]`.

### 4.3 — Add context methods to `lib/remapping/id_mapper.py`

Add two methods at the end of the class:
- `get_source_field_context(source_db_id, source_field_id)` → iterates `self.manifest.database_metadata.get(source_db_id, {}).get("tables", [])` and their fields
- `get_source_table_context(source_db_id, source_table_id)` → same but for tables

**Note:** The plan references `self._source_tables` but that attribute doesn't exist. The correct attribute path is `self.manifest.database_metadata.get(source_db_id, {}).get("tables", [])`.

### Final verification

```bash
make ci   # lint + type-check + test with coverage ≥ 85%
```

## Key codebase observations

- `lib/models.py` is actually `lib/models/__init__.py` — a re-export shim from `lib/models_core.py`
- IDMapper stores source metadata via `self.manifest.database_metadata` (NOT `_source_tables`)
- The `_log_import_summary()` accesses the collector via `self._get_context().unmapped_id_collector`
- The `_save_report()` already calls `collector.to_report_dict()` and dumps it to JSON
