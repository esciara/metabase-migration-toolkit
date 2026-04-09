# Metabase Migration Toolkit: File State Analysis

## Executive Summary

This document provides a comprehensive overview of the current state of key files in the Metabase Migration Toolkit project, focusing on unmapped ID tracking, ID mapping infrastructure, and query remapping.

---

## 1. `lib/models_core.py` — UnmappedIDCollector & UnmappedIDEvent

### UnmappedIDEvent (Dataclass)
Located at lines 197-210. Full definition:

```python
@dataclasses.dataclass
class UnmappedIDEvent:
    """A single occurrence of an unmapped ID during import."""

    id_type: Literal["field", "table", "card", "dashboard", "database"]
    source_id: int
    source_database_id: int | None
    source_context: str | None  # e.g. "table 'region_department', column 'num_dep'"
    entity_type: Literal["card", "dashboard"]
    entity_source_id: int
    entity_name: str
    location: str  # e.g. "template-tag 'Dept' → dimension[2]"
    action: Literal["skipped", "stripped"]
```

**Key Points:**
- All fields are required in the constructor
- `source_database_id` and `source_context` can be None
- Represents a single unmapped ID occurrence with context about where it was found

### UnmappedIDCollector (Dataclass)
Located at lines 212-307. Full definition:

```python
@dataclasses.dataclass
class UnmappedIDCollector:
    """Collects unmapped ID events during import for reporting."""

    events: list[UnmappedIDEvent] = dataclasses.field(default_factory=list)

    def record(
        self,
        id_type: Literal["field", "table", "card", "dashboard", "database"],
        source_id: int,
        entity_type: Literal["card", "dashboard"],
        entity_source_id: int,
        entity_name: str,
        location: str,
        action: Literal["skipped", "stripped"],
        source_database_id: int | None = None,
        source_context: str | None = None,
    ) -> None:
        """Record an unmapped ID event."""
        self.events.append(
            UnmappedIDEvent(
                id_type=id_type,
                source_id=source_id,
                source_database_id=source_database_id,
                source_context=source_context,
                entity_type=entity_type,
                entity_source_id=entity_source_id,
                entity_name=entity_name,
                location=location,
                action=action,
            )
        )

    def to_report_dict(self) -> dict[str, Any]:
        """Serialize to the unmapped_ids report section.

        Groups events by id_type, then by (source_id, source_database_id),
        listing all affected entities under each unmapped ID.
        
        Returns: dict mapping id_type -> list of entry dicts with:
        - source_id
        - source_database_id
        - source_context (if available)
        - affected_entities: list of dicts with entity_type, entity_source_id, 
                           entity_name, location, action
        """
        if not self.events:
            return {}

        # Group by id_type → (source_id, source_database_id) → list of events
        grouped: dict[str, dict[tuple[int, int | None], list[UnmappedIDEvent]]] = {}
        for event in self.events:
            if event.id_type not in grouped:
                grouped[event.id_type] = {}
            key = (event.source_id, event.source_database_id)
            if key not in grouped[event.id_type]:
                grouped[event.id_type][key] = []
            grouped[event.id_type][key].append(event)

        result: dict[str, Any] = {}
        for id_type, entries in grouped.items():
            id_type_list: list[dict[str, Any]] = []
            for (source_id, source_database_id), events in entries.items():
                entry: dict[str, Any] = {
                    "source_id": source_id,
                    "source_database_id": source_database_id,
                    "affected_entities": [
                        {
                            "entity_type": e.entity_type,
                            "entity_source_id": e.entity_source_id,
                            "entity_name": e.entity_name,
                            "location": e.location,
                            "action": e.action,
                        }
                        for e in events
                    ],
                }
                # Include source_context from the first event that has it
                for e in events:
                    if e.source_context:
                        entry["source_context"] = e.source_context
                        break
                id_type_list.append(entry)
            result[id_type] = id_type_list

        return result

    @property
    def has_events(self) -> bool:
        """Whether any unmapped IDs were recorded."""
        return len(self.events) > 0

    @property
    def skipped_count(self) -> int:
        """Number of entities skipped due to unmapped IDs.
        
        Returns count of unique (entity_type, entity_source_id) pairs
        where action == 'skipped'.
        """
        return len(
            {(e.entity_type, e.entity_source_id) for e in self.events if e.action == "skipped"}
        )

    @property
    def stripped_count(self) -> int:
        """Number of fields stripped due to unmapped IDs.
        
        Returns count of events where action == 'stripped'.
        """
        return len([e for e in self.events if e.action == "stripped"])
```

