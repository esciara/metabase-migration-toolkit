# Implementation Roadmap - Single Card & Dashboard Export

## Phase 1: Configuration (1-2 hours)

### Task 1.1: Add Config Fields
**File**: `lib/config.py:132-207`

```python
class ExportConfig(BaseModel):
    # ... existing fields ...
    card_ids: list[int] | None = None
    dashboard_ids: list[int] | None = None
```

**Checklist**:
- [ ] Add `card_ids` field to ExportConfig
- [ ] Add `dashboard_ids` field to ExportConfig
- [ ] Add field_validator for `card_ids` (follow pattern from lines 174-191)
- [ ] Add field_validator for `dashboard_ids`
- [ ] Add model_validator to ensure at least one export target is specified

### Task 1.2: Add CLI Arguments
**File**: `lib/config.py:288-391`

**In `get_export_args()` function**:

```python
# After --root-collections argument
parser.add_argument(
    "--card-ids",
    help="Comma-separated list of card IDs to export (empty=all)"
)
parser.add_argument(
    "--dashboard-ids",
    help="Comma-separated list of dashboard IDs to export"
)

# Parse new arguments (after line 363)
card_ids: list[int] | None = None
if args.card_ids:
    try:
        card_ids = [int(c_id.strip()) for c_id in args.card_ids.split(",")]
    except ValueError:
        parser.error("--card-ids must be comma-separated integers")

dashboard_ids: list[int] | None = None
if args.dashboard_ids:
    try:
        dashboard_ids = [int(d_id.strip()) for d_id in args.dashboard_ids.split(",")]
    except ValueError:
        parser.error("--dashboard-ids must be comma-separated integers")
```

**Checklist**:
- [ ] Add argument definitions
- [ ] Add parsing logic for `--card-ids`
- [ ] Add parsing logic for `--dashboard-ids`
- [ ] Pass parsed values to ExportConfig constructor

---

## Phase 2: Export Service Methods (3-4 hours)

### Task 2.1: Implement `_build_minimal_collection_tree()`
**File**: `lib/services/export_service.py`

**New method after line 188**:

```python
def _build_minimal_collection_tree(self, collection_id: int | None) -> None:
    """Build minimal collection tree from target collection up to root.
    
    Used when exporting single cards/dashboards to include only the
    necessary parent collections, not siblings.
    
    Args:
        collection_id: The target collection ID to start from.
    """
    if collection_id is None:
        # Card is in root collection
        return
    
    if collection_id in self._processed_collections:
        # Already processed this collection
        return
    
    try:
        # Fetch the target collection data
        collection_data = self.client.get_collection(collection_id)
        
        # Mark as processed to avoid infinite loops
        self._processed_collections.add(collection_id)
        
        # Recursively process parent
        parent_id = collection_data.get("parent_id")
        if parent_id:
            self._build_minimal_collection_tree(parent_id)
        
        # Build path (reuse logic from _traverse_collections)
        parent_path = ""
        if parent_id and parent_id in self._collection_path_map:
            parent_path = self._collection_path_map[parent_id]
        
        sanitized_name = sanitize_filename(collection_data["name"])
        current_path = f"{parent_path}/{sanitized_name}".lstrip("/")
        self._collection_path_map[collection_id] = current_path
        
        # Create Collection object
        collection_obj = Collection(
            id=collection_id,
            name=collection_data["name"],
            description=collection_data.get("description"),
            slug=collection_data.get("slug"),
            parent_id=parent_id,
            personal_owner_id=collection_data.get("personal_owner_id"),
            path=current_path,
        )
        self.manifest.collections.append(collection_obj)
        
        # Write collection metadata file
        collection_meta_path = self.export_dir / current_path / "_collection.json"
        write_json_file(collection_data, collection_meta_path)
        
        logger.info(f"Added collection '{collection_data['name']}' to minimal tree")
        
    except MetabaseAPIError as e:
        logger.error(f"Failed to fetch collection {collection_id}: {e}")
        raise
```

