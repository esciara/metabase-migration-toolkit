# Plan: Expand IMMUTABLE_FIELDS to strip read-only fields from card payloads

**Date:** 2026-04-09
**Status:** Implemented

## Context

When importing cards via `POST /api/card`, the payload contains **read-only/server-computed fields** from the export (which saves the full `GET /api/card/{id}` response). The `clean_for_create()` function only strips 9 fields listed in `IMMUTABLE_FIELDS`, letting ~25 read-only fields leak through.

This causes HTTP 400 errors on Metabase v57 — specifically, `dashboard_id` in the payload triggers a collection_id consistency check: *"Incompatibilité détectée entre `collection_id` (null) et `collection_id` (730) du tableau de bord"*. 4 cards currently fail with this error.

**Note:** This is distinct from commit `fea3ce13` which fixed cards with *unmapped* collection IDs being sent as `null`. Here, the card's `collection_id` is correctly remapped (730), but the stale `dashboard_id: 45` reference clashes with it.

## Approach: Expanded blocklist

Add all read-only fields to `IMMUTABLE_FIELDS`. Also deduplicate the two copies of this list found elsewhere in the codebase.

## Changes

### 1. `lib/constants.py` — Expand `IMMUTABLE_FIELDS` (9 → ~33 fields)

Add these fields organized by category:

**Dashboard references (the bug trigger):**
- `dashboard_id`, `dashboard`, `dashboard_count`

**Server-computed stats:**
- `average_query_time`, `cache_invalidated_at`, `last_query_start`, `last_used_at`, `last-edit-info`, `view_count`

**Permission/capability flags:**
- `can_delete`, `can_manage_db`, `can_restore`, `can_run_adhoc_query`

**Server-internal metadata:**
- `archived_directly`, `card_schema`, `collection` (nested object, redundant with `collection_id`), `dependency_analysis_version`, `entity_id`, `initially_published_at`, `is_remote_synced`, `legacy_query`, `metabase_version`, `parameter_usage_count`, `query_type`, `document_id`

**Deliberately NOT stripped:**
- `result_metadata` — actively remapped by `QueryRemapper._remap_result_metadata()` (line 136 in `query_remapper.py`)
- `source_card_id` — needs null-setting, not stripping (see step 2)
- All writable fields: `name`, `description`, `collection_id`, `archived`, `dataset_query`, `display`, `visualization_settings`, `parameters`, `parameter_mappings`, `cache_ttl`, `enable_embedding`, `embedding_params`, `collection_position`, `collection_preview`, `type`, `database_id`

### 2. `lib/utils/payload.py` — Set `source_card_id` to None

Add logic parallel to the existing `table_id` → `None` handling (line 36-37). The top-level `source_card_id` on a card object is instance-specific (references a card ID on the source). It's not remapped by `QueryRemapper` (which only handles `source_card_id` references *inside* queries/template tags). Setting to `None` lets Metabase auto-populate it.

### 3. `lib/version.py` — Eliminate duplicate list (line 163-177)

Replace the inline `frozenset({...})` default in `VersionConfig.immutable_fields` with `default_factory=lambda: IMMUTABLE_FIELDS` imported from `lib.constants`. This eliminates the duplicate while preserving the ability for version-specific overrides.

### 4. `lib/handlers/dashboard.py` — Replace inline list (line 522-535)

Replace the hardcoded 9-field list in `_remap_embedded_card()` with `IMMUTABLE_FIELDS` from constants. Keep `id` and `database_id` which are actively remapped by the handler.

### 5. `tests/test_utils.py` — Add tests

Add to the existing `TestCleanForCreate` class:
- Test that dashboard reference fields (`dashboard_id`, `dashboard`, `dashboard_count`) are stripped
- Test that server-computed fields are stripped (a few representative ones)
- Test that permission flags are stripped
- Test that `source_card_id` is set to None (similar to existing `table_id` tests)
- Realistic integration test with a full exported card payload showing all read-only fields are removed and writable fields preserved

### 6. Update existing test assertions

Check `tests/test_version.py` for `immutable_fields` tests — update to assert the new fields are present.

## Verification

```bash
# Run all tests with coverage
make test

# Run specific test file for payload cleaning
uv run pytest tests/test_utils.py -v -k "clean_for_create"

# Full CI (lint + type-check + test)
make ci
```

Then re-run the import command to confirm the 4 previously-failing cards import successfully:
```bash
uv run import_metabase.py --metabase-version v57 --export-dir exports-prod \
  --db-map export-one-card-prod/db-map-prod-to-stg.json --conflict overwrite
```
