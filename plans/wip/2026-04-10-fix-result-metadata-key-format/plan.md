# Plan: Fix result_metadata kebab-case key normalization

## Context

Card imports fail with HTTP 400 because Metabase's GET API returns `result_metadata` with
kebab-case non-namespaced keys (`base-type`, `display-name`, etc.), but its POST API requires
snake_case (`base_type`, `display_name`). This is a Metabase API asymmetry — not a version
mismatch. Full findings at `plans/wip/2026-04-10-fix-result-metadata-key-format/findings.md`.

The existing `_remap_result_metadata()` already uses snake_case keys for its lookups (`field_ref`,
`table_id`) but the incoming data has kebab-case, so ID remapping is also silently broken.

## Changes

### 1. Add key normalization helper in `lib/remapping/query_remapper.py`

Add a static method `_normalize_metadata_keys(item: dict) -> dict` that:
- For each key: if it contains `-` **and does NOT contain `/`** → replace `-` with `_`
- Namespaced keys (containing `/`) are preserved as-is
- Called at the top of the per-item loop in `_remap_result_metadata()`, **before** ID remapping

### 2. Apply normalization in `_remap_result_metadata()` (same file, line ~424)

Replace `item_copy = item.copy()` with `item_copy = self._normalize_metadata_keys(item)`
so that all downstream lookups (`field_ref`, `table_id`, `id`) work correctly on the
now-snake_case keys.

### 3. Add tests in `tests/test_query_remapper.py`

Add a new test class `TestResultMetadataKeyNormalization` with tests:
- `test_kebab_keys_converted_to_snake_case` — verifies non-namespaced keys are converted
- `test_namespaced_keys_preserved` — verifies `lib/type`, `lib/source` etc. stay as-is
- `test_normalization_enables_id_remapping` — verifies that field_ref and table_id remapping
  now works on data that originally had kebab-case keys
- `test_mixed_keys_handled` — items with both kebab and snake keys already present

## Files Modified

- `lib/remapping/query_remapper.py` — add `_normalize_metadata_keys()`, call it in `_remap_result_metadata()`
- `tests/test_query_remapper.py` — add `TestResultMetadataKeyNormalization` class

## Verification

```bash
uv run pytest tests/test_query_remapper.py -v -k "metadata"
make lint
make type-check
make test
```