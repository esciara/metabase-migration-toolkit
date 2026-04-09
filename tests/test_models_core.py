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

        # Should be grouped by id_type
        assert "field" in report
        assert "table" in report

        # Under "field", should group by (source_id, source_database_id)
        field_entries = report["field"]
        assert len(field_entries) == 1  # One unique (500, 1)
        entry = field_entries[0]
        assert entry["source_id"] == 500
        assert entry["source_database_id"] == 1
        assert len(entry["affected_entities"]) == 2

        # Under "table"
        table_entries = report["table"]
        assert len(table_entries) == 1
        assert table_entries[0]["source_id"] == 100

    def test_to_report_dict_empty(self):
        """Test to_report_dict with no events."""
        collector = UnmappedIDCollector()
        report = collector.to_report_dict()
        assert report == {}
