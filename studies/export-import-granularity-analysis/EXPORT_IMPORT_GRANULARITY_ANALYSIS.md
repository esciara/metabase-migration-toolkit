# Export/Import/Sync Feature Granularity Analysis

## Executive Summary

**Current Granularity Level: COLLECTION-LEVEL MINIMUM**

The export/import/sync feature operates at the **collection level** as the minimum scope. You **cannot export a single card or dashboard independently** — the feature is designed to export collections and their contents. However, there are mechanisms to scope exports to specific collections via the `root_collection_ids` parameter.

---

## 1. Export Granularity

### Minimum Exportable Scope: Collections (Not Individual Cards/Dashboards)

**Evidence from `ExportConfig`** (lib/config.py, lines 132-192):
```python
class ExportConfig(BaseModel):
    source_url: str
    export_dir: str
    include_dashboards: bool = False      # Toggle to include/exclude ALL dashboards
    include_archived: bool = False         # Toggle to include/exclude ALL archived items
    include_permissions: bool = False      # Toggle to include/exclude ALL permissions
    root_collection_ids: list[int] | None = None  # ONLY way to limit scope
```

**Key Finding**: The only scope-limiting parameter is `root_collection_ids`, which restricts export to specified collections.

### CLI Arguments for Export Scoping

From `lib/config.py` lines 288-386 (`get_export_args()` function):

```python
parser.add_argument(
    "--root-collections",
    help="Comma-separated list of root collection IDs to export (empty=all)",
)
```

**Limitation Analysis**:
- Takes: comma-separated collection IDs (e.g., `--root-collections 1,2,5`)
- Operates at: **Collection level only**
- No mechanism for: Card ID, Dashboard ID, or tag-based filtering
- Behavior: If specified, ONLY those collections are exported. If not specified (None), ALL collections are exported.

### Export Service Scoping Logic

**From `ExportService.run_export()` (lines 82-145)**:

```python
def run_export(self) -> None:
    # ... code ...
    
    logger.info("Fetching collection tree...")
    collection_tree = self.client.get_collections_tree()
    
    # FILTERING HAPPENS HERE - COLLECTION LEVEL ONLY
    if self.config.root_collection_ids:
        collection_tree = [
            c for c in collection_tree 
            if c.get("id") in self.config.root_collection_ids
        ]
        logger.info(
            f"Export restricted to root collections: {self.config.root_collection_ids}"
        )
    
    if not collection_tree:
        logger.warning("No collections found to export.")
        return
    
    # Process collections recursively
    self._traverse_collections(collection_tree)
```

**Key Points**:
- Filtering happens **before** traversal
- Filters entire collections in/out (no sub-item filtering)
- No mechanism to filter cards by ID, name, or properties
- No mechanism to filter dashboards except via `include_dashboards` toggle

### Collection Traversal Strategy

**From `ExportService._traverse_collections()` (lines 189-263)**:

The service recursively walks the entire collection tree:
1. Gets the root collections (filtered by `root_collection_ids` if provided)
2. For each collection, calls `_process_collection_items(collection_id, base_path)`
3. Recursively processes child collections
4. **All items in each collection are exported** — no card-level filtering

**From `ExportService._process_collection_items()` (lines 265-300)**:

```python
def _process_collection_items(self, collection_id: Any, base_path: str) -> None:
    # Fetches all items in the collection
    params = {
        "models": ["card", "dashboard", "dataset", "metric"],  # ALL types
        "archived": "false",
        "pinned_state": "all",  # Both pinned and non-pinned
    }
    items_response = self.client.get_collection_items(collection_id, params)
    items = items_response.get("data", [])
    
    for item in items:  # ITERATES OVER ALL ITEMS
        model = item.get("model")
        if model in ("card", "dataset", "metric"):
            self._export_card_with_dependencies(item["id"], base_path, ...)
        elif model == "dashboard" and self.config.include_dashboards:
            self._export_dashboard(item["id"], base_path)
```

**Key Points**:
- **All cards** in each collection are exported (no per-card filtering)
- **All dashboards** exported if `include_dashboards=True` (no per-dashboard filtering)
- No mechanism to skip specific cards or dashboards
- Dependency handling exports transitive dependencies even if outside the export scope

### Archived Items Handling

**From `ExportService._export_archived_cards()` (lines 305-337)**:

```python
if self.config.include_archived:
    self._export_archived_cards()
```

- `include_archived` is a **boolean toggle** (all-or-nothing)
- No per-item archival filtering

### Summary: Export Granularity Limitations

