"""
Unit tests for lib/utils.py

Tests utility functions for logging, file operations, and string manipulation.
"""

import json
import logging
from pathlib import Path

from lib.utils import (
    TOOL_VERSION,
    CustomJsonEncoder,
    calculate_checksum,
    clean_dashboard_for_update,
    clean_for_create,
    sanitize_filename,
    setup_logging,
    write_json_file,
)


class TestSanitizeFilename:
    """Test suite for sanitize_filename function."""

    def test_sanitize_basic_string(self):
        """Test sanitization of a basic string."""
        result = sanitize_filename("Test File")
        assert result == "Test-File"

    def test_sanitize_with_slashes(self):
        """Test sanitization removes slashes."""
        result = sanitize_filename("Test/File\\Name")
        assert result == "Test-File-Name"

    def test_sanitize_with_invalid_chars(self):
        """Test sanitization removes invalid filename characters."""
        result = sanitize_filename('Test<>:"|?*File')
        assert result == "TestFile"

    def test_sanitize_multiple_spaces(self):
        """Test sanitization collapses multiple spaces."""
        result = sanitize_filename("Test    Multiple   Spaces")
        assert result == "Test-Multiple-Spaces"

    def test_sanitize_leading_trailing_hyphens(self):
        """Test sanitization removes leading/trailing hyphens."""
        result = sanitize_filename("  Test File  ")
        assert result == "Test-File"

    def test_sanitize_long_filename(self):
        """Test sanitization truncates long filenames."""
        long_name = "a" * 150
        result = sanitize_filename(long_name)
        assert len(result) == 100

    def test_sanitize_empty_string(self):
        """Test sanitization of empty string."""
        result = sanitize_filename("")
        assert result == ""

    def test_sanitize_special_characters(self):
        """Test sanitization with various special characters."""
        result = sanitize_filename("Test_File-Name.txt")
        assert result == "Test-File-Name.txt"