**Checklist**:
- [ ] Implement method with proper recursion
- [ ] Handle None collection_id (root collection)
- [ ] Build _collection_path_map
- [ ] Create Collection objects
- [ ] Write _collection.json metadata
- [ ] Add error handling

### Task 2.2: Implement `run_export_single_card()`
**File**: `lib/services/export_service.py`

**New method after `run_export()` (after line 145)**:

```python
def run_export_single_card(self, card_id: int) -> None:
    """Export a single card and all its dependencies.
    
    Builds a minimal collection tree and exports the card with all
    recursively resolved dependencies.
    
    Args:
        card_id: The ID of the card to export.
    """
    logger.info(f"Exporting single card: ID {card_id}")
    self.export_dir.mkdir(parents=True, exist_ok=True)
    
    try:
        # Fetch the card
        card_data = self.client.get_card(card_id)
        
        # Build minimal collection tree
        collection_id = card_data.get("collection_id")
        if collection_id:
            logger.info(f"Card is in collection {collection_id}, building collection tree...")
            self._build_minimal_collection_tree(collection_id)
        
        # Export the card with all dependencies
        logger.info(f"Exporting card {card_id} with dependencies...")
        self._export_card_with_dependencies(card_id, base_path="")
        
        # Fetch and store databases
        logger.info("Fetching database metadata...")
        self._fetch_and_store_databases()
        
        # Write manifest
        manifest_path = self.export_dir / "manifest.json"
        logger.info(f"Writing manifest to {manifest_path}")
        write_json_file(self.manifest, manifest_path)
        
        # Print summary
        logger.info("=" * 80)
        logger.info("Export Summary:")
        logger.info(f"  Collections: {len(self.manifest.collections)}")
        logger.info(f"  Cards: {len(self.manifest.cards)}")
        logger.info(f"  Databases: {len(self.manifest.databases)}")
        logger.info("=" * 80)
        logger.info("Single card export completed successfully.")
        
    except Exception as e:
        logger.error(f"Failed to export card {card_id}: {e}", exc_info=True)
        raise
```

**Checklist**:
- [ ] Implement method
- [ ] Build collection tree
- [ ] Call _export_card_with_dependencies()
- [ ] Fetch databases
- [ ] Write manifest
- [ ] Add proper logging

### Task 2.3: Implement `run_export_single_dashboard()`
**File**: `lib/services/export_service.py`

**New method after `run_export_single_card()`**:

```python
def run_export_single_dashboard(self, dashboard_id: int) -> None:
    """Export a single dashboard and all its card dependencies.
    
    Builds a minimal collection tree and exports the dashboard with all
    referenced cards and their dependencies.
    
    Args:
        dashboard_id: The ID of the dashboard to export.
    """
    logger.info(f"Exporting single dashboard: ID {dashboard_id}")
    self.export_dir.mkdir(parents=True, exist_ok=True)
    
    try:
        # Fetch the dashboard
        dashboard_data = self.client.get_dashboard(dashboard_id)
        
        # Build minimal collection tree
        collection_id = dashboard_data.get("collection_id")
        if collection_id:
            logger.info(f"Dashboard is in collection {collection_id}, building tree...")
            self._build_minimal_collection_tree(collection_id)
        
        # Export cards from dashcards
        logger.info("Exporting dashboard cards...")
        for dashcard in dashboard_data.get("dashcards", []):
            card_id = dashcard.get("card_id")
            if card_id:
                logger.info(f"  Exporting card {card_id} from dashcard...")
                self._export_card_with_dependencies(card_id, base_path="")
        
        # Export cards from parameters (filter value sources)
        for param in dashboard_data.get("parameters", []):
            if "values_source_config" in param:
                card_id = param["values_source_config"].get("card_id")
                if card_id:
                    logger.info(f"  Exporting card {card_id} from parameter...")
                    self._export_card_with_dependencies(card_id, base_path="")
        
        # Export the dashboard itself
        logger.info(f"Exporting dashboard {dashboard_id}...")
        self._export_dashboard(dashboard_id, base_path="")
        
        # Fetch and store databases
        logger.info("Fetching database metadata...")
        self._fetch_and_store_databases()
        
        # Write manifest
        manifest_path = self.export_dir / "manifest.json"
        logger.info(f"Writing manifest to {manifest_path}")
        write_json_file(self.manifest, manifest_path)
        
        # Print summary
        logger.info("=" * 80)
        logger.info("Export Summary:")
        logger.info(f"  Collections: {len(self.manifest.collections)}")
        logger.info(f"  Cards: {len(self.manifest.cards)}")
        logger.info(f"  Dashboards: {len(self.manifest.dashboards)}")
        logger.info(f"  Databases: {len(self.manifest.databases)}")
        logger.info("=" * 80)
        logger.info("Single dashboard export completed successfully.")
        
    except Exception as e:
        logger.error(f"Failed to export dashboard {dashboard_id}: {e}", exc_info=True)
        raise
```