| Scope Level | Supported | Mechanism | Limitation |
|------------|-----------|-----------|-----------|
| **Collection** | ✅ Yes | `--root-collections` | Must specify collection IDs, affects entire collections |
| **Card** | ❌ No | None | No card ID filtering parameter |
| **Dashboard** | ❌ No (toggle only) | `--include-dashboards` | All-or-nothing; no per-dashboard selection |
| **Tag** | ❌ No | None | No tag-based filtering |
| **Archived Items** | ❌ (toggle only) | `--include-archived` | All-or-nothing; no per-item filtering |
| **Permissions** | ❌ (toggle only) | `--include-permissions` | All-or-nothing for entire workspace |

---

## 2. Import Granularity

### Import Process: Full Manifest Processing

The import service reads the manifest and imports **everything in it** — there is no per-item filtering during import.

**From `ImportService.run_import()` (lines 87-361)**:

```python
def run_import(self) -> None:
    self._load_export_package()  # Loads manifest.json
    
    if self.config.dry_run:
        self._perform_dry_run()
    else:
        self._perform_import()

def _perform_import(self) -> None:
    # ... validation ...
    
    self._import_collections()    # Imports all collections in manifest
    context.prefetch_collection_items()
    self._import_cards()          # Imports all cards in manifest
    if manifest.dashboards:
        self._import_dashboards()  # Imports all dashboards in manifest
    if self.config.apply_permissions and manifest.permission_groups:
        self._import_permissions()  # Imports all permissions in manifest
```

### ImportConfig Parameters

**From `lib/config.py` lines 210-286**:

```python
class ImportConfig(BaseModel):
    conflict_strategy: Literal["skip", "overwrite", "rename"] = "skip"
    dry_run: bool = False
    include_archived: bool = False
    apply_permissions: bool = False
```

**Key Finding**: Import has **NO scoping parameters** — it only has:
- Conflict resolution strategy (how to handle duplicates)
- Dry-run mode (simulation)
- Global toggles: `include_archived`, `apply_permissions`

**No mechanisms for**:
- Filtering which collections to import
- Filtering which cards to import
- Filtering which dashboards to import
- Per-item selection

### Import Behavior: All-or-Nothing per Manifest

The import process:
1. Loads the manifest
2. Imports **everything** in that manifest
3. Uses conflict strategy if items already exist in target
4. Cannot selectively import subsets

---

## 3. Sync Feature Granularity

### SyncConfig Parameters

**From `lib/config.py` lines 500-630**:

The `SyncConfig` combines both export and import:
```python
# Combines these:
root_collection_ids: list[int] | None = None   # FROM EXPORT
conflict_strategy: Literal["skip", "overwrite", "rename"] = "skip"  # FOR IMPORT
```

### Sync Flow

**From `sync_metabase.py` lines 21-84**:

```python
# Phase 1: Export with root_collection_ids restriction
export_config = config.to_export_config()
exporter = ExportService(export_config)
exporter.run_export()

# Phase 2: Import everything from the resulting manifest
import_config = config.to_import_config()
importer = ImportService(import_config)
importer.run_import()
```

**Key Finding**: Sync combines:
- Export with optional `--root-collections` filtering
- Import of everything in the resulting manifest (no selective import)

---

## 4. root_collection Parameter Analysis

### What `root_collection_ids` Actually Does

**Definition** (lib/config.py, lines 147, 174-191):

```python
root_collection_ids: list[int] | None = None

@field_validator("root_collection_ids")
@classmethod
def validate_collection_ids(cls, v: list[int] | None) -> list[int] | None:
    if v is None:
        return v
    if not v:
        return None  # Empty list treated as None (export all)
    for i, collection_id in enumerate(v):
        if collection_id <= 0:
            raise ConfigValidationError(...)
    return v
```

### Usage Pattern

**From CLI argument (lib/config.py, lines 333-336)**:

```python
parser.add_argument(
    "--root-collections",
    help="Comma-separated list of root collection IDs to export (empty=all)",
)
```

### Effect on Export

**From ExportService.run_export() (lines 96-103)**:

```python
if self.config.root_collection_ids:
    collection_tree = [
        c for c in collection_tree 
        if c.get("id") in self.config.root_collection_ids
    ]
    logger.info(
        f"Export restricted to root collections: {self.config.root_collection_ids}"
    )
```

### Summary: root_collection_ids

| Property | Value |
|----------|-------|
| **Type** | `list[int] \| None` |
| **Minimum Scope** | Collection (not card or dashboard) |
| **Default** | `None` (exports all collections) |
| **Mechanism** | Filters collection tree before recursion |
| **Includes Children** | ✅ Yes (child collections are included) |
| **Sub-Item Filtering** | ❌ No (all cards/dashboards in scope are included) |
| **Dependency Handling** | ⚠️ Dependencies from outside scope go to "dependencies" folder |

