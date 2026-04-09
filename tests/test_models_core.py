"""
Unit tests for UnmappedIDEvent and UnmappedIDCollector in lib/models_core.py.

Tests cover recording events, grouping, deduplication, counts,
and serialization to the report dict structure.
"""

from lib.models_core import UnmappedIDCollector, UnmappedIDEvent


class TestUnmappedIDEvent:
    """Tests for the UnmappedIDEvent dataclass."""

    def test_event_creation(self):
        """Test creating an UnmappedIDEvent with all fields."""
        event = UnmappedIDEvent(
            id_type="field",
            source_id=500,
            source_database_id=1,
            source_context="table 'region_department', column 'num_dep'",
            entity_type="card",
            entity_source_id=42,
            entity_name="Revenue Report",
            location="template-tag 'Dept' → dimension[2]",
            action="skipped",
        )
        assert event.id_type == "field"
        assert event.source_id == 500
        assert event.source_database_id == 1
        assert event.source_context == "table 'region_department', column 'num_dep'"
        assert event.entity_type == "card"
        assert event.entity_source_id == 42
        assert event.entity_name == "Revenue Report"
        assert event.location == "template-tag 'Dept' → dimension[2]"
        assert event.action == "skipped"

    def test_event_minimal(self):
        """Test creating an event with optional fields as None."""
        event = UnmappedIDEvent(
            id_type="table",
            source_id=100,
            source_database_id=None,
            source_context=None,
            entity_type="dashboard",
            entity_source_id=10,
            entity_name="Sales Dash",
            location="source-table",
            action="stripped",
        )
        assert event.source_database_id is None
        assert event.source_context is None


class TestUnmappedIDCollectorRecord:
    """Tests for UnmappedIDCollector.record()."""

    def test_unmapped_id_collector_record(self):
        """Test basic record and deduplication."""
        collector = UnmappedIDCollector()
        assert not collector.has_events
        assert len(collector.events) == 0

        # Record a first event
        collector.record(
            id_type="field",
            source_id=500,
            entity_type="card",
            entity_source_id=42,
            entity_name="Revenue Report",
            location="template-tag 'Dept' → dimension[2]",
            action="skipped",
            source_database_id=1,
            source_context="table 'region_department', column 'num_dep'",
        )
        assert collector.has_events
        assert len(collector.events) == 1
        assert collector.events[0].id_type == "field"
        assert collector.events[0].source_id == 500

        # Record a second event — same unmapped ID, different entity
        collector.record(
            id_type="field",
            source_id=500,
            entity_type="card",
            entity_source_id=43,
            entity_name="Other Report",
            location="filter[0]",
            action="skipped",
            source_database_id=1,
        )
        assert len(collector.events) == 2

    def test_record_stripped_event(self):
        """Test recording a 'stripped' event."""
        collector = UnmappedIDCollector()
        collector.record(
            id_type="field",
            source_id=600,
            entity_type="dashboard",
            entity_source_id=10,
            entity_name="Sales Dash",
            location="parameter_mappings[0]",
            action="stripped",
        )
        assert len(collector.events) == 1
        assert collector.events[0].action == "stripped"


class TestUnmappedIDCollectorCounts:
    """Tests for skipped_count and stripped_count properties."""

    def test_unmapped_id_collector_counts(self):
        """Test skipped_count and stripped_count properties."""
        collector = UnmappedIDCollector()

        # Two skipped events for the SAME entity (should count as 1 skipped entity)
        collector.record(
            id_type="field",
            source_id=500,
            entity_type="card",
            entity_source_id=42,
            entity_name="Revenue Report",
            location="dimension[2]",
            action="skipped",
        )
        collector.record(
            id_type="table",
            source_id=100,
            entity_type="card",
            entity_source_id=42,
            entity_name="Revenue Report",
            location="source-table",
            action="skipped",
        )

        # One stripped event
        collector.record(
            id_type="field",
            source_id=600,
            entity_type="dashboard",
            entity_source_id=10,
            entity_name="Sales Dash",
            location="parameter_mappings[0]",
            action="stripped",
        )

        # A skipped event for a different entity
        collector.record(
            id_type="field",
            source_id=700,
            entity_type="card",
            entity_source_id=99,
            entity_name="Other Card",
            location="filter[0]",
            action="skipped",
        )

        assert collector.skipped_count == 2  # 2 unique entities skipped (42, 99)
        assert collector.stripped_count == 1  # 1 stripped event

    def test_counts_empty_collector(self):
        """Test counts on empty collector."""
        collector = UnmappedIDCollector()
        assert collector.skipped_count == 0
        assert collector.stripped_count == 0