class TestCalculateChecksum:
    """Test suite for calculate_checksum function."""

    def test_calculate_checksum_basic(self, tmp_path: Path):
        """Test checksum calculation for a basic file."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello, World!")

        checksum = calculate_checksum(test_file)

        # SHA256 of "Hello, World!"
        expected = "dffd6021bb2bd5b0af676290809ec3a53191dd81c7f70a4b28688a362182986f"  # pragma: allowlist secret
        assert checksum == expected

    def test_calculate_checksum_empty_file(self, tmp_path: Path):
        """Test checksum calculation for an empty file."""
        test_file = tmp_path / "empty.txt"
        test_file.write_text("")

        checksum = calculate_checksum(test_file)

        # SHA256 of empty string
        expected = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"  # pragma: allowlist secret
        assert checksum == expected

    def test_calculate_checksum_binary_file(self, tmp_path: Path):
        """Test checksum calculation for a binary file."""
        test_file = tmp_path / "binary.bin"
        test_file.write_bytes(b"\x00\x01\x02\x03\x04")

        checksum = calculate_checksum(test_file)

        assert len(checksum) == 64  # SHA256 produces 64 hex characters
        assert all(c in "0123456789abcdef" for c in checksum)


class TestWriteJsonFile:
    """Test suite for write_json_file function."""

    def test_write_json_basic(self, tmp_path: Path):
        """Test writing a basic dictionary to JSON."""
        test_file = tmp_path / "test.json"
        data = {"key": "value", "number": 42}

        write_json_file(data, test_file)

        assert test_file.exists()
        with open(test_file) as f:
            loaded = json.load(f)
        assert loaded == data

    def test_write_json_creates_parent_dirs(self, tmp_path: Path):
        """Test that write_json_file creates parent directories."""
        test_file = tmp_path / "subdir" / "nested" / "test.json"
        data = {"test": "data"}

        write_json_file(data, test_file)

        assert test_file.exists()
        assert test_file.parent.exists()

    def test_write_json_with_dataclass(self, tmp_path: Path):
        """Test writing a dataclass to JSON using CustomJsonEncoder."""
        from dataclasses import dataclass

        @dataclass
        class TestData:
            name: str
            value: int

        test_file = tmp_path / "dataclass.json"
        data = TestData(name="test", value=42)

        write_json_file(data, test_file)

        assert test_file.exists()
        with open(test_file) as f:
            loaded = json.load(f)
        assert loaded == {"name": "test", "value": 42}

    def test_write_json_unicode(self, tmp_path: Path):
        """Test writing JSON with unicode characters."""
        test_file = tmp_path / "unicode.json"
        data = {"text": "Hello 世界 🌍"}

        write_json_file(data, test_file)

        assert test_file.exists()
        with open(test_file, encoding="utf-8") as f:
            loaded = json.load(f)
        assert loaded == data


class TestCleanForCreate:
    """Test suite for clean_for_create function."""

    def test_clean_removes_id(self):
        """Test that clean_for_create removes id field."""
        payload = {"id": 123, "name": "Test", "value": "data"}
        cleaned = clean_for_create(payload)

        assert "id" not in cleaned
        assert cleaned["name"] == "Test"
        assert cleaned["value"] == "data"

    def test_clean_removes_timestamps(self):
        """Test that clean_for_create removes timestamp fields."""
        payload = {
            "id": 123,
            "name": "Test",
            "created_at": "2025-01-01T00:00:00Z",
            "updated_at": "2025-01-02T00:00:00Z",
        }
        cleaned = clean_for_create(payload)

        assert "created_at" not in cleaned
        assert "updated_at" not in cleaned
        assert cleaned["name"] == "Test"

    def test_clean_removes_creator_fields(self):
        """Test that clean_for_create removes creator fields."""
        payload = {
            "id": 123,
            "name": "Test",
            "creator_id": 456,
            "creator": {"id": 456, "name": "User"},
        }
        cleaned = clean_for_create(payload)

        assert "creator_id" not in cleaned
        assert "creator" not in cleaned
        assert cleaned["name"] == "Test"

    def test_clean_preserves_valid_fields(self):
        """Test that clean_for_create preserves valid fields."""
        payload = {
            "id": 123,
            "name": "Test",
            "description": "A test item",
            "collection_id": 1,
            "database_id": 2,
            "dataset_query": {"type": "query"},
        }
        cleaned = clean_for_create(payload)

        assert "id" not in cleaned
        assert cleaned["name"] == "Test"
        assert cleaned["description"] == "A test item"
        assert cleaned["collection_id"] == 1
        assert cleaned["database_id"] == 2
        assert cleaned["dataset_query"] == {"type": "query"}

    def test_clean_empty_payload(self):
        """Test clean_for_create with empty payload."""
        payload = {}
        cleaned = clean_for_create(payload)

        assert cleaned == {}

    def test_clean_all_fields_removed(self):
        """Test clean_for_create when all fields are removed."""
        payload = {
            "id": 123,
            "created_at": "2025-01-01T00:00:00Z",
            "updated_at": "2025-01-02T00:00:00Z",
        }
        cleaned = clean_for_create(payload)

        assert cleaned == {}

    def test_clean_model_sets_type_model(self):
        """Test that clean_for_create sets type='model' for cards with dataset=True."""
        payload = {
            "id": 123,
            "name": "Customer Model",
            "dataset": True,
            "dataset_query": {"type": "query", "database": 1, "query": {"source-table": 10}},
        }
        cleaned = clean_for_create(payload)

        assert cleaned["type"] == "model"
        assert cleaned["dataset"] is True

    def test_clean_question_sets_type_question(self):
        """Test that clean_for_create sets type='question' for cards without type."""
        payload = {
            "id": 123,
            "name": "Revenue Query",
            "dataset": False,
            "dataset_query": {"type": "query", "database": 1, "query": {"source-table": 10}},
        }
        cleaned = clean_for_create(payload)

        assert cleaned["type"] == "question"
        assert cleaned["dataset"] is False

    def test_clean_question_no_dataset_field_defaults_to_question(self):
        """Test that clean_for_create defaults to type='question' when dataset is not set."""
        payload = {
            "id": 123,
            "name": "Simple Query",
            "dataset_query": {"type": "query", "database": 1, "query": {"source-table": 10}},
        }
        cleaned = clean_for_create(payload)

        assert cleaned["type"] == "question"

    def test_clean_preserves_existing_type_for_question(self):
        """Test that clean_for_create preserves existing type for questions."""
        payload = {
            "id": 123,
            "name": "Native Query",
            "type": "question",
            "dataset": False,
            "dataset_query": {"type": "native", "database": 1, "native": {"query": "SELECT 1"}},
        }
        cleaned = clean_for_create(payload)

        assert cleaned["type"] == "question"

    def test_clean_model_overrides_wrong_type(self):
        """Test that clean_for_create overrides type to 'model' when dataset=True."""
        # This handles the case where a model might have been incorrectly marked as question
        payload = {
            "id": 123,
            "name": "Customer Model",
            "type": "question",  # Wrong type for a model
            "dataset": True,  # This is a model
            "dataset_query": {"type": "query", "database": 1, "query": {"source-table": 10}},
        }
        cleaned = clean_for_create(payload)

        # dataset=True should override the type to 'model'
        assert cleaned["type"] == "model"
        assert cleaned["dataset"] is True

    def test_clean_empty_description_set_to_none(self):
        """Test that clean_for_create sanitizes empty-string description to None."""
        payload = {
            "name": "Test Card",
            "description": "",
            "dataset_query": {"type": "query"},
        }
        cleaned = clean_for_create(payload)

        assert cleaned["description"] is None

    def test_clean_valid_description_preserved(self):
        """Test that clean_for_create preserves non-empty description."""
        payload = {
            "name": "Test Card",
            "description": "A valid description",
        }
        cleaned = clean_for_create(payload)

        assert cleaned["description"] == "A valid description"

    def test_clean_none_description_preserved(self):
        """Test that clean_for_create preserves None description."""
        payload = {
            "name": "Test Card",
            "description": None,
        }
        cleaned = clean_for_create(payload)

        assert cleaned["description"] is None

    def test_clean_missing_description_not_added(self):
        """Test that clean_for_create does not add description if not present."""
        payload = {
            "name": "Test Card",
        }
        cleaned = clean_for_create(payload)

        assert "description" not in cleaned

    def test_clean_non_card_payload_unchanged(self):
        """Test that clean_for_create doesn't add type to non-card payloads."""
        # Collection payload - should not have type added
        payload = {
            "id": 123,
            "name": "Test Collection",
            "description": "A collection",
        }
        cleaned = clean_for_create(payload)

        assert "type" not in cleaned
        assert cleaned["name"] == "Test Collection"

    def test_clean_metric_type_preserved(self):
        """Test that clean_for_create preserves metric type."""
        payload = {
            "id": 123,
            "name": "Revenue Metric",
            "type": "metric",
            "dataset": False,
            "dataset_query": {"type": "query", "database": 1, "query": {"source-table": 10}},
        }
        cleaned = clean_for_create(payload)

        assert cleaned["type"] == "metric"


