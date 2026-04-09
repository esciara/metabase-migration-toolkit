"""Tests for QueryRemapper unmapped-ID handling.

Phase 2 (Tier 1): Verifies that unmapped IDs raise the correct MappingError subclass
instead of silently leaking source IDs to the target instance.
Force mode (--unmapped-ids=force) must preserve the original ID without raising.

Phase 3 (Tier 2): Verifies that advisory/metadata structures strip unmapped IDs
(set to None or remove the containing structure) and record RemapWarnings.
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


# ===========================================================================
# 5. Tier 2 — Strip advisory IDs (Phase 3)
# ===========================================================================


class TestTier2StripResultMetadata:
    """Leaks 1.3, 1.4, 2.4 — _remap_result_metadata strips unmapped IDs."""

    def test_remap_result_metadata_field_id_stripped(self) -> None:
        """Leak 1.3: unmapped field ID in result_metadata[].id is removed + warning."""
        mapper = _make_id_mapper(db_mapping={1: 10})
        # No field mapping for (1, 500) — unmapped
        remapper = _make_remapper(mapper, mode="skip")

        metadata = [
            {"name": "col1", "id": 500, "base_type": "type/Integer"},
        ]

        result = remapper._remap_result_metadata(metadata, source_db_id=1)

        # The "id" key must be stripped (removed entirely)
        assert "id" not in result[0], "Unmapped field ID should be stripped from result_metadata"
        # A RemapWarning should be recorded
        assert len(remapper._current_warnings) == 1
        w = remapper._current_warnings[0]
        assert w.id_type == "field"
        assert w.source_id == 500
        assert "result_metadata" in w.location

    def test_remap_result_metadata_field_ref_stripped(self) -> None:
        """Leak 1.4: unmapped field ref in result_metadata[].field_ref is removed + warning."""
        mapper = _make_id_mapper(db_mapping={1: 10})
        # No field mapping for (1, 600) — will cause FieldMappingError in remap_field_ids_recursively
        remapper = _make_remapper(mapper, mode="skip")

        metadata = [
            {
                "name": "col1",
                "field_ref": ["field", 600, {"base-type": "type/Text"}],
            },
        ]

        result = remapper._remap_result_metadata(metadata, source_db_id=1)

        # The "field_ref" key must be stripped
        assert (
            "field_ref" not in result[0]
        ), "Unmapped field_ref should be stripped from result_metadata"
        # A RemapWarning should be recorded
        assert len(remapper._current_warnings) >= 1
        w = remapper._current_warnings[0]
        assert w.id_type == "field"
        assert "result_metadata" in w.location

    def test_remap_result_metadata_table_id_stripped(self) -> None:
        """Leak 2.4: unmapped table_id in result_metadata[].table_id is removed + warning."""
        mapper = _make_id_mapper(db_mapping={1: 10})
        # No table mapping for (1, 700) — unmapped
        remapper = _make_remapper(mapper, mode="skip")

        metadata = [
            {"name": "col1", "table_id": 700},
        ]

        result = remapper._remap_result_metadata(metadata, source_db_id=1)

        # The "table_id" key must be stripped
        assert (
            "table_id" not in result[0]
        ), "Unmapped table_id should be stripped from result_metadata"
        # A RemapWarning should be recorded
        assert len(remapper._current_warnings) == 1
        w = remapper._current_warnings[0]
        assert w.id_type == "table"
        assert w.source_id == 700
        assert "result_metadata" in w.location


class TestTier2StripClickBehavior:
    """Leaks 3.8, 4.1 — _remap_click_behavior strips unmapped targetId."""

    def test_remap_click_behavior_question_stripped(self) -> None:
        """Leak 3.8: unmapped card targetId is removed, type set to 'none'."""
        mapper = _make_id_mapper(db_mapping={1: 10})
        # No card mapping for 42
        remapper = _make_remapper(mapper, mode="skip")

        click_behavior = {
            "type": "link",
            "linkType": "question",
            "targetId": 42,
        }

        result = remapper._remap_click_behavior(click_behavior)

        assert "targetId" not in result, "Unmapped card targetId should be stripped"
        assert result["type"] == "none", "Type should be set to 'none' when targetId is stripped"
        assert len(remapper._current_warnings) == 1
        w = remapper._current_warnings[0]
        assert w.id_type == "card"
        assert w.source_id == 42

    def test_remap_click_behavior_dashboard_stripped(self) -> None:
        """Leak 4.1: unmapped dashboard targetId is removed, type set to 'none'."""
        mapper = _make_id_mapper(db_mapping={1: 10})
        # No dashboard mapping for 99
        remapper = _make_remapper(mapper, mode="skip")

        click_behavior = {
            "type": "link",
            "linkType": "dashboard",
            "targetId": 99,
        }

        result = remapper._remap_click_behavior(click_behavior)

        assert "targetId" not in result, "Unmapped dashboard targetId should be stripped"
        assert result["type"] == "none", "Type should be set to 'none' when targetId is stripped"
        assert len(remapper._current_warnings) == 1
        w = remapper._current_warnings[0]
        assert w.id_type == "dashboard"
        assert w.source_id == 99


class TestTier2StripVisualizerRefs:
    """Leaks 3.9, 3.10 — Visualizer sourceId and data source name ref."""

    def test_remap_visualizer_source_id_stripped(self) -> None:
        """Leak 3.9: unmapped card in sourceId 'card:123' is set to None + warning."""
        mapper = _make_id_mapper(db_mapping={1: 10})
        # No card mapping for 123
        remapper = _make_remapper(mapper, mode="skip")

        item = {"sourceId": "card:123", "name": "col1", "originalName": "col1"}

        result = remapper._remap_visualizer_source_id(item)

        assert result["sourceId"] is None, "Unmapped Visualizer sourceId should be set to None"
        assert len(remapper._current_warnings) == 1
        w = remapper._current_warnings[0]
        assert w.id_type == "card"
        assert w.source_id == 123
        assert "sourceId" in w.location or "visualizer" in w.location.lower()

    def test_remap_data_source_name_ref_stripped(self) -> None:
        """Leak 3.10: unmapped card in $_card:123_name returns None + warning."""
        mapper = _make_id_mapper(db_mapping={1: 10})
        # No card mapping for 123
        remapper = _make_remapper(mapper, mode="skip")

        result = remapper._remap_data_source_name_ref("$_card:123_name")

        assert result is None, "Unmapped data source name ref should return None"
        assert len(remapper._current_warnings) == 1
        w = remapper._current_warnings[0]
        assert w.id_type == "card"
        assert w.source_id == 123


class TestRegressionFieldLeak:
    """Regression tests for real-world field leak scenarios."""

    def test_regression_field_100294_dept_filter(self) -> None:
        """Regression: field 100294 in template-tag 'Dept' dimension must not leak through.

        Real-world scenario from import.log: a card has a native SQL query with a
        template-tag 'Dept' of type 'dimension' whose dimension reference contains
        field ID 100294. If that field is unmapped, the remapper must raise
        FieldMappingError (skip mode) rather than silently passing the source ID
        to the target instance.
        """
        mapper = _make_id_mapper(
            db_mapping={3: 30},
            # Field 100294 is deliberately NOT mapped
            field_mapping={
                (3, 100): 200,  # some other field that IS mapped
            },
        )
        remapper = _make_remapper(mapper, mode="skip")

        # Realistic template-tags payload from a native query card
        template_tags = {
            "Dept": {
                "type": "dimension",
                "name": "Dept",
                "id": "abc-def-123",
                "display-name": "Département",
                "dimension": ["field", 100294, {"base-type": "type/Text"}],
                "widget-type": "string/=",
            },
        }

        with pytest.raises(FieldMappingError) as exc_info:
            remapper._remap_template_tags(template_tags, source_db_id=3)

        assert exc_info.value.source_id == 100294
        # The error should indicate it came from a field reference context
        assert exc_info.value.source_type == "field"


class TestTier2StripLinkCardEntity:
    """Leaks 3.11, 4.2 — _remap_link_card_settings strips unmapped entity."""

    def test_remap_link_card_entity_stripped(self) -> None:
        """Leak 3.11: unmapped card entity.id removes the entity dict + warning."""
        mapper = _make_id_mapper(db_mapping={1: 10})
        # No card mapping for 88
        remapper = _make_remapper(mapper, mode="skip")

        link = {
            "entity": {"id": 88, "model": "card", "name": "Some Card"},
        }

        result = remapper._remap_link_card_settings(link)

        assert "entity" not in result, "Unmapped card entity should be removed"
        assert len(remapper._current_warnings) == 1
        w = remapper._current_warnings[0]
        assert w.id_type == "card"
        assert w.source_id == 88

    def test_remap_link_dashboard_entity_stripped(self) -> None:
        """Leak 4.2: unmapped dashboard entity.id removes the entity dict + warning."""
        mapper = _make_id_mapper(db_mapping={1: 10})
        # No dashboard mapping for 77
        remapper = _make_remapper(mapper, mode="skip")

        link = {
            "entity": {"id": 77, "model": "dashboard", "name": "Some Dashboard"},
        }

        result = remapper._remap_link_card_settings(link)

        assert "entity" not in result, "Unmapped dashboard entity should be removed"
        assert len(remapper._current_warnings) == 1
        w = remapper._current_warnings[0]
        assert w.id_type == "dashboard"
        assert w.source_id == 77