---

## 5. Dependency Resolution and Scope

### Card Dependencies

**From `ExportService._export_card_with_dependencies()` (lines 407-496)**:

When a card has dependencies, they are **automatically exported**:

```python
# Extract dependencies
dependencies = self._extract_card_dependencies(card_data)

if dependencies:
    # Recursively export dependencies FIRST
    for dep_id in sorted(dependencies):
        if dep_id not in self._exported_cards:
            try:
                dep_card_data = self.client.get_card(dep_id)
                dep_collection_id = dep_card_data.get("collection_id")
                
                if dep_collection_id and dep_collection_id in self._collection_path_map:
                    dep_base_path = self._collection_path_map[dep_collection_id]
                else:
                    # OUTSIDE SCOPE: Place in dependencies folder
                    dep_base_path = "dependencies"
```

**Key Finding**: 
- **Dependencies are transitively exported**, even if outside `root_collection_ids`
- Outside-scope dependencies go to `dependencies/` folder
- This can expand the export beyond the specified `root_collection_ids`

### Dashboard Card Dependencies

**From `ExportService._export_dashboard()` (lines 574-671)**:

```python
for card_id in card_ids:
    if card_id not in self._exported_cards:
        try:
            card_data = self.client.get_card(card_id)
            card_collection_id = card_data.get("collection_id")
            
            if card_collection_id and card_collection_id in self._collection_path_map:
                card_base_path = self._collection_path_map[card_collection_id]
            else:
                card_base_path = "dependencies"
            
            self._export_card_with_dependencies(card_id, card_base_path)
```

**Key Finding**: Dashboards' referenced cards are exported even if outside scope

---

## 6. No TODO/Feature Requests for Single-Item Export

### Search Results

Grep search for TODOs related to single-item export yields:
- No feature requests for per-card export
- No TODOs about granular filtering
- Mentions of "single card" and "single dashboard" refer to **internal methods** for processing, not export options

Example from test files:
```python
# test_card_handler.py
def test_extract_single_card_dependency(self):
    """Test extraction with single card__X dependency."""
    
def test_import_single_card(self):  # Internal test method
    handler._import_single_card(card)  # Internal implementation detail
```

**Conclusion**: Single-item export is not a planned feature.

---

## 7. Actual Export Flow Visualization

```
CLI: export_metabase.py --root-collections 1,2
         ↓
get_export_args() → ExportConfig(root_collection_ids=[1, 2])
         ↓
ExportService(config).run_export()
         ↓
client.get_collections_tree()
         ↓
Filter: only collections with id in [1, 2]
         ↓
_traverse_collections(filtered_tree)
         ├─→ Collection 1
         │   └─→ _process_collection_items(1)
         │       └─→ Exports ALL cards in Collection 1
         │       └─→ Exports ALL dashboards in Collection 1 (if --include-dashboards)
         │       └─→ Recursively exports child collections
         │
         └─→ Collection 2
             └─→ Similar process
         ↓
RESULT: Export contains:
  - Collections 1, 2 and all descendants
  - ALL cards/dashboards in those collections
  - Dependencies (may include items outside [1,2])
```

---

## 8. Import Flow Visualization

```
CLI: import_metabase.py --export-dir ./export
         ↓
get_import_args() → ImportConfig(no scope parameters)
         ↓
ImportService(config).run_import()
         ↓
_load_export_package()
  └─→ Read manifest.json
         ↓
_perform_import()
  ├─→ _import_collections() 
  │   └─→ Imports ALL collections in manifest
  │
  ├─→ _import_cards()
  │   └─→ Imports ALL cards in manifest
  │
  ├─→ _import_dashboards()
  │   └─→ Imports ALL dashboards in manifest (if any)
  │
  └─→ _import_permissions() (if --apply-permissions)
      └─→ Imports ALL permissions in manifest
         ↓
RESULT: Target instance has:
  - All collections from manifest
  - All cards from manifest
  - All dashboards from manifest
  - (Can't be selective - all-or-nothing)
```

---

## 9. Comparison Matrix: Export vs Import vs Sync