**Key Points:**
- `record()` creates and appends events
- `to_report_dict()` groups events hierarchically: id_type → (source_id, source_db_id) → affected entities
- `has_events`, `skipped_count`, `stripped_count` are properties for quick metrics
- Deduplication of skipped entities by (entity_type, entity_source_id) pair

---

## 2. `tests/test_models_core.py` — Test Patterns

### Test Classes & Coverage:
1. **TestUnmappedIDEvent** (lines 11-51)
   - `test_event_creation()` - Tests creating event with all fields
   - `test_event_minimal()` - Tests optional fields as None

2. **TestUnmappedIDCollectorRecord** (lines 54-107)
   - `test_unmapped_id_collector_record()` - Tests basic record and multiple events
   - `test_record_stripped_event()` - Tests recording 'stripped' action

3. **TestUnmappedIDCollectorCounts** (lines 109-166)
   - `test_unmapped_id_collector_counts()` - Tests counting skipped entities (deduped) and stripped fields
   - `test_counts_empty_collector()` - Tests empty collector returns 0

4. **TestUnmappedIDCollectorToReportDict** (lines 168-234)
   - `test_unmapped_id_collector_to_report_dict()` - Tests grouping structure and source_context inclusion
   - `test_to_report_dict_empty()` - Tests empty collector returns {}

### Key Test Patterns:
- Creates collector instances
- Records multiple events with varying id_types, source_ids, entity_types
- Asserts on `has_events`, `skipped_count`, `stripped_count` properties
- Validates `to_report_dict()` grouping by id_type and (source_id, source_database_id)
- Tests that source_context is included when available
- Tests deduplication of skipped entities by (entity_type, entity_source_id)

---

## 3. `lib/remapping/id_mapper.py` — Structure & Attributes

### Class Overview (lines 15-318):

```python
class IDMapper:
    """Manages ID mappings between source and target Metabase instances."""

    def __init__(
        self,
        manifest: Manifest,
        db_map: DatabaseMap,
        client: MetabaseClient | None = None,
    ) -> None:
        # ID mappings: source_id -> target_id
        self._collection_map: dict[int, int] = {}
        self._card_map: dict[int, int] = {}
        self._dashboard_map: dict[int, int] = {}
        self._group_map: dict[int, int] = {}

        # Table and field mappings: (source_db_id, source_id) -> target_id
        self._table_map: dict[tuple[int, int], int] = {}
        self._field_map: dict[tuple[int, int], int] = {}

        # Cache of target database metadata
        self._target_db_metadata: dict[int, dict[str, Any]] = {}
```

### Existing Methods (Summary):
- Property accessors: `collection_map`, `card_map`, `dashboard_map`, `group_map`, `table_map`, `field_map`
- Setters: `set_collection_mapping()`, `set_card_mapping()`, `set_dashboard_mapping()`, `set_group_mapping()`
- Resolvers: `resolve_db_id()`, `resolve_table_id()`, `resolve_field_id()`, `resolve_collection_id()`, `resolve_card_id()`, `resolve_dashboard_id()`
- Mapping builders: `build_table_and_field_mappings()`, `_map_tables_and_fields()`, `_map_fields()`

