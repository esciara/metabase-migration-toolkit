"""Tests for IDMapper source context helper methods.

Phase 4: Verifies that get_source_field_context() and get_source_table_context()
return human-readable context strings from manifest database metadata.

Phase 5 (schema): Verifies that schema is included in context strings when present,
and gracefully omitted when None (H2/SQLite) or missing (old manifests).

Phase 6 (supplementary fallback): Verifies that register_result_metadata_fields()
populates a fallback cache, and get_source_field_meta() / get_source_field_context()
fall back to it when the field is missing from manifest metadata.
"""

from lib.models import DatabaseMap, Manifest, ManifestMeta
from lib.remapping.id_mapper import IDMapper


def _make_mapper_with_metadata(
    database_metadata: dict | None = None,
) -> IDMapper:
    """Build an IDMapper with source database metadata in the manifest.

    Args:
        database_metadata: db_id -> {tables: [{id, name, schema?, fields: [{id, name}]}]}
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

    def test_field_context_with_schema(self) -> None:
        """Returns 'schema X, table Y, column Z' when schema is present."""
        mapper = _make_mapper_with_metadata(
            database_metadata={
                1: {
                    "tables": [
                        {
                            "id": 50,
                            "name": "region_department",
                            "schema": "public",
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
        assert result == "schema 'public', table 'region_department' (ID: 50), column 'num_dep'"

    def test_field_context_with_null_schema(self) -> None:
        """Returns 'table Y, column Z' when schema is None (H2/SQLite)."""
        mapper = _make_mapper_with_metadata(
            database_metadata={
                1: {
                    "tables": [
                        {
                            "id": 50,
                            "name": "region_department",
                            "schema": None,
                            "fields": [
                                {"id": 500, "name": "num_dep"},
                            ],
                        },
                    ]
                }
            }
        )

        result = mapper.get_source_field_context(source_db_id=1, source_field_id=500)
        assert result == "table 'region_department' (ID: 50), column 'num_dep'"

    def test_field_context_without_schema_key(self) -> None:
        """Returns 'table Y, column Z' when schema key is missing (old manifests)."""
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

        result = mapper.get_source_field_context(source_db_id=1, source_field_id=500)
        assert result == "table 'region_department' (ID: 50), column 'num_dep'"

    def test_get_source_field_context_not_found(self) -> None:
        """Returns None for an unknown field ID."""
        mapper = _make_mapper_with_metadata(
            database_metadata={
                1: {
                    "tables": [
                        {
                            "id": 50,
                            "name": "region_department",
                            "schema": "public",
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

    def test_table_context_with_schema(self) -> None:
        """Returns 'schema X, table Y' when schema is present."""
        mapper = _make_mapper_with_metadata(
            database_metadata={
                1: {
                    "tables": [
                        {
                            "id": 50,
                            "name": "region_department",
                            "schema": "public",
                            "fields": [],
                        },
                    ]
                }
            }
        )

        result = mapper.get_source_table_context(source_db_id=1, source_table_id=50)
        assert result == "schema 'public', table 'region_department'"

    def test_table_context_with_null_schema(self) -> None:
        """Returns 'table Y' when schema is None (H2/SQLite)."""
        mapper = _make_mapper_with_metadata(
            database_metadata={
                1: {
                    "tables": [
                        {
                            "id": 50,
                            "name": "region_department",
                            "schema": None,
                            "fields": [],
                        },
                    ]
                }
            }
        )

        result = mapper.get_source_table_context(source_db_id=1, source_table_id=50)
        assert result == "table 'region_department'"

    def test_table_context_without_schema_key(self) -> None:
        """Returns 'table Y' when schema key is missing (old manifests)."""
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
                        {
                            "id": 50,
                            "name": "region_department",
                            "schema": "public",
                            "fields": [],
                        },
                    ]
                }
            }
        )

        result = mapper.get_source_table_context(source_db_id=1, source_table_id=99999)
        assert result is None


class TestRegisterResultMetadataFields:
    """Tests for IDMapper.register_result_metadata_fields()."""

    def test_populates_supplementary_cache(self) -> None:
        """Registers fields from result_metadata into the supplementary cache."""
        mapper = _make_mapper_with_metadata(
            database_metadata={
                1: {
                    "tables": [
                        {
                            "id": 4632,
                            "name": "global_collective_offer",
                            "schema": "public",
                            "fields": [{"id": 100834, "name": "other_field"}],
                        },
                    ]
                }
            }
        )

        result_metadata = [
            {"id": 100835, "name": "venue_is_virtual", "table_id": 4632},
        ]
        mapper.register_result_metadata_fields(source_db_id=1, result_metadata=result_metadata)

        meta = mapper.get_source_field_meta(source_db_id=1, source_field_id=100835)
        assert meta is not None
        assert meta["field_name"] == "venue_is_virtual"
        assert meta["table_name"] == "global_collective_offer"
        assert meta["table_id"] == 4632
        assert meta["schema"] == "public"
        assert meta["from_supplementary"] is True

    def test_skips_items_missing_required_keys(self) -> None:
        """Items without id, name, or table_id are silently skipped."""
        mapper = _make_mapper_with_metadata(database_metadata={})

        result_metadata = [
            {"name": "no_id", "table_id": 1},  # missing id
            {"id": 10, "table_id": 1},  # missing name
            {"id": 11, "name": "no_table"},  # missing table_id
        ]
        mapper.register_result_metadata_fields(source_db_id=1, result_metadata=result_metadata)

        assert mapper.get_source_field_meta(1, 10) is None
        assert mapper.get_source_field_meta(1, 11) is None

    def test_does_not_overwrite_existing_supplementary(self) -> None:
        """Once a field is registered, subsequent calls don't overwrite it."""
        mapper = _make_mapper_with_metadata(
            database_metadata={
                1: {
                    "tables": [
                        {"id": 50, "name": "first_table", "schema": "public", "fields": []},
                        {"id": 60, "name": "second_table", "schema": "public", "fields": []},
                    ]
                }
            }
        )

        mapper.register_result_metadata_fields(
            source_db_id=1,
            result_metadata=[{"id": 100, "name": "col_a", "table_id": 50}],
        )
        # Second registration with different table_id should be ignored
        mapper.register_result_metadata_fields(
            source_db_id=1,
            result_metadata=[{"id": 100, "name": "col_a_v2", "table_id": 60}],
        )

        meta = mapper.get_source_field_meta(1, 100)
        assert meta is not None
        assert meta["table_name"] == "first_table"

    def test_table_name_fallback_when_table_not_in_manifest(self) -> None:
        """Uses 'table_id=<id>' when the table is not in manifest metadata."""
        mapper = _make_mapper_with_metadata(database_metadata={})

        mapper.register_result_metadata_fields(
            source_db_id=1,
            result_metadata=[{"id": 999, "name": "orphan_col", "table_id": 7777}],
        )

        meta = mapper.get_source_field_meta(1, 999)
        assert meta is not None
        assert meta["table_name"] == "table_id=7777"
        assert meta["schema"] is None


