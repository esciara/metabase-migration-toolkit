# Implementation Result: Expand IMMUTABLE_FIELDS

**Date:** 2026-04-09
**Status:** Complete — all CI checks pass (837 passed, 81 skipped, 88.01% coverage)

---

## Problem

Exported card JSON files contain the full Metabase `GET /api/card/{id}` response (~50 fields). Only 9 read-only fields were stripped before `POST /api/card`, letting ~25 server-computed fields leak into the payload.

The immediate symptom: 4 cards failed import with HTTP 400:

```
Incompatibilité détectée entre `collection_id` (null) et `collection_id` (730) du tableau de bord
```

Root cause: `dashboard_id: 45` in the payload references a dashboard in a different collection than the card's remapped `collection_id: 730`. Metabase v57 validates this consistency.

**Distinction from `fea3ce13`:** That commit fixed cards with *unmapped* collection IDs (source collection has no target mapping → `collection_id` sent as `null`). This bug is different — `collection_id` is correctly remapped, but the stale `dashboard_id` metadata clashes with it.

---

## Changes Made

### 1. `lib/constants.py` — IMMUTABLE_FIELDS expanded (9 → 33 fields)

Added 24 fields organized by category:

| Category | Fields added |
|---|---|
| Dashboard references (bug trigger) | `dashboard_id`, `dashboard`, `dashboard_count` |
| Server-computed stats | `average_query_time`, `cache_invalidated_at`, `last_query_start`, `last_used_at`, `last-edit-info`, `view_count` |
| Permission flags | `can_delete`, `can_manage_db`, `can_restore`, `can_run_adhoc_query` |
| Server-internal metadata | `archived_directly`, `card_schema`, `collection`, `dependency_analysis_version`, `document_id`, `entity_id`, `initially_published_at`, `is_remote_synced`, `legacy_query`, `metabase_version`, `parameter_usage_count`, `query_type` |

**Deliberately NOT stripped:**
- `result_metadata` — actively remapped by `QueryRemapper._remap_result_metadata()`
- `source_card_id` — null-set instead of stripped (see below)
- All writable fields (name, description, collection_id, dataset_query, display, etc.)

### 2. `lib/utils/payload.py` — `source_card_id` → None

Added parallel to existing `table_id → None` handling. The top-level `source_card_id` on a card references an instance-specific card ID that isn't remapped by `QueryRemapper` (which handles references *inside* queries).

### 3. `lib/version.py` — Deduplicated

Replaced inline `frozenset({...})` default in `VersionConfig.immutable_fields` with `default_factory=lambda: IMMUTABLE_FIELDS` imported from `lib.constants`. Single source of truth.

### 4. `lib/handlers/dashboard.py` — Replaced inline list

Replaced hardcoded 9-field list in `_remap_embedded_card()` with `IMMUTABLE_FIELDS`, excluding `id` and `database_id` which are actively remapped by the handler.

### 5. Tests

**`tests/test_utils.py`** — 8 new tests:
- `TestCleanForCreateSourceCardId` (3 tests): null-setting, absent field, already-null
- `TestCleanForCreateDashboardFields` (3 tests): dashboard_id, dashboard object, dashboard_count
- `TestCleanForCreateServerComputedFields` (2 tests): permission flags + stats, server-internal metadata + realistic full-payload integration test

**`tests/test_version.py`** — Updated:
- `test_immutable_fields`: added assertions for `dashboard_id`, `dashboard`, `dashboard_count`, `entity_id`, `legacy_query`
- `TestV58Adapter.test_transform_card_for_create`: updated `entity_id` assertion (now stripped rather than null-set, since this code path is unused by handlers)

---

## Gotcha During Implementation

The initial approach of simply iterating `IMMUTABLE_FIELDS` in `_remap_embedded_card()` broke 5 tests because `IMMUTABLE_FIELDS` contains `"id"`, but embedded cards need `id` preserved (it's the card reference ID, actively remapped by the handler). Fixed by excluding `{"id", "database_id"}` from the stripping loop.

---

## CI Results

```
837 passed, 81 skipped (integration/Docker), 88.01% coverage (threshold: 85%)
Lint: passed (ruff + black)
Type-check: passed (mypy strict)
```
