"""Tests for IDMapper source context helper methods.

Phase 4: Verifies that get_source_field_context() and get_source_table_context()
return human-readable context strings from manifest database metadata.
"""

from lib.models import DatabaseMap, Manifest, ManifestMeta
from lib.remapping.id_mapper import IDMapper


def _make_mapper_with_metadata(
    database_metadata: dict | None = None,
) -> IDMapper:
    """Build an IDMapper with source database metadata in the manifest.

    Args:
        database_metadata: db_id -> {tables: [{id, name, fields: [{id, name}, ...]}, ...]}
    """
    manifest = Manifest(
        meta=ManifestMeta(
            source_url="https://source.example.com",
            export_timestamp="2025-01-01T00:00:00",
            tool_version="1.0.0",
            cli_args={},
        ),
        databases={1: "Production DB"},
        database_metadata=database_metadata or {},
    )
    db_map = DatabaseMap(by_id={"1": 10})
    return IDMapper(manifest, db_map)


class TestGetSourceFieldContext:
    """Tests for IDMapper.get_source_field_context()."""

    def test_get_source_field_context(self) -> None:
        """Returns 'table X, column Y' format for a known field."""
        mapper = _make_mapper_with_metadata(
            database_metadata={
                1: {
                    "tables": [
                        {
                            "id": 50,
                            "name": "region_department",
                            "fields": [
                                {"id": 500, "name": "num_dep"},
                                {"id": 501, "name": "name"},
                            ],
                        },
                    ]
                }
            }
        )

        result = mapper.get_source_field_context(source_db_id=1, source_field_id=500)
        assert result == "table 'region_department', column 'num_dep'"

    def test_get_source_field_context_not_found(self) -> None:
        """Returns None for an unknown field ID."""
        mapper = _make_mapper_with_metadata(
            database_metadata={
                1: {
                    "tables": [
                        {
                            "id": 50,
                            "name": "region_department",
                            "fields": [
                                {"id": 500, "name": "num_dep"},
                            ],
                        },
                    ]
                }
            }
        )

        result = mapper.get_source_field_context(source_db_id=1, source_field_id=99999)
        assert result is None

    def test_get_source_field_context_unknown_db(self) -> None:
        """Returns None when the database ID has no metadata."""
        mapper = _make_mapper_with_metadata(database_metadata={})

        result = mapper.get_source_field_context(source_db_id=999, source_field_id=500)
        assert result is None


class TestGetSourceTableContext:
    """Tests for IDMapper.get_source_table_context()."""

    def test_get_source_table_context(self) -> None:
        """Returns 'table X' format for a known table."""
        mapper = _make_mapper_with_metadata(
            database_metadata={
                1: {
                    "tables": [
                        {
                            "id": 50,
                            "name": "region_department",
                            "fields": [],
                        },
                    ]
                }
            }
        )

        result = mapper.get_source_table_context(source_db_id=1, source_table_id=50)
        assert result == "table 'region_department'"

    def test_get_source_table_context_not_found(self) -> None:
        """Returns None for an unknown table ID."""
        mapper = _make_mapper_with_metadata(
            database_metadata={
                1: {
                    "tables": [
                        {"id": 50, "name": "region_department", "fields": []},
                    ]
                }
            }
        )

        result = mapper.get_source_table_context(source_db_id=1, source_table_id=99999)
        assert result is None
