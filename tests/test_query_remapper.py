"""Tests for QueryRemapper unmapped-ID handling (Phase 2 Tier 1).

Verifies that unmapped IDs raise the correct MappingError subclass
instead of silently leaking source IDs to the target instance.
Force mode (--unmapped-ids=force) must preserve the original ID without raising.
"""

import pytest

from lib.constants import (
    CARD_REF_PREFIX,
    JOINS_KEY,
    SOURCE_TABLE_KEY,
    V57_BASE_TYPE,
    V57_LIB_UUID,
    V57_SOURCE_CARD_KEY,
)
from lib.errors import CardMappingError, FieldMappingError, TableMappingError
from lib.models import DatabaseMap, Manifest, ManifestMeta
from lib.remapping.id_mapper import IDMapper
from lib.remapping.query_remapper import QueryRemapper

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_id_mapper(
    *,
    db_mapping: dict[int, int] | None = None,
    table_mapping: dict[tuple[int, int], int] | None = None,
    field_mapping: dict[tuple[int, int], int] | None = None,
    card_mapping: dict[int, int] | None = None,
) -> IDMapper:
    """Build an IDMapper pre-loaded with the given mappings.

    Args:
        db_mapping: source_db_id -> target_db_id
        table_mapping: (source_db_id, source_table_id) -> target_table_id
        field_mapping: (source_db_id, source_field_id) -> target_field_id
        card_mapping: source_card_id -> target_card_id
    """
    db_mapping = db_mapping or {}

    manifest = Manifest(
        meta=ManifestMeta(
            source_url="https://source.example.com",
            export_timestamp="2025-01-01T00:00:00",
            tool_version="1.0.0",
            cli_args={},
        ),
        databases={src: f"DB{src}" for src in db_mapping},
    )
    db_map = DatabaseMap(by_id={str(k): v for k, v in db_mapping.items()})
    mapper = IDMapper(manifest, db_map)

    # Inject table/field/card mappings directly into internal dicts
    if table_mapping:
        mapper._table_map.update(table_mapping)
    if field_mapping:
        mapper._field_map.update(field_mapping)
    if card_mapping:
        for src, tgt in card_mapping.items():
            mapper.set_card_mapping(src, tgt)

    return mapper


def _make_remapper(
    mapper: IDMapper,
    mode: str = "skip",
) -> QueryRemapper:
    """Build a QueryRemapper in the given unmapped_ids_mode."""
    return QueryRemapper(mapper, unmapped_ids_mode=mode)  # type: ignore[arg-type]


# ===========================================================================
# 1. FieldMappingError — unmapped field IDs
# ===========================================================================


class TestFieldUnmappedRaises:
    """Leak 1.1 & 1.2 — _remap_list field references."""

    def test_remap_list_v57_field_unmapped_raises(self) -> None:
        """Leak 1.1: v57 field ref ["field", {metadata}, field_id] must raise."""
        mapper = _make_id_mapper(db_mapping={1: 10})
        # No field mapping for (1, 999) — field 999 is unmapped
        remapper = _make_remapper(mapper)

        v57_field_ref = [
            "field",
            {V57_LIB_UUID: "abc-123", V57_BASE_TYPE: "type/Integer"},
            999,
        ]

        with pytest.raises(FieldMappingError) as exc_info:
            remapper._remap_list(v57_field_ref, source_db_id=1)

        assert exc_info.value.source_id == 999
        assert "v57" in (exc_info.value.location or "")

    def test_remap_list_v56_field_unmapped_raises(self) -> None:
        """Leak 1.2: v56 field ref ["field", field_id, opts] must raise."""
        mapper = _make_id_mapper(db_mapping={1: 10})
        # No field mapping for (1, 888)
        remapper = _make_remapper(mapper)

        v56_field_ref = ["field", 888, {"temporal-unit": "month"}]

        with pytest.raises(FieldMappingError) as exc_info:
            remapper._remap_list(v56_field_ref, source_db_id=1)

        assert exc_info.value.source_id == 888
        assert "v56" in (exc_info.value.location or "")


