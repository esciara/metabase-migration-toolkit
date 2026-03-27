# Code References for Export/Import Granularity

This document provides exact file locations and line numbers for all key code related to export/import granularity.

## Configuration (lib/config.py)

### ExportConfig Class Definition
- **File**: `lib/config.py`
- **Lines**: 132-192
- **Key Fields**:
  - `root_collection_ids: list[int] | None = None` (line 147)
  - `include_dashboards: bool = False` (line 144)
  - `include_archived: bool = False` (line 145)
  - `include_permissions: bool = False` (line 146)

### CLI Export Arguments (get_export_args function)
- **File**: `lib/config.py`
- **Function**: `get_export_args()`
- **Lines**: 288-391
- **Key CLI Arguments**:
  - `--root-collections` (lines 333-336)
  - `--include-dashboards` (lines 322-324)
  - `--include-archived` (lines 325-327)
  - `--include-permissions` (lines 328-332)

### ImportConfig Class Definition
- **File**: `lib/config.py`
- **Lines**: 210-286
- **Key Fields**:
  - `conflict_strategy: Literal["skip", "overwrite", "rename"]` (line 223)
  - `include_archived: bool = False` (line 225)
  - `apply_permissions: bool = False` (line 226)
  - **NO `root_collection_ids` field** - import has no scoping parameters

### CLI Import Arguments (get_import_args function)
- **File**: `lib/config.py`
- **Function**: `get_import_args()`
- **Lines**: 394-497
- **Key Absence**: No `--root-collections` or per-item filtering arguments

### SyncConfig Class Definition
- **File**: `lib/config.py`
- **Lines**: 500-665
- **Combines**:
  - Export options: `root_collection_ids` (line 529)
  - Import options: `conflict_strategy` (line 532)

### CLI Sync Arguments (get_sync_args function)
- **File**: `lib/config.py`
- **Function**: `get_sync_args()`
- **Lines**: 668-834
- **Export Group** (lines 740-755): Includes `--root-collections`
- **Import Group** (lines 758-772): Does NOT include collection filtering

---

## Export Service (lib/services/export_service.py)

### Class Definition
- **File**: `lib/services/export_service.py`
- **Class**: `ExportService`
- **Lines**: 31-712

### Main Export Entry Point
- **Method**: `run_export()`
- **Lines**: 82-145
- **Key Logic**:
  - Collection tree fetching (line 94)
  - Root collection filtering (lines 96-103)
  - Collection traversal (line 110)

```python
# FILTERING HAPPENS HERE (lines 96-103)
if self.config.root_collection_ids:
    collection_tree = [
        c for c in collection_tree 
        if c.get("id") in self.config.root_collection_ids
    ]
```

### Collection Traversal
- **Method**: `_traverse_collections()`
- **Lines**: 189-263
- **Key Points**:
  - Recursively processes collections
  - Calls `_process_collection_items()` for each (line 257)
  - No per-card/dashboard filtering here

### Collection Items Processing
- **Method**: `_process_collection_items()`
- **Lines**: 265-300
- **Key Logic**:
  - Fetches ALL items in collection (lines 277-282)
  - Iterates over all items (line 288)
  - Exports all cards (lines 292-298)
  - Exports dashboards if flag set (line 299)
  - **NO PER-ITEM FILTERING**

### Card Dependency Extraction
- **Method**: `_extract_card_dependencies()`
- **Lines**: 339-371
- **Purpose**: Identifies cards this card depends on
- **Returns**: `set[int]` of dependency card IDs

### Card Export with Dependencies
- **Method**: `_export_card_with_dependencies()`
- **Lines**: 407-496
- **Key Points**:
  - Recursively exports dependencies (line 482)
  - Handles circular dependencies (lines 431-434)
  - Places outside-scope dependencies in "dependencies" folder (lines 466-469)

### Single Card Export
- **Method**: `_export_card()`
- **Lines**: 498-572
- **Purpose**: Exports a single card (internal method)
- **Called by**: `_export_card_with_dependencies()` and `_process_collection_items()`

### Dashboard Export
- **Method**: `_export_dashboard()`
- **Lines**: 574-671
- **Key Points**:
  - Exports dashboards
  - Extracts and exports card dependencies (lines 605-622)
  - Handles outside-scope dependencies (lines 636-642)

### Archived Cards Handling
- **Method**: `_export_archived_cards()`
- **Lines**: 305-337
- **Key Logic**:
  - Only called if `include_archived=True` (line 115)
  - Fetches all archived cards (line 314)
  - Filters by processed collections (line 325)

---

## Import Service (lib/services/import_service.py)

### Class Definition
- **File**: `lib/services/import_service.py`
- **Class**: `ImportService`
- **Lines**: 36-438

### Main Import Entry Point
- **Method**: `run_import()`
- **Lines**: 87-108
- **Key Points**:
  - Loads export package (line 93)
  - Calls `_perform_import()` (line 98)
  - **NO SCOPING AT THIS LEVEL**

### Import Execution
- **Method**: `_perform_import()`
- **Lines**: 304-361
- **Key Logic**:
  - Imports ALL collections (line 340)
  - Imports ALL cards (line 347)
  - Imports ALL dashboards if present (lines 348-349)
  - Imports ALL permissions if requested (lines 350-351)

### Collection Import
- **Method**: `_import_collections()`
- **Lines**: 363-368
- **Key**: Imports ALL collections in manifest