**Checklist**:
- [ ] Implement method
- [ ] Build collection tree
- [ ] Export cards from dashcards
- [ ] Export cards from parameters
- [ ] Call _export_dashboard()
- [ ] Fetch databases
- [ ] Write manifest
- [ ] Add proper logging

### Task 2.4: Update `run_export()` to route based on config
**File**: `lib/services/export_service.py`

**Modify lines 82-110**:

```python
def run_export(self) -> None:
    """Main entry point to start the export process."""
    logger.info(f"Starting Metabase export from {self.config.source_url}")
    logger.info(f"Export directory: {self.export_dir.resolve()}")

    try:
        # Route to appropriate export method based on config
        if self.config.card_ids:
            for card_id in self.config.card_ids:
                self.run_export_single_card(card_id)
        
        elif self.config.dashboard_ids:
            for dashboard_id in self.config.dashboard_ids:
                self.run_export_single_dashboard(dashboard_id)
        
        else:
            # Default: export collections (existing behavior)
            logger.info("Fetching source databases...")
            self._fetch_and_store_databases()

            logger.info("Fetching collection tree...")
            collection_tree = self.client.get_collections_tree()

            # ... rest of existing collection export logic ...
            # (keep existing code from line 96 onwards)
```

**Checklist**:
- [ ] Add card_ids routing
- [ ] Add dashboard_ids routing
- [ ] Keep existing collection export as default
- [ ] Test that existing behavior is unchanged

---

## Phase 3: Testing (4-6 hours)

### Task 3.1: Unit Tests - Collection Tree Building
**File**: `tests/test_export_service.py` (create if needed)

```python
def test_build_minimal_collection_tree_single_level():
    """Test building minimal tree for card in single-level collection."""
    # Test setup: mock client returning collection
    # Verify: Collection object created, _collection_path_map updated, manifest updated
    
def test_build_minimal_collection_tree_nested():
    """Test building minimal tree for nested collections."""
    # Test setup: mock client returning nested collections (3 levels)
    # Verify: All 3 collections in manifest, correct path hierarchy

def test_build_minimal_collection_tree_root():
    """Test handling card in root collection."""
    # Test setup: card_data with collection_id=None
    # Verify: No collections added, method returns gracefully
```

**Checklist**:
- [ ] Test single-level collection
- [ ] Test nested collections (3+ levels)
- [ ] Test root collection (None)
- [ ] Test collection fetch failure (error handling)

### Task 3.2: Integration Tests - Single Card Export
**File**: `tests/test_export_integration.py` (create if needed)

```python
def test_export_single_card_no_dependencies():
    """Export a simple card with no dependencies."""
    # Setup: Create export config with card_ids=[123]
    # Run export
    # Verify: manifest.json created, contains 1 card, 1 collection, correct database

def test_export_single_card_with_dependencies():
    """Export card that depends on other cards."""
    # Setup: Card A depends on Card B depends on Card C
    # Run export with card_ids=[A]
    # Verify: manifest contains all 3 cards, collections, correct order

def test_export_single_card_dependency_order():
    """Verify dependency cards are imported before dependent."""
    # Setup: Export card with dependency
    # Verify: manifest.cards order has dependencies first
```