# ===========================================================================
# 2. TableMappingError — unmapped table IDs
# ===========================================================================


class TestTableUnmappedRaises:
    """Leak 2.2 & 2.3 — _remap_source_table / _remap_joins table references."""

    def test_remap_source_table_unmapped_raises(self) -> None:
        """Leak 2.2: integer source-table with no mapping must raise."""
        mapper = _make_id_mapper(db_mapping={1: 10})
        # No table mapping for (1, 555)
        remapper = _make_remapper(mapper)

        query: dict = {SOURCE_TABLE_KEY: 555}

        with pytest.raises(TableMappingError) as exc_info:
            remapper._remap_source_table(query, source_db_id=1)

        assert exc_info.value.source_id == 555
        assert "source-table" in (exc_info.value.location or "")

    def test_remap_joins_table_unmapped_raises(self) -> None:
        """Leak 2.3: join clause with unmapped integer source-table must raise."""
        mapper = _make_id_mapper(db_mapping={1: 10})
        # No table mapping for (1, 777)
        remapper = _make_remapper(mapper)

        query: dict = {
            JOINS_KEY: [
                {
                    SOURCE_TABLE_KEY: 777,
                    "condition": ["=", 1, 1],
                }
            ]
        }

        with pytest.raises(TableMappingError) as exc_info:
            remapper._remap_joins(query, source_db_id=1)

        assert exc_info.value.source_id == 777
        assert "join" in (exc_info.value.location or "").lower()


# ===========================================================================
# 3. CardMappingError — unmapped card IDs
# ===========================================================================


class TestCardUnmappedRaises:
    """Leaks 3.1–3.7 — various card reference sites."""

    def test_remap_source_table_v57_card_unmapped_raises(self) -> None:
        """Leak 3.1: v57 source-card integer with no mapping must raise."""
        mapper = _make_id_mapper(db_mapping={1: 10})
        # No card mapping for 42
        remapper = _make_remapper(mapper)

        query: dict = {V57_SOURCE_CARD_KEY: 42}

        with pytest.raises(CardMappingError) as exc_info:
            remapper._remap_source_table(query, source_db_id=1)

        assert exc_info.value.source_id == 42
        assert "v57" in (exc_info.value.location or "").lower()

    def test_remap_card_reference_v56_unmapped_raises(self) -> None:
        """Leak 3.2: v56 card__123 reference with no mapping must raise."""
        mapper = _make_id_mapper(db_mapping={1: 10})
        # No card mapping for 123
        remapper = _make_remapper(mapper)

        container: dict = {SOURCE_TABLE_KEY: f"{CARD_REF_PREFIX}123"}

        with pytest.raises(CardMappingError) as exc_info:
            remapper._remap_card_reference(container, SOURCE_TABLE_KEY, f"{CARD_REF_PREFIX}123")

        assert exc_info.value.source_id == 123
        assert "v56" in (exc_info.value.location or "").lower()

    def test_remap_joins_v57_card_unmapped_raises(self) -> None:
        """Leak 3.3: v57 join source-card with no mapping must raise."""
        mapper = _make_id_mapper(db_mapping={1: 10})
        # No card mapping for 55
        remapper = _make_remapper(mapper)

        query: dict = {
            JOINS_KEY: [
                {
                    V57_SOURCE_CARD_KEY: 55,
                    "condition": ["=", 1, 1],
                }
            ]
        }

        with pytest.raises(CardMappingError) as exc_info:
            remapper._remap_joins(query, source_db_id=1)

        assert exc_info.value.source_id == 55
        assert "join" in (exc_info.value.location or "").lower()

    def test_remap_list_metric_unmapped_raises(self) -> None:
        """Leak 3.4: metric reference ["metric", {meta}, card_id] must raise."""
        mapper = _make_id_mapper(db_mapping={1: 10})
        # No card mapping for 77
        remapper = _make_remapper(mapper)

        metric_ref = ["metric", {V57_LIB_UUID: "m-uuid"}, 77]

        with pytest.raises(CardMappingError) as exc_info:
            remapper._remap_list(metric_ref, source_db_id=1)

        assert exc_info.value.source_id == 77
        assert "metric" in (exc_info.value.location or "").lower()

    def test_remap_sql_card_ref_unmapped_raises(self) -> None:
        """Leak 3.5: native SQL {{#123-model}} with no mapping must raise."""
        mapper = _make_id_mapper(db_mapping={1: 10})
        # No card mapping for 123
        remapper = _make_remapper(mapper)

        sql = "SELECT * FROM {{#123-my-model}}"

        with pytest.raises(CardMappingError) as exc_info:
            remapper._remap_sql_card_references(sql)

        assert exc_info.value.source_id == 123
        assert "native SQL" in (exc_info.value.location or "")

    def test_remap_template_tags_card_unmapped_raises(self) -> None:
        """Leak 3.6: template-tag with type=card and unmapped card-id must raise."""
        mapper = _make_id_mapper(db_mapping={1: 10})
        # No card mapping for 99
        remapper = _make_remapper(mapper)

        tags = {
            "99-some-model": {
                "type": "card",
                "card-id": 99,
                "name": "99-some-model",
            }
        }

        with pytest.raises(CardMappingError) as exc_info:
            remapper._remap_template_tags(tags, source_db_id=1)

        assert exc_info.value.source_id == 99
        assert "template-tag" in (exc_info.value.location or "").lower()

    def test_remap_dashcard_param_card_unmapped_raises(self) -> None:
        """Leak 3.7: dashcard parameter_mapping card_id with no mapping must raise."""
        mapper = _make_id_mapper(db_mapping={1: 10})
        # No card mapping for 200
        remapper = _make_remapper(mapper)

        mappings = [{"card_id": 200, "target": ["dimension", ["field", 1, None]]}]

        with pytest.raises(CardMappingError) as exc_info:
            remapper.remap_dashcard_parameter_mappings(mappings, source_db_id=1)

        assert exc_info.value.source_id == 200
        assert "parameter_mapping" in (exc_info.value.location or "").lower()