### **IMPORTANT**: Methods NOT YET IMPLEMENTED:
- ❌ `get_source_field_context(source_db_id: int, source_field_id: int) -> str | None`
- ❌ `get_source_table_context(source_db_id: int, source_table_id: int) -> str | None`

These methods would need to:
- Access source database metadata from `self.manifest.database_metadata`
- Look up table/field names to construct human-readable context strings like:
  - Field: `"table 'region_department', column 'num_dep'"`
  - Table: `"table 'region_department'"`

---

## 4. `tests/test_query_remapper.py` — Existing Test Patterns

### File Structure (1 file, 531 lines):
Located at lines 1-531 in the test file.

### Helper Functions:
```python
def _make_id_mapper(
    *,
    db_mapping: dict[int, int] | None = None,
    table_mapping: dict[tuple[int, int], int] | None = None,
    field_mapping: dict[tuple[int, int], int] | None = None,
    card_mapping: dict[int, int] | None = None,
) -> IDMapper:
    """Build an IDMapper pre-loaded with the given mappings."""
    # Creates Manifest and DatabaseMap, injects mappings into internal dicts

def _make_remapper(
    mapper: IDMapper,
    mode: str = "skip",
) -> QueryRemapper:
    """Build a QueryRemapper in the given unmapped_ids_mode."""
```

### Test Classes:
1. **TestFieldUnmappedRaises** - Unmapped field IDs raise FieldMappingError
2. **TestTableUnmappedRaises** - Unmapped table IDs raise TableMappingError
3. **TestCardUnmappedRaises** - Unmapped card IDs raise CardMappingError (7 leak scenarios)
4. **TestForceModeKeeps** - Force mode preserves source IDs without raising
5. **TestTier2StripResultMetadata** - Result metadata strips unmapped IDs + warnings
6. **TestTier2StripClickBehavior** - Click behavior strips unmapped targetId
7. **TestTier2StripVisualizerRefs** - Visualizer refs strip unmapped card IDs
8. **TestTier2StripLinkCardEntity** - Link card settings strip unmapped entities

### Key Test Patterns:
- Create mapper with specific mappings (or empty for unmapped scenarios)
- Create remapper in 'skip' or 'force' mode
- Call specific remap method and assert:
  - For 'skip' mode: expects exception (FieldMappingError, TableMappingError, CardMappingError)
  - For 'force' mode: no exception, original ID preserved
  - For Tier 2: data structure modified (ID stripped), warnings recorded
- Check `remapper._current_warnings` list for RemapWarning objects

---

## 5. `lib/remapping/query_remapper.py` — Structure & Methods

### File Statistics:
- **Lines**: 1268 total
- **Key dataclass**: `RemapWarning` (lines 36-43)

### RemapWarning Dataclass:
```python
@dataclasses.dataclass
class RemapWarning:
    """Warning about a stripped unmapped ID during remapping."""

    id_type: str  # "field", "table", "card", "dashboard", "database"
    source_id: int
    source_database_id: int | None
    location: str  # "result_metadata[].id", "click_behavior.targetId", etc.
```

### QueryRemapper Class (lines 46-1268):

**Constructor:**
```python
def __init__(
    self,
    id_mapper: IDMapper,
    unmapped_ids_mode: Literal["skip", "strict", "force"] = "skip",
) -> None:
    self.id_mapper = id_mapper
    self.unmapped_ids_mode = unmapped_ids_mode
    self._current_warnings: list[RemapWarning] = []
```

**Key Public Methods:**
- `remap_card_data()` - Main entry point for card remapping
- `remap_dashboard_parameters()` - Remap dashboard parameter configs
- `remap_dashcard_parameter_mappings()` - Remap dashcard parameter mappings
- `remap_native_query()` - Remap native SQL query
- `remap_dashcard_visualization_settings()` - Remap visualization settings
- `remap_field_ids_recursively()` - Recursively find and remap field IDs

