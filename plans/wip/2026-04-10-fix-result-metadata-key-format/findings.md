# Findings: result_metadata kebab-case vs snake_case

## Problem

Card import fails with 400 Bad Request when `result_metadata` items contain non-namespaced
kebab-case keys (e.g. `base-type`, `display-name`). The target Metabase API requires snake_case
for these keys.

## Root Cause

This is **NOT a version mismatch** between source and target (both are v57). It's an internal
Metabase API asymmetry:

- **GET `/api/card/:id`** returns `result_metadata` with Clojure-native **kebab-case** keys
  for non-namespaced fields (`base-type`, `display-name`, `field-ref`, etc.)
- **POST `/api/card`** runs stricter validation that expects **snake_case** for these same keys
  (`base_type`, `display_name`, `field_ref`, etc.)
- **Namespaced keys** (containing `/`) like `lib/type`, `lib/source` are correctly kept in
  kebab-case in both directions.

Metabase is written in Clojure (kebab-case native). Its GET serialization leaks Clojure keywords
directly into JSON, but its POST validation expects JSON convention (snake_case) for non-namespaced
keys. The GET response is therefore not directly round-trippable through POST.

## Error Message (from log)

```
"legacy source query metadata should use snake_case keys (except for namespaced lib keys,
which should use kebab-case), got: #{:database-partitioned :base-type :semantic-type :table-id
:database-type :effective-type :visibility-type :display-name :field-ref}"
```

## Keys Requiring Conversion

| Sent (kebab-case) | Expected (snake_case) |
|---|---|
| `base-type` | `base_type` |
| `semantic-type` | `semantic_type` |
| `effective-type` | `effective_type` |
| `display-name` | `display_name` |
| `field-ref` | `field_ref` |
| `database-type` | `database_type` |
| `table-id` | `table_id` |
| `visibility-type` | `visibility_type` |
| `database-partitioned` | `database_partitioned` |

Keys to **keep in kebab-case** (namespaced, contain `/`):
`lib/type`, `lib/source`, `lib/deduplicated-name`, `lib/original-name`, `lib/breakout?`,
`lib/source-column-alias`, `lib/original-display-name`, `lib/desired-column-alias`,
`metabase.lib.query/transformation-added-base-type`

## Secondary Bug

The existing `_remap_result_metadata()` in `query_remapper.py` already looks up keys using
snake_case (`field_ref`, `table_id`) on lines 427 and 456. But the actual data has kebab-case
(`field-ref`, `table-id`), so these lookups **silently miss** and no ID remapping happens for
`result_metadata` items. The key normalization must happen BEFORE the ID remapping logic.

## Impact

Affects every card whose `result_metadata` contains these kebab-case keys — likely the majority
of the ~6,597 cards being imported.