class TestCustomJsonEncoder:
    """Test suite for CustomJsonEncoder class."""

    def test_encode_dataclass(self):
        """Test encoding a dataclass."""
        from dataclasses import dataclass

        @dataclass
        class Person:
            name: str
            age: int

        person = Person(name="Alice", age=30)
        result = json.dumps(person, cls=CustomJsonEncoder)

        assert json.loads(result) == {"name": "Alice", "age": 30}

    def test_encode_nested_dataclass(self):
        """Test encoding nested dataclasses."""
        from dataclasses import dataclass

        @dataclass
        class Address:
            city: str
            country: str

        @dataclass
        class Person:
            name: str
            address: Address

        person = Person(name="Alice", address=Address(city="NYC", country="USA"))
        result = json.dumps(person, cls=CustomJsonEncoder)

        expected = {"name": "Alice", "address": {"city": "NYC", "country": "USA"}}
        assert json.loads(result) == expected

    def test_encode_regular_dict(self):
        """Test encoding a regular dictionary."""
        data = {"key": "value", "number": 42}
        result = json.dumps(data, cls=CustomJsonEncoder)

        assert json.loads(result) == data


class TestSetupLogging:
    """Test suite for setup_logging function."""

    def teardown_method(self):
        """Clean up logger handlers after each test."""
        # Clean up both the specific logger and root logger
        logger = logging.getLogger("metabase_migration")
        logger.handlers.clear()
        root_logger = logging.getLogger()
        root_logger.handlers.clear()

    def test_setup_logging_info_level(self):
        """Test setting up logging with INFO level."""
        logger = setup_logging("INFO")

        assert logger.level == logging.INFO
        # Handlers are on the root logger, not the specific logger
        root_logger = logging.getLogger()
        assert len(root_logger.handlers) > 0

    def test_setup_logging_debug_level(self):
        """Test setting up logging with DEBUG level."""
        logger = setup_logging("DEBUG")

        assert logger.level == logging.DEBUG

    def test_setup_logging_warning_level(self):
        """Test setting up logging with WARNING level."""
        logger = setup_logging("WARNING")

        assert logger.level == logging.WARNING

    def test_setup_logging_error_level(self):
        """Test setting up logging with ERROR level."""
        logger = setup_logging("ERROR")

        assert logger.level == logging.ERROR


