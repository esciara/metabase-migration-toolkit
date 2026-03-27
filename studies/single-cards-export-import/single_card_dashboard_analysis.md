# Deep Analysis: Single Card and Single Dashboard Export/Import Feature

## Executive Summary

Adding single-card and single-dashboard export/import capabilities to the Metabase migration toolkit is **moderately complex** but **highly feasible**. The current architecture already handles dependency management and collection hierarchies well. The primary challenges are:

1. **Collection path reconstruction** - Cards/dashboards need their parent collections in the target
2. **Dependency graph traversal** - Must recursively export all dependencies
3. **Manifest structure** - Must reflect only the selected item(s) plus their dependencies
4. **Config/CLI changes** - Need new arguments to specify card/dashboard IDs

The complexity is manageable because the core export/import logic doesn't need fundamental changes, only new entry points.

---

## 1. CARD (QUESTION) EXPORT ANALYSIS

### 1.1 Card Data Structure

**Location**: `lib/models_core.py:28-39`

```python
@dataclasses.dataclass
class Card:
    id: int                               # Source card ID
    name: str                             # Card name (exported as filename)
    collection_id: int | None             # Parent collection ID
    database_id: int | None               # Database the card queries
    file_path: str = ""                   # Relative path: "collections/Cards/card_123_name.json"
    checksum: str = ""                    # SHA256 of the JSON file
    archived: bool = False                # Archived status
    dataset_query: dict[str, Any] = None  # Query definition (not populated in manifest)
    dataset: bool = False                 # True if this is a model (dataset)
```

**Actual card JSON file** contains:
- `id`, `name`, `collection_id`, `database_id`
- `dataset_query`: Full query definition with all references
- `type`: "question", "metric", or "model"
- `dataset`: Boolean (true for models)
- `archived`, `description`, `caching_ttl`, etc.
- **Critically**: All query references are embedded in `dataset_query`

### 1.2 Card Dependencies - Full Extraction Logic

**Export Service** (`lib/services/export_service.py:340-406`):

The export service extracts dependencies through:

1. **MBQL v56 format** (source-table: "card__123" string refs):
   ```python
   dataset_query = {
       "database": 1,
       "query": {
           "source-table": "card__53",  # Reference to card ID 53
           "joins": [{"source-table": "card__54"}]  # Join to another card
       }
   }
   ```

2. **MBQL v57 format** (source-card: 123 integer refs):
   ```python
   dataset_query = {
       "database": 1,
       "stages": [
           {
               "source-card": 53,  # Direct integer reference
               "joins": [{"source-card": 54}]
           }
       ]
   }
   ```