# ===========================================================================
# 4. Force mode — preserves original ID without raising
# ===========================================================================


class TestForceModeKeeps:
    """Force mode must keep the source ID and NOT raise."""

    def test_remap_list_v57_field_force_mode_keeps(self) -> None:
        """Leak 1.1 in force mode: source field ID preserved, no exception."""
        mapper = _make_id_mapper(db_mapping={1: 10})
        # No field mapping for (1, 999)
        remapper = _make_remapper(mapper, mode="force")

        v57_field_ref = [
            "field",
            {V57_LIB_UUID: "abc-123", V57_BASE_TYPE: "type/Integer"},
            999,
        ]

        result = remapper._remap_list(v57_field_ref, source_db_id=1)
        # Original field ID is preserved (no change)
        assert result[2] == 999

    def test_remap_source_table_force_mode_keeps(self) -> None:
        """Leak 2.2 in force mode: source table ID preserved, no exception."""
        mapper = _make_id_mapper(db_mapping={1: 10})
        # No table mapping for (1, 555)
        remapper = _make_remapper(mapper, mode="force")

        query: dict = {SOURCE_TABLE_KEY: 555}
        remapper._remap_source_table(query, source_db_id=1)

        # Original table ID still present
        assert query[SOURCE_TABLE_KEY] == 555

    def test_remap_card_reference_force_mode_keeps(self) -> None:
        """Leak 3.2 in force mode: source card ref preserved, no exception."""
        mapper = _make_id_mapper(db_mapping={1: 10})
        # No card mapping for 123
        remapper = _make_remapper(mapper, mode="force")

        container: dict = {SOURCE_TABLE_KEY: f"{CARD_REF_PREFIX}123"}
        remapper._remap_card_reference(container, SOURCE_TABLE_KEY, f"{CARD_REF_PREFIX}123")

        # Original card reference preserved
        assert container[SOURCE_TABLE_KEY] == f"{CARD_REF_PREFIX}123"