class TestToolVersion:
    """Test suite for TOOL_VERSION constant."""

    def test_tool_version_exists(self):
        """Test that TOOL_VERSION is defined."""
        assert TOOL_VERSION is not None

    def test_tool_version_format(self):
        """Test that TOOL_VERSION follows semantic versioning."""
        parts = TOOL_VERSION.split(".")
        assert len(parts) == 3
        assert all(part.isdigit() for part in parts)

    def test_tool_version_matches_package(self):
        """Test that TOOL_VERSION matches package version."""
        from lib import __version__

        assert TOOL_VERSION == __version__


class TestCleanDashboardForUpdate:
    """Test suite for clean_dashboard_for_update function."""

    def test_clean_dashboard_removes_dashcards(self):
        """Test that clean_dashboard_for_update removes dashcards field."""
        payload = {
            "id": 123,
            "name": "Test Dashboard",
            "dashcards": [{"id": 1, "card_id": 100}],
        }
        cleaned = clean_dashboard_for_update(payload)

        assert "dashcards" not in cleaned
        assert cleaned["name"] == "Test Dashboard"

    def test_clean_dashboard_removes_tabs(self):
        """Test that clean_dashboard_for_update removes tabs field."""
        payload = {
            "id": 123,
            "name": "Test Dashboard",
            "tabs": [{"id": 1, "name": "Tab 1"}],
        }
        cleaned = clean_dashboard_for_update(payload)

        assert "tabs" not in cleaned
        assert cleaned["name"] == "Test Dashboard"

    def test_clean_dashboard_removes_both_dashcards_and_tabs(self):
        """Test that clean_dashboard_for_update removes both dashcards and tabs."""
        payload = {
            "id": 123,
            "name": "Test Dashboard",
            "dashcards": [{"id": 1}],
            "tabs": [{"id": 1}],
        }
        cleaned = clean_dashboard_for_update(payload)

        assert "dashcards" not in cleaned
        assert "tabs" not in cleaned
        assert "id" not in cleaned  # Also removed by clean_for_create
        assert cleaned["name"] == "Test Dashboard"

    def test_clean_dashboard_removes_standard_fields(self):
        """Test that clean_dashboard_for_update also removes standard immutable fields."""
        payload = {
            "id": 123,
            "name": "Test Dashboard",
            "created_at": "2025-01-01T00:00:00Z",
            "creator_id": 1,
        }
        cleaned = clean_dashboard_for_update(payload)

        assert "id" not in cleaned
        assert "created_at" not in cleaned
        assert "creator_id" not in cleaned
        assert cleaned["name"] == "Test Dashboard"

    def test_clean_dashboard_empty_description_set_to_none(self):
        """Test that clean_dashboard_for_update sanitizes empty-string description to None."""
        payload = {
            "name": "Test Dashboard",
            "description": "",
            "dashcards": [{"id": 1}],
        }
        cleaned = clean_dashboard_for_update(payload)

        assert cleaned["description"] is None
        assert "dashcards" not in cleaned

    def test_clean_dashboard_valid_description_preserved(self):
        """Test that clean_dashboard_for_update preserves non-empty description."""
        payload = {
            "name": "Test Dashboard",
            "description": "Dashboard description",
        }
        cleaned = clean_dashboard_for_update(payload)

        assert cleaned["description"] == "Dashboard description"


class TestCleanForCreateTableId:
    """Test suite for clean_for_create handling of table_id."""

    def test_clean_sets_table_id_to_null(self):
        """Test that clean_for_create sets table_id to null."""
        payload = {
            "name": "Test Card",
            "table_id": 123,
            "dataset_query": {},
        }
        cleaned = clean_for_create(payload)

        assert cleaned["table_id"] is None
        assert cleaned["name"] == "Test Card"

    def test_clean_without_table_id(self):
        """Test that clean_for_create works without table_id field."""
        payload = {
            "name": "Test Card",
            "dataset_query": {},
        }
        cleaned = clean_for_create(payload)

        assert "table_id" not in cleaned
        assert cleaned["name"] == "Test Card"