3. **Native SQL with model references** ({{#123-model-name}}):
   ```sql
   SELECT * FROM {{#53-source-model}}
   ```

4. **Saved metrics** (v57 MBQL 5 aggregation format):
   ```python
   "aggregation": [["metric", {"lib/uuid": "..."}, 53]]  # Card 53 is a metric
   ```

5. **Template tags** (for parameterized queries):
   ```python
   "template_tags": {
       "category": {"type": "card", "card-id": 53}
   }
   ```

**Key extraction method** (`_extract_card_dependencies` at line 340):
- Recursively scans through stages, joins, aggregations
- Returns a `set[int]` of dependent card IDs
- Handles circular dependencies by tracking a `dependency_chain`

### 1.3 Card Export Flow

**Export Service** (`lib/services/export_service.py:407-493`):

```
_export_card_with_dependencies(card_id, base_path, dependency_chain=[])
    ├─ Check if already exported (skip to avoid duplicates)
    ├─ Check for circular dependencies (break cycle)
    ├─ Fetch card data via API: client.get_card(card_id)
    ├─ Extract dependencies: _extract_card_dependencies(card_data)
    ├─ For each dependency (in sorted order):
    │   ├─ Recursively call _export_card_with_dependencies()
    │   └─ Place in "dependencies" folder if outside export scope
    └─ Export the card itself: _export_card()
```

**Key variables tracked**:
- `self._exported_cards: set[int]` - Prevents re-exporting
- `self._collection_path_map: dict[int, str]` - Maps source collection IDs to filesystem paths
- `self._processed_collections: set[int]` - Tracks which collections were traversed
- `dependency_chain: list[int]` - Used for circular dependency detection

### 1.4 Card File Location

**Export location** (`lib/services/export_service.py:535-537`):
```python
file_path_str = f"{base_path}/cards/card_{card_id}_{card_slug}.json"
# Example: "collections/Sales_Dashboard/cards/card_123_sales_by_region.json"
```

**What gets written**: Full API response from `GET /api/card/{id}` (unmodified)

### 1.5 Card in Manifest

**Manifest entries** (`lib/services/export_service.py:550-560`):
```python
Card(
    id=123,
    name="Sales by Region",
    collection_id=5,
    database_id=2,
    file_path="collections/Sales_Dashboard/cards/card_123_sales_by_region.json",
    checksum="abc123...",  # SHA256 of file
    archived=False,
    dataset=False  # True if it's a model
)
```

---

## 2. DASHBOARD EXPORT ANALYSIS

### 2.1 Dashboard Data Structure

**Location**: `lib/models_core.py:43-52`

```python
@dataclasses.dataclass
class Dashboard:
    id: int                    # Dashboard ID
    name: str                  # Dashboard name
    collection_id: int | None  # Parent collection ID
    ordered_cards: list[int]   # List of card IDs on this dashboard (in order)
    file_path: str = ""        # Relative path: "collections/X/dashboards/dash_123_name.json"
    checksum: str = ""         # SHA256 of file
    archived: bool = False     # Archived status
```

### 2.2 Dashboard Dependencies - DashCard Analysis

**Export Service** (`lib/services/export_service.py:604-622`):

A dashboard contains `dashcards` - these are the **placement and configuration** of cards:

```json
{
    "id": 1,
    "dashboard_id": 123,
    "card_id": 456,           // ← CRITICAL: References the card ID
    "row": 0, "column": 0,
    "size_x": 4, "size_y": 3,
    "visualization_settings": { ... },
    "parameter_mappings": [ ... ],
    "series": [{"id": 789}],  // ← Card IDs for combined series
    "dashboard_tab_id": 1,    // For tabbed dashboards
    "card": { ... }           // Embedded card object (for "Visualize another way")
}
```

**Dashboard parameters (filters)**:
```json
{
    "parameters": [
        {
            "name": "Category",
            "type": "category",
            "values_source_config": {
                "card_id": 789  // ← Parameter values sourced from a card
            }
        }
    ]
}
```

**Extraction logic** (`lib/services/export_service.py:604-622`):
```python
card_ids = []
# From dashcards
for dashcard in dashboard_data.get("dashcards", []):
    if dashcard.get("card_id"):
        card_ids.append(dashcard["card_id"])

# From parameters
for param in dashboard_data.get("parameters", []):
    if "values_source_config" in param:
        source_card_id = param["values_source_config"].get("card_id")
        if source_card_id:
            card_ids.append(source_card_id)

# Export all cards as dependencies
for card_id in card_ids:
    self._export_card_with_dependencies(card_id, card_base_path)
```

### 2.3 Dashboard Dependency Chain

```
Dashboard → DashCards → Card IDs (ordered_cards list)
         → Parameters → Source Card IDs
         
Each referenced Card → Its own dependencies (via dataset_query)
```

**Key insight**: Dashboards themselves don't have `dataset_query`, so they don't have direct dependencies. **All dependencies come through the referenced cards.**

### 2.4 Dashboard File Location & Content

**Export location** (`lib/services/export_service.py:598-599`):
```python
file_path_str = f"{base_path}/dashboards/dash_{dashboard_id}_{dash_slug}.json"
# Example: "collections/Executive/dashboards/dash_123_q3_metrics.json"
```

**What gets written**: Full API response from `GET /api/dashboard/{id}` with all dashcards and parameters

### 2.5 Dashboard in Manifest

```python
Dashboard(
    id=123,
    name="Q3 Metrics",
    collection_id=5,
    ordered_cards=[456, 789, 790],  # Card IDs on dashboard
    file_path="collections/Executive/dashboards/dash_123_q3_metrics.json",
    checksum="def456...",
    archived=False
)
```

---

## 3. COLLECTION HANDLING ANALYSIS

### 3.1 Current Collection Export

**Export Service** (`lib/services/export_service.py:189-263`):

Collection tree traversal happens **top-down**:

```
get_collections_tree()  // Fetches full tree from API
├─ Recursively process each collection
│  ├─ Create Collection object
│  ├─ Write _collection.json metadata file
│  ├─ Call _process_collection_items() to export cards/dashboards
│  └─ Recurse into children
```

**Collection path mapping** (`lib/services/export_service.py:221-223`):
```python
sanitized_name = sanitize_filename(collection_data["name"])
current_path = f"{parent_path}/{sanitized_name}".lstrip("/")
self._collection_path_map[collection_id] = current_path
```

**Example structure exported**:
```
export_dir/
├─ manifest.json
├─ collections/
│  ├─ _collection.json  (root)
│  ├─ Sales/
│  │  ├─ _collection.json
│  │  ├─ cards/
│  │  │  └─ card_123_by_region.json
│  │  └─ dashboards/
│  │     └─ dash_456_summary.json
│  └─ Marketing/
│     ├─ _collection.json
│     └─ cards/
│        └─ card_789_campaigns.json
└─ dependencies/
   └─ cards/
      └─ card_999_shared_model.json  (if referenced but outside export scope)
```

### 3.2 Collection Manifest Structure

**What gets recorded** (`lib/services/export_service.py:239-248`):

```python
Collection(
    id=5,
    name="Sales",
    slug="sales",
    description="...",
    parent_id=None,
    personal_owner_id=None,
    path="collections/Sales"  # ← Filesystem path, used for reconstruction
)
```

The `path` field is **critical** - it stores the relative filesystem path, enabling reconstruction on import.

### 3.3 Collection Import Flow

**Collection Handler** (`lib/handlers/collection.py:24-64`):

```
import_collections(collections: list[Collection])
    ├─ Sort by path (alphabetical, ensures parent before child)
    └─ For each collection:
        ├─ Resolve parent_id (parent must exist first)
        ├─ Check for existing collection on target
        ├─ Apply conflict strategy (skip/overwrite/rename)
        └─ Create or update via API
```

**Collection ID remapping** happens in `IDMapper.set_collection_mapping()`:
```python
self._collection_map[source_id] = target_id
```

---

## 4. IMPORT SIDE - ID REMAPPING ANALYSIS

### 4.1 IDMapper Responsibility

**Location**: `lib/remapping/id_mapper.py`

The IDMapper tracks **5 different mapping types**:

```python
_collection_map: dict[int, int] = {}   # source_collection_id → target_collection_id
_card_map: dict[int, int] = {}         # source_card_id → target_card_id
_dashboard_map: dict[int, int] = {}    # source_dashboard_id → target_dashboard_id
_group_map: dict[int, int] = {}        # source_group_id → target_group_id
_table_map: dict[tuple[int, int], int] = {}  # (source_db_id, source_table_id) → target_table_id
_field_map: dict[tuple[int, int], int] = {}  # (source_db_id, source_field_id) → target_field_id
```

### 4.2 Card Import with ID Remapping

**Card Handler** (`lib/handlers/card.py:39-116`):

```
import_cards(cards: list[Card])
    ├─ Filter archived status
    ├─ Topological sort (dependencies first)
    └─ For each card:
        ├─ Read JSON file
        ├─ Extract card dependencies
        ├─ Check all dependencies are in export
        ├─ Remap database IDs (via QueryRemapper)
        ├─ Remap card references in query (via QueryRemapper)
        ├─ Remap collection_id (via IDMapper)
        ├─ Check for existing card on target
        ├─ Apply conflict strategy
        └─ Create or update via API, then set_card_mapping()
```

**Topological sort** (`lib/handlers/card.py:466-525`):
- Analyzes **all card dependencies** from manifest
- Uses **Kahn's algorithm** to sort cards
- Dependencies imported first, so card references resolve correctly
- Cards with circular dependencies are placed at end (import fails gracefully)

### 4.3 Dashboard Import with ID Remapping

**Dashboard Handler** (`lib/handlers/dashboard.py:29-142`):

```
import_dashboards(dashboards: list[Dashboard])
    └─ For each dashboard:
        ├─ Read JSON file
        ├─ Remap collection_id
        ├─ Remap dashboard parameter card references (via QueryRemapper)
        ├─ Check for existing dashboard
        ├─ Apply conflict strategy
        ├─ Create dashboard (minimal, just name/collection)
        ├─ Prepare tabs (with negative IDs)
        ├─ Prepare dashcards:
        │   ├─ Remap card_id (via IDMapper.resolve_card_id())
        │   ├─ Remap visualization_settings (field/dashboard IDs)
        │   ├─ Remap parameter_mappings
        │   ├─ Remap series card IDs
        │   └─ Remap embedded card object (for "Visualize another way")
        └─ Update dashboard with tabs + dashcards (single PUT request for v57)
```

### 4.4 QueryRemapper Responsibility

**Location**: `lib/remapping/query_remapper.py`

Remaps IDs **within query definitions**:

```python
remap_card_data(card_data)
    # Updates card_data["dataset_query"] in-place
    # - Remaps database IDs
    # - Remaps table IDs (in source-table: "table_123")
    # - Remaps field IDs (in filter/groupby clauses)
    # - Remaps card references (card__123 → card__target_id)

remap_dashboard_parameters(parameters, manifest_cards)
    # Remaps card_id references in parameter.values_source_config

remap_dashcard_visualization_settings(settings, source_db_id)
    # Remaps dashboard/card/field IDs in visualization settings

remap_dashcard_parameter_mappings(mappings, source_db_id)
    # Remaps field IDs in parameter mappings
```

### 4.5 Import Order Requirement

**Critical constraint** from `lib/services/import_service.py:340-351`:

```python
# Collections MUST be imported first
self._import_collections()

# Then pre-fetch collection items for conflict detection
context.prefetch_collection_items()

# Then import cards (which depend on collections)
self._import_cards()

# Then dashboards (which depend on cards)
if manifest.dashboards:
    self._import_dashboards()

# Finally permissions (if requested)
if self.config.apply_permissions:
    self._import_permissions()
```

**Why this order?**
1. Collections must exist first (cards/dashboards reference `collection_id`)
2. Cards must be imported before dashboards (dashboards reference card IDs)
3. Pre-fetching collection items enables O(1) conflict lookup

---

## 5. MANIFEST.JSON STRUCTURE & ROLE

### 5.1 Current Manifest Format

**Location**: `lib/models_core.py:78-91`

```python
@dataclasses.dataclass
class Manifest:
    meta: ManifestMeta  # Export metadata (timestamp, tool version, etc.)
    databases: dict[int, str]  # {source_db_id: "db_name"} - for database mapping
    collections: list[Collection]  # All exported collections
    cards: list[Card]  # All exported cards (references to files)
    dashboards: list[Dashboard]  # All exported dashboards (references to files)
    permission_groups: list[PermissionGroup]  # Permission groups (optional)
    permissions_graph: dict[str, Any]  # Full permissions (optional)
    collection_permissions_graph: dict[str, Any]  # Collection permissions (optional)
    database_metadata: dict[int, dict]  # Table/field metadata (for ID mapping)
```

### 5.2 How Manifest is Used on Import

**Import Service** (`lib/services/import_service.py:110-166`):

1. **Loaded from file**: `manifest.json` is parsed into `Manifest` object
2. **Used by handlers**:
   - Collections from `manifest.collections` → imported via `CollectionHandler`
   - Cards from `manifest.cards` → imported via `CardHandler`
   - Dashboards from `manifest.dashboards` → imported via `DashboardHandler`
3. **Dependency checking**: Card handler checks if dependencies are in `manifest.cards`
4. **Database metadata**: Used for table/field ID mapping via `IDMapper.build_table_and_field_mappings()`

**Key insight**: The manifest is the **source of truth for what to import**. The import service only imports items listed in the manifest.

### 5.3 Database Metadata in Manifest

**What's stored** (`lib/services/export_service.py:171-184`):

```python
simplified_metadata = {
    "tables": [
        {
            "id": 1,
            "name": "users",
            "fields": [
                {"id": 10, "name": "id"},
                {"id": 11, "name": "email"},
                {"id": 12, "name": "created_at"}
            ]
        },
        ...
    ]
}
manifest.database_metadata[db_id] = simplified_metadata
```

**Used during import** (`lib/remapping/id_mapper.py`):
- `build_table_and_field_mappings()` uses this to map source table/field IDs to target

---

## 6. CONFIG/CLI CHANGES REQUIRED

### 6.1 Current Export Config

**Location**: `lib/config.py:132-207`

```python
class ExportConfig(BaseModel):
    source_url: str
    export_dir: str
    metabase_version: MetabaseVersion = DEFAULT_METABASE_VERSION
    source_username: str | None = None
    source_password: str | None = None
    source_session_token: str | None = None
    source_personal_token: str | None = None
    include_dashboards: bool = False
    include_archived: bool = False
    include_permissions: bool = False
    root_collection_ids: list[int] | None = None  # ← Existing filter mechanism
    log_level: str = "INFO"
```

**Current CLI** (`lib/config.py:288-387`):
```
--source-url URL
--export-dir DIR
--source-username USER
--source-password PASS
--source-session TOKEN
--source-token TOKEN
--include-dashboards
--include-archived
--include-permissions
--root-collections ID1,ID2,ID3
--log-level LEVEL
```

### 6.2 Proposed Changes for Single Card/Dashboard

**New CLI arguments needed**:

```bash
# Option A: Mutually exclusive export modes
--export-mode collection|card|dashboard  (default: collection)
--card-id ID                             (with --export-mode card)
--dashboard-id ID                        (with --export-mode dashboard)

# Option B: Accept both, use first provided
--card-ids ID1,ID2,...
--dashboard-ids ID1,ID2,...
--root-collections ID1,ID2,...          (existing)
```

**Recommended approach**: Option B (more flexible, allows combining card + dashboard exports)

### 6.3 Config Validation Changes

**Location to modify**: `lib/config.py:132-207`

```python
class ExportConfig(BaseModel):
    # ... existing fields ...
    card_ids: list[int] | None = None
    dashboard_ids: list[int] | None = None
    
    @field_validator("card_ids", "dashboard_ids")
    @classmethod
    def validate_item_ids(cls, v: list[int] | None) -> list[int] | None:
        if v is None:
            return v
        if not v:
            return None  # Empty list → None (export all)
        for item_id in v:
            if item_id <= 0:
                raise ConfigValidationError(f"Item IDs must be positive")
        return v
    
    @model_validator(mode="after")
    def validate_export_mode(self) -> "ExportConfig":
        # Ensure at least one export target is specified
        has_collections = self.root_collection_ids is None or len(self.root_collection_ids) > 0
        has_cards = self.card_ids is not None and len(self.card_ids) > 0
        has_dashboards = self.dashboard_ids is not None and len(self.dashboard_ids) > 0
        
        if not (has_collections or has_cards or has_dashboards):
            raise ConfigValidationError("Must export at least collections, cards, or dashboards")
        
        return self
```

### 6.4 CLI Argument Parsing Changes

**Location to modify**: `lib/config.py:333-387`

```python
def get_export_args() -> ExportConfig:
    # ... existing code ...
    
    # Add new export mode arguments
    export_group = parser.add_argument_group("Export Mode")
    export_group.add_argument(
        "--card-ids",
        help="Comma-separated list of card IDs to export (empty=all)"
    )
    export_group.add_argument(
        "--dashboard-ids",
        help="Comma-separated list of dashboard IDs to export"
    )
    
    # Parse new arguments
    card_ids: list[int] | None = None
    if args.card_ids:
        try:
            card_ids = [int(c_id.strip()) for c_id in args.card_ids.split(",")]
        except ValueError:
            parser.error(f"--card-ids must be comma-separated integers")
    
    dashboard_ids: list[int] | None = None
    if args.dashboard_ids:
        try:
            dashboard_ids = [int(d_id.strip()) for d_id in args.dashboard_ids.split(",")]
        except ValueError:
            parser.error(f"--dashboard-ids must be comma-separated integers")
    
    # Pass to ExportConfig
    return ExportConfig(
        # ... existing fields ...
        card_ids=card_ids,
        dashboard_ids=dashboard_ids,
    )
```

---

## 7. IMPLEMENTATION STRATEGY

### 7.1 Export Service Changes Required

**New method needed** in `ExportService`:

```python
def run_export_single_card(self, card_id: int) -> None:
    """Export a single card and its dependencies."""
    self.export_dir.mkdir(parents=True, exist_ok=True)
    
    # Fetch the card
    card_data = self.client.get_card(card_id)
    
    # Build collection tree to parent
    collection_id = card_data.get("collection_id")
    self._build_minimal_collection_tree(collection_id)
    
    # Export card with dependencies
    self._export_card_with_dependencies(card_id, base_path="")
    
    # Fetch databases referenced by card and dependencies
    self._fetch_and_store_databases()
    
    # Write manifest
    manifest_path = self.export_dir / "manifest.json"
    write_json_file(self.manifest, manifest_path)
```

**New collection tree building**:

```python
def _build_minimal_collection_tree(self, collection_id: int | None) -> None:
    """Build minimal collection tree from target collection up to root."""
    if collection_id is None:
        return
    
    # Fetch the target collection
    collection_data = self.client.get_collection(collection_id)
    
    # Recursively build parent collections
    parent_id = collection_data.get("parent_id")
    if parent_id:
        self._build_minimal_collection_tree(parent_id)
    
    # Add this collection
    # ... same logic as _traverse_collections
```

**Similar method for dashboard**:

```python
def run_export_single_dashboard(self, dashboard_id: int) -> None:
    """Export a single dashboard and all its card dependencies."""
    self.export_dir.mkdir(parents=True, exist_ok=True)
    
    # Fetch dashboard
    dashboard_data = self.client.get_dashboard(dashboard_id)
    
    # Build collection tree
    collection_id = dashboard_data.get("collection_id")
    self._build_minimal_collection_tree(collection_id)
    
    # Export cards referenced by dashboard
    for dashcard in dashboard_data.get("dashcards", []):
        card_id = dashcard.get("card_id")
        if card_id:
            self._export_card_with_dependencies(card_id, base_path="")
    
    # Export cards from parameters
    for param in dashboard_data.get("parameters", []):
        if "values_source_config" in param:
            card_id = param["values_source_config"].get("card_id")
            if card_id:
                self._export_card_with_dependencies(card_id, base_path="")
    
    # Export the dashboard itself
    self._export_dashboard(dashboard_id, base_path="")
    
    # Fetch databases and write manifest
    self._fetch_and_store_databases()
    # ... write manifest
```

### 7.2 Export Service Main Method Change

```python
def run_export(self) -> None:
    """Main export entry point - delegates to specific method."""
    logger.info(f"Starting Metabase export from {self.config.source_url}")
    
    try:
        # Handle single-card export
        if self.config.card_ids:
            for card_id in self.config.card_ids:
                self.run_export_single_card(card_id)
        
        # Handle single-dashboard export
        elif self.config.dashboard_ids:
            for dashboard_id in self.config.dashboard_ids:
                self.run_export_single_dashboard(dashboard_id)
        
        # Default: export collections
        else:
            self._run_export_collections()
    except MetabaseAPIError as e:
        logger.error(f"A Metabase API error occurred: {e}", exc_info=True)
        raise
```

### 7.3 Import Side - No Changes Needed

**Key insight**: The import service **already handles arbitrary manifests**. It:
1. Loads whatever is in manifest.json
2. Imports collections from `manifest.collections`
3. Imports cards from `manifest.cards`
4. Imports dashboards from `manifest.dashboards`

**No changes required** for importing single cards/dashboards - the existing logic works!

---

## 8. COMPLEXITY ASSESSMENT

### 8.1 Changes by File

| File | Lines Changed | Complexity | Notes |
|------|---------------|-----------|-------|
| `lib/config.py` | ~50 | Low | Add 3 new config fields, validators, CLI args |
| `lib/services/export_service.py` | ~100 | Medium | Add 2 new entry methods, collection tree builder |
| `export_metabase.py` | ~15 | Low | Route to appropriate export method |
| Other files | 0 | None | Import side needs no changes |

**Total new code**: ~165 lines
**Modified code**: ~65 lines
**Backward compatible**: Yes (existing full-export mode unchanged)

### 8.2 Key Implementation Challenges

1. **Collection path reconstruction**
   - **Challenge**: Need to fetch parent collections to build correct path
   - **Solution**: Recursive `_build_minimal_collection_tree()` method
   - **Complexity**: Medium (requires following parent_id chain)

2. **Dependency traversal**
   - **Challenge**: Must recursively export all card dependencies
   - **Solution**: Already implemented in `_export_card_with_dependencies()`
   - **Complexity**: Low (reuse existing logic)

3. **Manifest consistency**
   - **Challenge**: Manifest must only list what was exported
   - **Solution**: Build manifest during export as items are added
   - **Complexity**: Low (current approach already does this)

4. **Database metadata**
   - **Challenge**: Must include DB metadata for all referenced databases
   - **Solution**: Reuse `_fetch_and_store_databases()`
   - **Complexity**: Low (existing method)

---

## 9. DEPENDENCY GRAPH - VISUAL

### Single Card Export
```
Card ID 123
    │
    ├─ Collection 5 (parent)
    │   ├─ Collection 3 (grandparent)
    │   │   └─ Collection 1 (root)
    │   └─ Other siblings (NOT exported)
    │
    ├─ Database 2
    │   └─ Table/Field metadata
    │
    └─ Dependencies (via dataset_query)
        ├─ Card 456 (model source)
        │   ├─ Collection (parent of 456)
        │   ├─ Database
        │   └─ Its own dependencies...
        └─ Card 789 (joined source)
            └─ ...
```

### Single Dashboard Export
```
Dashboard ID 123
    │
    ├─ Collection 5 (parent)
    │   ├─ Collection 3 (grandparent)
    │   │   └─ Collection 1 (root)
    │   └─ Other siblings (NOT exported)
    │
    ├─ Cards (from dashcards)
    │   ├─ Card 456
    │   │   ├─ Collection (parent)
    │   │   ├─ Database
    │   │   └─ Card dependencies
    │   └─ Card 789
    │       └─ ...
    │
    ├─ Cards (from parameters)
    │   └─ Card 999
    │       └─ ...
    │
    └─ Database (aggregate from all cards)
```

---

## 10. FILE LOCATIONS & LINE NUMBERS - COMPLETE REFERENCE

### Export Service
- **Lines 31-145**: `ExportService.__init__()` and main orchestration
- **Lines 147-188**: `_fetch_and_store_databases()` - fetches DB metadata
- **Lines 189-263**: `_traverse_collections()` - recursive collection processing
- **Lines 265-304**: `_process_collection_items()` - export cards/dashboards in collection
- **Lines 305-337**: `_export_archived_cards()` - export archived items
- **Lines 339-406**: `_extract_card_dependencies()` - dependency extraction (CRITICAL)
- **Lines 407-493**: `_export_card_with_dependencies()` - recursive card export with deps
- **Lines 498-572**: `_export_card()` - single card export
- **Lines 574-671**: `_export_dashboard()` - single dashboard export

### Card Handler
- **Lines 39-63**: `import_cards()` - topological sort + import loop
- **Lines 65-115**: `_import_single_card()` - single card import
- **Lines 330-429**: `_extract_card_dependencies()` - dependency extraction on import side
- **Lines 466-525**: `_topological_sort_cards()` - Kahn's algorithm for sorting

### Dashboard Handler
- **Lines 29-142**: `import_dashboards()` - main import loop
- **Lines 259-375**: `_prepare_dashcards()` - ID remapping for dashcards

### Config
- **Lines 132-207**: `ExportConfig` class definition
- **Lines 288-391**: `get_export_args()` - CLI parsing for export
- **Lines 394-497**: `get_import_args()` - CLI parsing for import

### Models
- **Lines 28-39**: `Card` dataclass
- **Lines 43-52**: `Dashboard` dataclass
- **Lines 15-24**: `Collection` dataclass
- **Lines 78-91**: `Manifest` dataclass

### IDMapper
- **Lines 15-47**: `IDMapper` class initialization and properties
- **Lines 82-96**: Mapping setters
- **Lines 100-118**: Database ID resolution
- **Lines 146-159**: Collection ID resolution (for import)

### Collection Handler
- **Lines 24-40**: `import_collections()` - main import
- **Lines 42-78**: `_import_single_collection()` - single collection import

---

## 11. TESTING REQUIREMENTS

### Unit Tests Needed

1. **Single Card Export**
   - Export a simple question (no dependencies)
   - Export a question with card dependencies
   - Export a model (dataset=true)
   - Export with dependencies outside collection scope

2. **Single Dashboard Export**
   - Export with single card
   - Export with multiple cards
   - Export with parameter filters (values_source_config)
   - Export tabbed dashboard

3. **Dependency Handling**
   - Circular dependency detection
   - Nested dependencies (card → card → card)
   - Missing dependency handling

4. **Collection Tree Building**
   - Single level collection
   - Multi-level hierarchy
   - Collections with siblings (shouldn't export)

5. **Import Verification**
   - Card imports with correct collection
   - Dashboard imports with correct card references
   - ID remapping works correctly

---

## 12. ESTIMATION

### Implementation Effort

| Task | Estimate | Notes |
|------|----------|-------|
| Config changes | 1-2 hours | Straightforward, well-established pattern |
| Export service methods | 3-4 hours | Mostly code reuse, collection tree builder is new |
| Export CLI routing | 1 hour | Just add conditional logic |
| Integration testing | 4-6 hours | Multiple scenarios to test |
| **Total** | **9-13 hours** | Medium complexity task |

### Code Review & Risk Assessment

**Low-risk changes**:
- Config additions (isolated, validated)
- Export service delegating to new methods (no impact on existing paths)

**Medium-risk areas**:
- Collection tree building (recursion, could miss edge cases)
- Dependency graph verification (must handle all cases from current system)

**Mitigation**: Leverage existing, well-tested `_export_card_with_dependencies()` method

---

## CONCLUSION

Adding single-card and single-dashboard export/import is **feasible and recommended**. The toolkit already has solid foundations for:
- Dependency extraction
- Collection management
- ID remapping on import
- Manifest-driven imports

The main additions are:
1. New export entry points for single card/dashboard
2. Minimal collection tree reconstruction
3. CLI argument handling
4. Reuse of all existing import logic

**Estimated complexity**: Medium
**Implementation time**: 9-13 hours
**Code changes**: ~230 lines of new/modified code
**Backward compatibility**: Fully maintained