### Card Import
- **Method**: `_import_cards()`
- **Lines**: 370-375
- **Key**: Imports ALL cards in manifest

### Dashboard Import
- **Method**: `_import_dashboards()`
- **Lines**: 377-382
- **Key**: Imports ALL dashboards in manifest

### Permissions Import
- **Method**: `_import_permissions()`
- **Lines**: 384-389
- **Key**: Imports ALL permissions in manifest

---

## Models (lib/models_core.py)

### Card Model
- **File**: `lib/models_core.py`
- **Class**: `Card`
- **Lines**: 27-39
- **Fields**:
  - `id: int`
  - `name: str`
  - `collection_id: int | None`
  - `archived: bool`
  - `dataset: bool` (True if model)

### Collection Model
- **File**: `lib/models_core.py`
- **Class**: `Collection`
- **Lines**: 14-24
- **Fields**:
  - `id: int`
  - `name: str`
  - `parent_id: int | None`

### Dashboard Model
- **File**: `lib/models_core.py`
- **Class**: `Dashboard`
- **Lines**: 42-52
- **Fields**:
  - `id: int`
  - `name: str`
  - `collection_id: int | None`
  - `ordered_cards: list[int]`

### Manifest Model
- **File**: `lib/models_core.py`
- **Class**: `Manifest`
- **Lines**: 78-91
- **Key Collections**:
  - `collections: list[Collection]`
  - `cards: list[Card]`
  - `dashboards: list[Dashboard]`
- **Note**: All collections, cards, and dashboards in the export

---

## Sync Orchestration (sync_metabase.py)

### Main Sync Function
- **File**: `sync_metabase.py`
- **Function**: `main()`
- **Lines**: 21-84
- **Flow**:
  - Phase 1: Export (lines 35-50)
    - Converts config to ExportConfig
    - Calls `ExportService.run_export()`
  - Phase 2: Import (lines 52-74)
    - Converts config to ImportConfig
    - Calls `ImportService.run_import()`
    - Imports everything from resulting manifest

---

## Client API Calls (lib/client.py)

### Collection Tree Fetching
- **File**: `lib/client.py`
- **Method**: `get_collections_tree()`
- **Line**: 209
- **Purpose**: Fetches the entire collection hierarchy
- **Used in**: `ExportService.run_export()` (line 94 of export_service.py)

### Collection Items Fetching
- **File**: `lib/client.py`
- **Method**: `get_collection_items()`
- **Lines**: 217-220
- **Purpose**: Fetches cards/dashboards/models in a collection
- **Used in**: `ExportService._process_collection_items()` (line 282 of export_service.py)

### Individual Card Fetching
- **File**: `lib/client.py`
- **Method**: `get_card()`
- **Lines**: 223-231
- **Purpose**: Fetches a single card by ID
- **Used in**: Dependency analysis and export

### Individual Dashboard Fetching
- **File**: `lib/client.py`
- **Method**: `get_dashboard()`
- **Lines**: 234-240
- **Purpose**: Fetches a single dashboard by ID
- **Used in**: Dashboard export

---

## Test Files (for reference)

### Export Tests
- **File**: `tests/test_export.py`
- **Key Test**: Tests for export configuration and service

### Import Tests
- **File**: `tests/test_import.py`
- **Key Test**: Tests for import service

### Card Handler Tests
- **File**: `tests/test_card_handler.py`
- **Methods Tested**:
  - `_import_single_card()` (internal method)
  - `_extract_single_card_dependency()` (internal method)
  - Note: "single" refers to internal processing, not user-facing feature

### Dashboard Handler Tests
- **File**: `tests/test_dashboard_handler.py`
- **Methods Tested**:
  - `_prepare_single_dashcard()` (internal method)
  - Note: "single" refers to internal processing, not user-facing feature

---

## Key Search Patterns

### To Find Scope Filtering:
Search for: `root_collection_ids` in:
- `lib/config.py` - Configuration definition
- `lib/services/export_service.py` - Usage in export

### To Find Item-Level Filtering:
Search for: `card_ids`, `dashboard_ids`, `--card`, `--dashboard` in:
- Result: NOT FOUND - no per-item filtering exists

### To Find TODOs About Granularity:
Search for: `TODO.*export`, `FIXME.*card`, `single.*card`, `granular` in:
- Result: No feature requests for per-item export found

### To Find Import Scoping:
Search for: `root_collection_ids` in `lib/config.py` ImportConfig:
- Result: NOT DEFINED - import has no scoping

---

## Architecture Summary

```
CLI Entry Points:
  ├─ export_metabase.py → get_export_args() → ExportConfig
  ├─ import_metabase.py → get_import_args() → ImportConfig  
  └─ sync_metabase.py → get_sync_args() → SyncConfig

ExportConfig → ExportService
  └─ root_collection_ids parameter
      └─ Filters collections in run_export() line 96-103
          └─ Affects ALL cards/dashboards in filtered collections
              └─ (No per-item filtering within collections)

ImportConfig → ImportService
  └─ NO scoping parameters
      └─ Imports everything in manifest.json
          └─ From _perform_import() line 304-361
              ├─ _import_collections()
              ├─ _import_cards()
              ├─ _import_dashboards()
              └─ _import_permissions()

Manifest Object
  └─ Contains:
      ├─ collections: List of ALL exported collections
      ├─ cards: List of ALL exported cards
      └─ dashboards: List of ALL exported dashboards
```