class TestCleanForCreateSourceCardId:
    """Test suite for clean_for_create handling of source_card_id."""

    def test_clean_sets_source_card_id_to_null(self):
        """Test that clean_for_create sets source_card_id to null."""
        payload = {
            "name": "Test Card",
            "source_card_id": 456,
            "dataset_query": {},
        }
        cleaned = clean_for_create(payload)

        assert cleaned["source_card_id"] is None
        assert cleaned["name"] == "Test Card"

    def test_clean_preserves_absent_source_card_id(self):
        """Test that clean_for_create works without source_card_id field."""
        payload = {
            "name": "Test Card",
            "dataset_query": {},
        }
        cleaned = clean_for_create(payload)

        assert "source_card_id" not in cleaned

    def test_clean_sets_null_source_card_id_to_null(self):
        """Test that clean_for_create keeps source_card_id as None when already None."""
        payload = {
            "name": "Test Card",
            "source_card_id": None,
            "dataset_query": {},
        }
        cleaned = clean_for_create(payload)

        assert cleaned["source_card_id"] is None


class TestCleanForCreateDashboardFields:
    """Test suite for clean_for_create stripping dashboard reference fields."""

    def test_clean_removes_dashboard_id(self):
        """Test that dashboard_id is stripped (prevents collection_id mismatch errors)."""
        payload = {
            "name": "Test Card",
            "collection_id": 730,
            "dashboard_id": 45,
            "dataset_query": {},
        }
        cleaned = clean_for_create(payload)

        assert "dashboard_id" not in cleaned
        assert cleaned["collection_id"] == 730

    def test_clean_removes_dashboard_object(self):
        """Test that nested dashboard object is stripped."""
        payload = {
            "name": "Test Card",
            "dashboard": {"name": "My Dashboard", "id": 45, "moderation_status": None},
            "dataset_query": {},
        }
        cleaned = clean_for_create(payload)

        assert "dashboard" not in cleaned

    def test_clean_removes_dashboard_count(self):
        """Test that dashboard_count is stripped."""
        payload = {
            "name": "Test Card",
            "dashboard_count": 3,
            "dataset_query": {},
        }
        cleaned = clean_for_create(payload)

        assert "dashboard_count" not in cleaned