**Checklist**:
- [ ] Simple card export
- [ ] Card with dependencies
- [ ] Dependency ordering
- [ ] Collection hierarchy verification

### Task 3.3: Integration Tests - Single Dashboard Export
**File**: `tests/test_export_integration.py`

```python
def test_export_single_dashboard_with_cards():
    """Export dashboard with multiple cards."""
    # Setup: Dashboard with 3 cards
    # Run export
    # Verify: manifest contains dashboard + all 3 cards

def test_export_single_dashboard_with_parameter_cards():
    """Export dashboard with parameter value sources."""
    # Setup: Dashboard with parameter that sources values from card
    # Run export
    # Verify: Parameter source card is exported

def test_export_single_dashboard_cards_with_dependencies():
    """Export dashboard with cards that have dependencies."""
    # Setup: Dashboard with cards that depend on models
    # Run export
    # Verify: All cards and dependencies exported
```

**Checklist**:
- [ ] Dashboard with multiple cards
- [ ] Dashboard with parameter value sources
- [ ] Card dependencies are exported
- [ ] Collection tree is built

### Task 3.4: End-to-End Tests - Export & Import
**File**: `tests/test_e2e_single_items.py`

```python
def test_e2e_export_and_import_single_card():
    """Export single card from source, import to target, verify."""
    # Setup: Source and target instances
    # Export: Card 123 from source
    # Import: To target
    # Verify: Card 123 exists in target, in correct collection

def test_e2e_export_and_import_single_dashboard():
    """Export single dashboard from source, import to target, verify."""
    # Setup: Source and target instances
    # Export: Dashboard 456 from source
    # Import: To target
    # Verify: Dashboard exists, cards are referenced correctly
```

**Checklist**:
- [ ] E2E single card export/import
- [ ] E2E single dashboard export/import
- [ ] Verify data integrity after round-trip

---

## Phase 4: Documentation (1-2 hours)

### Task 4.1: Update README
**File**: `README.md`

Add section under "Usage":
```markdown
### Exporting Single Cards or Dashboards

To export only specific cards or dashboards instead of entire collections:

**Single Card**:
```bash
python export_metabase.py \
  --source-url https://source.metabase.com \
  --export-dir ./export \
  --card-ids 123,456
```

**Single Dashboard**:
```bash
python export_metabase.py \
  --source-url https://source.metabase.com \
  --export-dir ./export \
  --dashboard-ids 789
```

**Mixed Export**:
```bash
python export_metabase.py \
  --source-url https://source.metabase.com \
  --export-dir ./export \
  --root-collections 1 \
  --card-ids 100,200
```

**Note**: Collections are automatically included if you export cards/dashboards.
```

### Task 4.2: Update CONTRIBUTING.md
Add reference to new functionality in architecture section.

---

## Phase 5: Code Review & Polish (1-2 hours)

### Task 5.1: Review & Cleanup
**Checklist**:
- [ ] All code follows existing style conventions
- [ ] All methods have docstrings
- [ ] All error cases have error handling
- [ ] No breaking changes to existing code
- [ ] All tests pass
- [ ] Code reviewed by team

### Task 5.2: Edge Case Testing
**Checklist**:
- [ ] Card/dashboard with archived dependencies
- [ ] Card/dashboard with deleted parent collection
- [ ] Circular dependencies
- [ ] Very large dependency chains (10+ levels)
- [ ] Collections with special characters in names

---

## Summary

**Total estimated time**: 9-14 hours
**Total new code**: ~200 lines
**Total test code**: ~500 lines
**Risk level**: Low
**Backward compatibility**: 100%

### Prerequisites
- [ ] Local development environment set up
- [ ] Test Metabase instances available
- [ ] git branch created for feature

### Go/No-Go Checklist
- [ ] Architecture design reviewed
- [ ] Dependency analysis complete
- [ ] Team approved roadmap
- [ ] Test plan defined
- [ ] Performance impact assessed