| Feature | Export | Import | Sync |
|---------|--------|--------|------|
| **Collection Filtering** | ✅ `--root-collections` | ❌ No | ✅ `--root-collections` |
| **Card Filtering** | ❌ No | ❌ No | ❌ No |
| **Dashboard Filtering** | 🔄 Toggle only | ❌ No | 🔄 Toggle only |
| **Archived Filtering** | 🔄 Toggle only | 🔄 Toggle only | 🔄 Toggle only |
| **Permissions Filtering** | 🔄 Toggle only | 🔄 Toggle only | 🔄 Toggle only |
| **Dependency Auto-Export** | ✅ Yes | N/A | ✅ Yes (via export) |
| **Conflict Resolution** | N/A | ✅ (skip/overwrite/rename) | ✅ (skip/overwrite/rename) |
| **Dry-Run Mode** | ❌ No | ✅ Yes | ❌ No (only import phase has dry-run) |

---

## 10. Key Limitations and Design Decisions

### Why Single-Card Export Isn't Implemented

1. **Dependency Complexity**: Cards can depend on other cards. Exporting one card requires exporting dependencies, which can cascade.

2. **Collection-Based Organization**: Metabase organizes content by collections. The export mirrors this structure.

3. **Manifest-Driven Approach**: The entire export produces a manifest that describes all exported items. Selective import would require:
   - Per-item selection logic in CLI
   - Manifest subsetting
   - Additional conflict resolution complexity

4. **Current Scope Mechanism**: `root_collection_ids` provides collection-level scoping, which is sufficient for most use cases:
   - Export only specific departments/teams (separate collections)
   - Exclude personal collections
   - Scope to a project collection

### Workaround for Limiting Export Scope

To export a subset of cards/dashboards:
1. **Move items to a dedicated collection** in the source
2. **Export that collection** with `--root-collections <id>`
3. **Import to target**

Or:
1. **Export all** (no `--root-collections`)
2. **Manually edit manifest.json** to remove unwanted items (advanced users only)
3. **Import the modified manifest**

---

## 11. Configuration Examples

### Example 1: Export Single Collection
```bash
python export_metabase.py \
  --source-url https://source.metabase.com \
  --source-username admin \
  --source-password password \
  --export-dir ./export \
  --root-collections 42
```
**Result**: Only collection 42 and its children are exported

### Example 2: Export Multiple Collections
```bash
python export_metabase.py \
  --source-url https://source.metabase.com \
  --source-username admin \
  --source-password password \
  --export-dir ./export \
  --root-collections 1,2,5,10
```
**Result**: Collections 1, 2, 5, 10 and their descendants are exported

### Example 3: Export Everything
```bash
python export_metabase.py \
  --source-url https://source.metabase.com \
  --source-username admin \
  --source-password password \
  --export-dir ./export
```
**Result**: All collections (except personal unless in root-collections) and their cards are exported

### Example 4: Export with Dashboards
```bash
python export_metabase.py \
  --source-url https://source.metabase.com \
  --source-username admin \
  --source-password password \
  --export-dir ./export \
  --include-dashboards
```
**Result**: All collections and ALL dashboards are exported

### Example 5: Import (No Scoping)
```bash
python import_metabase.py \
  --target-url https://target.metabase.com \
  --target-username admin \
  --target-password password \
  --export-dir ./export \
  --db-map ./db_map.json
```
**Result**: Everything from the export manifest is imported to target

---

## Summary of Findings

### Question 1: Can you export/import a single card or dashboard?
**Answer: NO.** The minimum scope is a collection. You cannot export just one card or dashboard independently.

### Question 2: How is the scope of export determined?
**Answer**: Via the `--root-collections` CLI argument, which accepts a comma-separated list of collection IDs. Defaults to all collections if not specified.

### Question 3: Is there a `root_collection` parameter?
**Answer: YES**, it's called `root_collection_ids` (plural), defined as:
- **Type**: `list[int] | None`
- **CLI**: `--root-collections <comma-separated IDs>`
- **Effect**: Restricts export to specified collections (and their descendants)
- **Default**: `None` (export all)

### Question 4: What's the minimum scope you can export?
**Answer**: A single **collection** with all its contents. You cannot selectively export cards or dashboards within a collection.

### Question 5: Does the export service iterate over all collections or target individual items?
**Answer**: 
- **Export**: Iterates over all collections (filtered by `root_collection_ids`)
- **Within each collection**: Iterates over ALL cards and dashboards
- **No per-item targeting**

### Question 6: Is there filtering by card ID, dashboard ID, or individual item selection?
**Answer: NO.** The only filtering mechanisms are:
- Collection ID (via `--root-collections`)
- Item type toggles: `--include-dashboards`, `--include-archived`, `--include-permissions`
- All are all-or-nothing toggles, not selective

### Question 7: Are there TODOs or feature requests for single-item export?
**Answer: NO.** No planned feature for per-card or per-dashboard export in the codebase.