class TestCleanForCreateServerComputedFields:
    """Test suite for clean_for_create stripping server-computed fields."""

    def test_clean_removes_permission_flags(self):
        """Test that permission/capability flags are stripped."""
        payload = {
            "name": "Test Card",
            "can_delete": False,
            "can_manage_db": True,
            "can_restore": False,
            "can_run_adhoc_query": True,
            "dataset_query": {},
        }
        cleaned = clean_for_create(payload)

        assert "can_delete" not in cleaned
        assert "can_manage_db" not in cleaned
        assert "can_restore" not in cleaned
        assert "can_run_adhoc_query" not in cleaned

    def test_clean_removes_stats_fields(self):
        """Test that server-computed statistics are stripped."""
        payload = {
            "name": "Test Card",
            "average_query_time": 3009.68,
            "cache_invalidated_at": "2025-08-06T14:06:27Z",
            "last_query_start": "2025-10-03T09:05:28Z",
            "last_used_at": "2025-10-03T09:05:29Z",
            "last-edit-info": {"id": 256, "email": "bot@example.com"},
            "view_count": 1881,
            "dataset_query": {},
        }
        cleaned = clean_for_create(payload)

        assert "average_query_time" not in cleaned
        assert "cache_invalidated_at" not in cleaned
        assert "last_query_start" not in cleaned
        assert "last_used_at" not in cleaned
        assert "last-edit-info" not in cleaned
        assert "view_count" not in cleaned

    def test_clean_removes_server_internal_metadata(self):
        """Test that server-internal metadata fields are stripped."""
        payload = {
            "name": "Test Card",
            "archived_directly": False,
            "card_schema": 23,
            "collection": {"id": 166, "name": "Test Collection"},
            "dependency_analysis_version": 3,
            "document_id": None,
            "entity_id": None,
            "initially_published_at": None,
            "is_remote_synced": False,
            "legacy_query": '{"type":"native"}',
            "metabase_version": None,
            "parameter_usage_count": 0,
            "query_type": "native",
            "dataset_query": {},
        }
        cleaned = clean_for_create(payload)

        for field in [
            "archived_directly",
            "card_schema",
            "collection",
            "dependency_analysis_version",
            "document_id",
            "entity_id",
            "initially_published_at",
            "is_remote_synced",
            "legacy_query",
            "metabase_version",
            "parameter_usage_count",
            "query_type",
        ]:
            assert field not in cleaned, f"Expected '{field}' to be stripped"

    def test_clean_preserves_writable_fields(self):
        """Test that writable fields survive cleaning with a realistic payload."""
        payload = {
            # Writable fields that must be preserved
            "name": "[Archive] - Réseaux : liste magasins",
            "description": None,
            "collection_id": 730,
            "archived": False,
            "type": "question",
            "database_id": 2,
            "dataset_query": {"lib/type": "mbql/query", "database": 2},
            "display": "table",
            "visualization_settings": {"table.pivot_column": "x"},
            "parameters": [{"id": "abc", "type": "category"}],
            "parameter_mappings": None,
            "cache_ttl": None,
            "enable_embedding": False,
            "embedding_params": None,
            "collection_position": None,
            "collection_preview": True,
            "result_metadata": [{"name": "col1"}],
            # Read-only fields that must be stripped
            "id": 622,
            "dashboard_id": 45,
            "dashboard": {"name": "TdB Réseaux", "id": 45},
            "dashboard_count": 1,
            "view_count": 1881,
            "can_delete": False,
            "entity_id": None,
            "legacy_query": '{"type":"native"}',
        }
        cleaned = clean_for_create(payload)

        # Writable fields preserved
        assert cleaned["name"] == "[Archive] - Réseaux : liste magasins"
        assert cleaned["collection_id"] == 730
        assert cleaned["database_id"] == 2
        assert cleaned["display"] == "table"
        assert cleaned["visualization_settings"] == {"table.pivot_column": "x"}
        assert cleaned["result_metadata"] == [{"name": "col1"}]
        assert cleaned["type"] == "question"

        # Read-only fields stripped
        assert "id" not in cleaned
        assert "dashboard_id" not in cleaned
        assert "dashboard" not in cleaned
        assert "dashboard_count" not in cleaned
        assert "view_count" not in cleaned
        assert "can_delete" not in cleaned
        assert "entity_id" not in cleaned
        assert "legacy_query" not in cleaned


class TestSetupLoggingAdvanced:
    """Additional test cases for setup_logging function."""

    def teardown_method(self):
        """Clean up logger handlers after each test."""
        logger = logging.getLogger("metabase_migration")
        logger.handlers.clear()
        root_logger = logging.getLogger()
        root_logger.handlers.clear()

    def test_setup_logging_with_explicit_level_parameter(self):
        """Test setting up logging with explicit level parameter."""
        logger = setup_logging("my_module", level="DEBUG")

        assert logger.name == "my_module"
        assert logger.level == logging.DEBUG

    def test_setup_logging_with_module_name(self):
        """Test setting up logging with module name as first argument."""
        logger = setup_logging("my_custom_logger")

        assert logger.name == "my_custom_logger"
        # Default level should be INFO
        assert logger.level == logging.INFO

    def test_setup_logging_level_as_first_arg_uses_default_name(self):
        """Test that log level as first arg uses default logger name."""
        logger = setup_logging("WARNING")

        assert logger.name == "metabase_migration"
        assert logger.level == logging.WARNING


class TestCustomJsonEncoderFallback:
    """Test suite for CustomJsonEncoder fallback behavior."""

    def test_encode_non_serializable_raises_error(self):
        """Test that non-serializable objects raise TypeError."""
        import pytest

        class NonSerializable:
            pass

        obj = NonSerializable()

        with pytest.raises(TypeError):
            json.dumps(obj, cls=CustomJsonEncoder)

    def test_encode_datetime_raises_error(self):
        """Test that datetime objects raise TypeError (not a dataclass)."""
        from datetime import datetime

        import pytest

        now = datetime.now()

        with pytest.raises(TypeError):
            json.dumps(now, cls=CustomJsonEncoder)