class TestGetSourceFieldMetaFallback:
    """Tests for the supplementary fallback in get_source_field_meta()."""

    def test_manifest_takes_priority_over_supplementary(self) -> None:
        """Manifest metadata is returned even when supplementary cache has the field."""
        mapper = _make_mapper_with_metadata(
            database_metadata={
                1: {
                    "tables": [
                        {
                            "id": 50,
                            "name": "my_table",
                            "schema": "public",
                            "fields": [{"id": 500, "name": "from_manifest"}],
                        },
                    ]
                }
            }
        )
        # Also register same field in supplementary cache
        mapper.register_result_metadata_fields(
            source_db_id=1,
            result_metadata=[{"id": 500, "name": "from_supplementary", "table_id": 50}],
        )

        meta = mapper.get_source_field_meta(1, 500)
        assert meta is not None
        assert meta["field_name"] == "from_manifest"
        assert meta["from_supplementary"] is False

    def test_falls_back_to_supplementary_when_not_in_manifest(self) -> None:
        """Falls back to supplementary when field is missing from manifest."""
        mapper = _make_mapper_with_metadata(
            database_metadata={
                1: {
                    "tables": [
                        {
                            "id": 4632,
                            "name": "my_table",
                            "schema": "public",
                            "fields": [{"id": 100, "name": "existing"}],
                        },
                    ]
                }
            }
        )
        mapper.register_result_metadata_fields(
            source_db_id=1,
            result_metadata=[{"id": 200, "name": "hidden_field", "table_id": 4632}],
        )

        meta = mapper.get_source_field_meta(1, 200)
        assert meta is not None
        assert meta["field_name"] == "hidden_field"
        assert meta["from_supplementary"] is True

    def test_returns_none_when_not_found_anywhere(self) -> None:
        """Returns None when field is in neither manifest nor supplementary."""
        mapper = _make_mapper_with_metadata(database_metadata={})

        meta = mapper.get_source_field_meta(1, 99999)
        assert meta is None


class TestGetSourceFieldContextFallback:
    """Tests for the supplementary fallback in get_source_field_context()."""

    def test_context_from_supplementary_includes_hidden_tag(self) -> None:
        """Context string from supplementary cache includes [hidden/disabled]."""
        mapper = _make_mapper_with_metadata(
            database_metadata={
                1: {
                    "tables": [
                        {
                            "id": 4632,
                            "name": "global_collective_offer",
                            "schema": "public",
                            "fields": [],
                        },
                    ]
                }
            }
        )
        mapper.register_result_metadata_fields(
            source_db_id=1,
            result_metadata=[{"id": 100835, "name": "venue_is_virtual", "table_id": 4632}],
        )

        result = mapper.get_source_field_context(1, 100835)
        assert result is not None
        assert "venue_is_virtual" in result
        assert "global_collective_offer" in result
        assert "[hidden/disabled]" in result

    def test_context_from_manifest_has_no_hidden_tag(self) -> None:
        """Context string from manifest does NOT include [hidden/disabled]."""
        mapper = _make_mapper_with_metadata(
            database_metadata={
                1: {
                    "tables": [
                        {
                            "id": 50,
                            "name": "region_department",
                            "schema": "public",
                            "fields": [{"id": 500, "name": "num_dep"}],
                        },
                    ]
                }
            }
        )

        result = mapper.get_source_field_context(1, 500)
        assert result is not None
        assert "[hidden/disabled]" not in result
        assert "column 'num_dep'" in result

    def test_context_returns_none_when_not_found(self) -> None:
        """Returns None when field is not found anywhere."""
        mapper = _make_mapper_with_metadata(database_metadata={})

        result = mapper.get_source_field_context(1, 99999)
        assert result is None