**Key Private Methods (Tier 1 — raise errors on unmapped):**
- `_remap_source_table()` - Remap source-table and source-card (handles card refs)
- `_remap_card_reference()` - Remap card__123 format refs
- `_remap_joins()` - Remap joins with table/card refs
- `_remap_list()` - Handle field refs in lists ["field", metadata, field_id] or ["field", field_id, opts]
- `_remap_query_clauses()` - Remap clauses (filter, aggregation, etc.)
- `_remap_template_tags()` - Remap native query template tags with card-id
- `_remap_sql_card_references()` - Remap {{#123-model}} refs in SQL

**Key Private Methods (Tier 2 — strip unmapped IDs + warnings):**
- `_remap_result_metadata()` - Strip unmapped field IDs and field_refs
- `_remap_click_behavior()` - Strip unmapped card/dashboard targetIds
- `_remap_visualizer_source_id()` - Strip unmapped card in sourceId
- `_remap_data_source_name_ref()` - Strip unmapped card in $_card:123_name
- `_remap_link_card_settings()` - Strip unmapped card/dashboard entities

**Template Tag Handling (lines 854-965):**
- `_remap_template_tags()` - Main entry for template tag remapping
  - Handles "card" type tags with card-id remapping
  - Handles "dimension" type tags with field ID remapping
  - Handles "database" type tags
  - Records warnings for unmapped IDs in skip mode
- `_remap_tag_name()` - Updates tag name when card-id is remapped

### Current Limitations:
- ❌ No context lookups for source table/field names
- ✅ Stores warnings in `_current_warnings` during remapping
- ✅ Warnings are NOT automatically persisted to UnmappedIDCollector

---

## 6. `lib/services/import_service.py` — _log_import_summary()

### Method Location: Lines 409-443

```python
def _log_import_summary(self) -> None:
    """Logs the import summary."""
    manifest = self._get_manifest()
    logger.info("\n--- Import Summary ---")
    summary = self.report.summary
    logger.info(
        f"Collections: {summary['collections']['created']} created, "
        f"{summary['collections']['updated']} updated, "
        f"{summary['collections']['skipped']} skipped, "
        f"{summary['collections']['failed']} failed."
    )
    logger.info(
        f"Cards: {summary['cards']['created']} created, "
        f"{summary['cards']['updated']} updated, "
        f"{summary['cards']['skipped']} skipped, "
        f"{summary['cards']['failed']} failed."
    )
    if manifest.dashboards:
        logger.info(
            f"Dashboards: {summary['dashboards']['created']} created, "
            f"{summary['dashboards']['updated']} updated, "
            f"{summary['dashboards']['skipped']} skipped, "
            f"{summary['dashboards']['failed']} failed."
        )

    # Log unmapped ID summary if any events were recorded
    context = self._get_context()
    collector = context.unmapped_id_collector
    if collector.has_events:
        logger.warning(
            f"{len(collector.events)} unmapped IDs caused "
            f"{collector.skipped_count} entities to be skipped and "
            f"{collector.stripped_count} fields to be stripped. "
            f"See import report for details."
        )
```

### Current Behavior:
- Logs import summary (collections, cards, dashboards counts)
- If collector has events, logs:
  - Total event count
  - Skipped entity count (deduplicated)
  - Stripped field count
  - Message to check report for details

### Integration with UnmappedIDCollector:
- Uses `context.unmapped_id_collector` property
- Calls `has_events`, `skipped_count`, `stripped_count` properties
- Already implemented to reference the collector

### Report Saving (lines 445-459):
```python
def _save_report(self) -> None:
    """Saves the import report to a file."""
    import dataclasses

    report_path = (
        self.export_dir
        / f"import_report_{datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d_%H%M%S')}.json"
    )
    report_data = dataclasses.asdict(self.report)
    context = self._get_context()
    collector = context.unmapped_id_collector
    if collector.has_events:
        report_data["unmapped_ids"] = collector.to_report_dict()
    write_json_file(report_data, report_path)
    logger.info(f"Full import report saved to {report_path}")
```

---

## 7. `tests/integration/test_e2e_export_import.py` — Integration Tests

### File Structure:
- **Purpose**: End-to-end integration tests using Docker Compose
- **Scope**: Tests export/import workflow with real Metabase instances
- **Lines**: 100+ (continues beyond sample)

### Test Infrastructure:
- Uses Docker Compose to spin up source and target Metabase instances
- Creates test data in source instance
- Exports from source
- Imports to target
- Verifies data integrity

### Helper Functions (lines 83-258):
1. `get_query_from_card()` - Extracts query from card (handles v56/v57 formats)
2. `get_source_card_reference()` - Gets card ref as "card__123" string
3. `get_join_source_card_reference()` - Gets card ref from join clause
4. `get_native_query_from_card()` - Extracts native SQL query
5. `is_native_query()` - Checks if card uses native SQL
6. `get_template_tags_from_card()` - Gets template tags from native query
7. `has_expression_name()` - Checks if card has expression (v56/v57 format aware)
8. `has_order_by()` - Checks if card has order-by clause

### Version Detection:
- `get_metabase_version()` - Gets version from MB_METABASE_VERSION env var
- `is_v57()`, `is_v58()`, `is_mbql5()` - Version checking helpers

### Test Coverage Areas:
- Collections (nested hierarchy, descriptions)
- Cards (simple queries, complex with joins/filters, dependencies)
- Models (type=dataset)
- Dashboards (with parameters, dashcards, filters)
- Permissions (groups, data permissions, collection permissions)

### Usage:
```bash
# v57 testing
MB_METABASE_VERSION=v57 pytest tests/integration/test_e2e_export_import.py -v -s

# v58 testing
MB_METABASE_VERSION=v58 pytest tests/integration/test_e2e_export_import.py -v -s
```

---

## Summary Table

| Component | Location | Status | Key Methods/Properties |
|-----------|----------|--------|------------------------|
| **UnmappedIDEvent** | `lib/models_core.py:197-210` | ✅ Complete | All fields required; 8 fields total |
| **UnmappedIDCollector** | `lib/models_core.py:212-307` | ✅ Complete | `record()`, `to_report_dict()`, `has_events`, `skipped_count`, `stripped_count` |
| **Test Suite** | `tests/test_models_core.py` | ✅ Complete | 4 test classes, 7 test methods |
| **IDMapper** | `lib/remapping/id_mapper.py:15-318` | ⚠️ Partial | Missing: `get_source_field_context()`, `get_source_table_context()` |
| **QueryRemapper** | `lib/remapping/query_remapper.py:45-1268` | ✅ Complete | 25+ methods; Tier 1 raises errors; Tier 2 strips + warns |
| **QueryRemapper Tests** | `tests/test_query_remapper.py` | ✅ Complete | 8 test classes, 20+ test methods |
| **ImportService** | `lib/services/import_service.py` | ✅ Partial | `_log_import_summary()` integrated with collector |
| **Integration Tests** | `tests/integration/test_e2e_export_import.py` | ✅ Active | Version-aware (v56/v57/v58), 7+ helper functions |

---

## Architecture Integration Points

### Data Flow:
1. **QueryRemapper** remaps query/card data and records **RemapWarnings** in `_current_warnings`
2. **ImportContext** holds **UnmappedIDCollector** instance
3. **Handlers** (CardHandler, DashboardHandler) call QueryRemapper, then transfer warnings to collector
4. **ImportService** calls `_log_import_summary()` which reads from collector
5. **ImportService** calls `_save_report()` which serializes collector via `to_report_dict()`

### Key Data Structures:
- **QueryRemapper._current_warnings**: `list[RemapWarning]` — ephemeral per remap operation
- **UnmappedIDCollector.events**: `list[UnmappedIDEvent]` — persistent across import
- **UnmappedIDCollector.to_report_dict()**: Output format for JSON report