class TestUnmappedIDCollectorToReportDict:
    """Tests for to_report_dict() serialization."""

    def test_unmapped_id_collector_to_report_dict(self):
        """Test grouping and structure of to_report_dict output."""
        collector = UnmappedIDCollector()

        # Two events for the same field, different entities
        collector.record(
            id_type="field",
            source_id=500,
            entity_type="card",
            entity_source_id=42,
            entity_name="Revenue Report",
            location="dimension[2]",
            action="skipped",
            source_database_id=1,
            source_context="table 'users', column 'email'",
        )
        collector.record(
            id_type="field",
            source_id=500,
            entity_type="card",
            entity_source_id=43,
            entity_name="Other Report",
            location="filter[0]",
            action="skipped",
            source_database_id=1,
        )

        # One event for a table
        collector.record(
            id_type="table",
            source_id=100,
            entity_type="dashboard",
            entity_source_id=10,
            entity_name="Sales Dash",
            location="source-table",
            action="stripped",
            source_database_id=2,
        )

        report = collector.to_report_dict()

        # New structure: top-level by_type wrapper
        assert "by_type" in report
        assert "action_summary" in report
        by_type = report["by_type"]

        # Should be grouped by id_type
        assert "field" in by_type
        assert "table" in by_type

        # Under "field", should group by (source_id, source_database_id)
        field_data = by_type["field"]
        assert field_data["count"] == 1  # One unique (500, 1)
        entry = field_data["items"][0]
        assert entry["source_id"] == 500
        assert entry["source_database_id"] == 1
        assert len(entry["affected_entities"]) == 2

        # Affected entity uses new key names
        ae = entry["affected_entities"][0]
        assert "source_id" in ae
        assert "name" in ae
        assert "action_taken" in ae

        # Under "table"
        table_data = by_type["table"]
        assert table_data["count"] == 1
        assert table_data["items"][0]["source_id"] == 100

    def test_to_report_dict_empty(self):
        """Test to_report_dict with no events."""
        collector = UnmappedIDCollector()
        report = collector.to_report_dict()
        assert report == {}

    def test_unmapped_id_collector_to_report_dict_grouping(self):
        """Test that to_report_dict groups events into by_type with count and items."""
        collector = UnmappedIDCollector()

        # Two field events for different source IDs
        collector.record(
            id_type="field",
            source_id=500,
            entity_type="card",
            entity_source_id=42,
            entity_name="Revenue Report",
            location="dimension[2]",
            action="skipped",
            source_database_id=1,
            source_context="table 'users', column 'email'",
        )
        collector.record(
            id_type="field",
            source_id=600,
            entity_type="card",
            entity_source_id=43,
            entity_name="Other Report",
            location="filter[0]",
            action="stripped",
            source_database_id=1,
        )

        # One table event
        collector.record(
            id_type="table",
            source_id=100,
            entity_type="dashboard",
            entity_source_id=10,
            entity_name="Sales Dash",
            location="source-table",
            action="stripped",
            source_database_id=2,
        )

        report = collector.to_report_dict()

        # Must have the top-level by_type wrapper
        assert "by_type" in report, "Report must contain 'by_type' key"
        by_type = report["by_type"]

        # Grouped by id_type
        assert "field" in by_type
        assert "table" in by_type

        # Each type has count and items
        assert "count" in by_type["field"]
        assert "items" in by_type["field"]
        assert by_type["field"]["count"] == 2  # Two distinct field source IDs (500, 600)

        assert by_type["table"]["count"] == 1
        assert len(by_type["table"]["items"]) == 1

        # Check item structure: source_context from first event with it
        field_items = by_type["field"]["items"]
        item_500 = next(i for i in field_items if i["source_id"] == 500)
        assert item_500["source_database_id"] == 1
        assert item_500["source_context"] == "table 'users', column 'email'"
        assert len(item_500["affected_entities"]) == 1

    def test_unmapped_id_collector_to_report_dict_action_summary(self):
        """Test action_summary with entities_skipped, fields_stripped, total_unmapped_ids."""
        collector = UnmappedIDCollector()

        # Two skipped events for different entities but same field
        collector.record(
            id_type="field",
            source_id=500,
            entity_type="card",
            entity_source_id=42,
            entity_name="Revenue Report",
            location="dimension[2]",
            action="skipped",
            source_database_id=1,
        )
        collector.record(
            id_type="field",
            source_id=500,
            entity_type="card",
            entity_source_id=43,
            entity_name="Other Report",
            location="filter[0]",
            action="skipped",
            source_database_id=1,
        )

        # One stripped event for a different unmapped ID
        collector.record(
            id_type="table",
            source_id=100,
            entity_type="dashboard",
            entity_source_id=10,
            entity_name="Sales Dash",
            location="source-table",
            action="stripped",
            source_database_id=2,
        )

        report = collector.to_report_dict()

        assert "action_summary" in report, "Report must contain 'action_summary' key"
        summary = report["action_summary"]

        # 2 unique entities skipped: (card, 42) and (card, 43)
        assert summary["entities_skipped"] == 2
        # 1 stripped event
        assert summary["fields_stripped"] == 1
        # 2 total unique unmapped IDs: (500, 1, "field") and (100, 2, "table")
        assert summary["total_unmapped_ids"] == 2

    def test_unmapped_id_collector_to_report_dict_dedup(self):
        """Test that same source ID affecting multiple entities is grouped correctly."""
        collector = UnmappedIDCollector()

        # Same field ID 500 in db 1 affects three different cards
        for card_id, card_name in [(42, "Card A"), (43, "Card B"), (44, "Card C")]:
            collector.record(
                id_type="field",
                source_id=500,
                entity_type="card",
                entity_source_id=card_id,
                entity_name=card_name,
                location="filter[0]",
                action="skipped",
                source_database_id=1,
                source_context="table 'orders', column 'region'",
            )

        report = collector.to_report_dict()
        by_type = report["by_type"]

        # Only one item in field group (source_id=500, source_database_id=1)
        assert by_type["field"]["count"] == 1
        item = by_type["field"]["items"][0]
        assert item["source_id"] == 500
        assert item["source_database_id"] == 1

        # But three affected entities
        assert len(item["affected_entities"]) == 3

        # Check affected entity structure matches plan spec
        entity = item["affected_entities"][0]
        assert "entity_type" in entity
        assert (
            "source_id" in entity
        ), "Affected entity must have 'source_id' key (not entity_source_id)"
        assert "name" in entity, "Affected entity must have 'name' key (not entity_name)"
        assert "action_taken" in entity, "Affected entity must have 'action_taken' key (not action)"
        assert "location" in entity
