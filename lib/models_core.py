"""Defines the data classes for Metabase objects and the migration manifest.

Using typed dataclasses provides clarity and reduces errors.
"""

from __future__ import annotations

import dataclasses
from typing import Any, Literal

# --- Core Metabase Object Models ---


@dataclasses.dataclass
class Collection:
    """Represents a Metabase collection."""

    id: int
    name: str
    slug: str
    description: str | None = None
    parent_id: int | None = None
    personal_owner_id: int | None = None
    path: str = ""  # Filesystem path, populated during export
    type: str | None = None  # Metabase collection type (e.g. "trash" for the Trash collection)


@dataclasses.dataclass
class Card:
    """Represents a Metabase card (question/model)."""

    id: int
    name: str
    collection_id: int | None = None
    database_id: int | None = None
    file_path: str = ""
    checksum: str = ""
    archived: bool = False
    dataset_query: dict[str, Any] | None = None
    dataset: bool = False  # True if this card is a model (dataset)


@dataclasses.dataclass
class Dashboard:
    """Represents a Metabase dashboard."""

    id: int
    name: str
    collection_id: int | None = None
    ordered_cards: list[int] = dataclasses.field(default_factory=list)
    file_path: str = ""
    checksum: str = ""
    archived: bool = False


@dataclasses.dataclass
class PermissionGroup:
    """Represents a Metabase permission group."""

    id: int
    name: str
    member_count: int = 0


# --- Manifest Models ---


@dataclasses.dataclass
class ManifestMeta:
    """Metadata about the export process."""

    source_url: str
    export_timestamp: str
    tool_version: str
    cli_args: dict[str, Any]
    metabase_version: str | None = None  # Metabase version used during export (e.g., "v56")


@dataclasses.dataclass
class Manifest:
    """The root object for the manifest.json file."""

    meta: ManifestMeta
    databases: dict[int, str] = dataclasses.field(default_factory=dict)
    collections: list[Collection] = dataclasses.field(default_factory=list)
    cards: list[Card] = dataclasses.field(default_factory=list)
    dashboards: list[Dashboard] = dataclasses.field(default_factory=list)
    permission_groups: list[PermissionGroup] = dataclasses.field(default_factory=list)
    permissions_graph: dict[str, Any] = dataclasses.field(default_factory=dict)
    collection_permissions_graph: dict[str, Any] = dataclasses.field(default_factory=dict)
    # Database metadata: db_id -> {tables: [{id, name, fields: [{id, name}, ...]}, ...]}
    database_metadata: dict[int, dict[str, Any]] = dataclasses.field(default_factory=dict)


# --- Import-specific Models ---


@dataclasses.dataclass
class DatabaseMap:
    """Represents the database mapping file."""

    by_id: dict[str, int] = dataclasses.field(default_factory=dict)
    by_name: dict[str, int] = dataclasses.field(default_factory=dict)
    dataset_suffix_replacement: dict[str, str] = dataclasses.field(default_factory=dict)


@dataclasses.dataclass
class UnmappedDatabase:
    """Represents a source database that could not be mapped to a target."""

    source_db_id: int
    source_db_name: str
    card_ids: set[int] = dataclasses.field(default_factory=set)


@dataclasses.dataclass
class ImportAction:
    """Represents a single planned action for an import dry-run."""

    entity_type: Literal["collection", "card", "dashboard"]
    action: Literal["create", "update", "skip", "rename"]
    source_id: int
    name: str
    target_path: str


@dataclasses.dataclass
class ImportPlan:
    """Represents the full plan for an import operation."""

    actions: list[ImportAction] = dataclasses.field(default_factory=list)
    unmapped_databases: list[UnmappedDatabase] = dataclasses.field(default_factory=list)


@dataclasses.dataclass
class ImportReportItem:
    """Represents the result of a single item import."""

    entity_type: Literal["collection", "card", "dashboard"]
    status: Literal["created", "updated", "skipped", "failed", "success", "error"]
    source_id: int
    target_id: int | None
    name: str
    reason: str | None = None
    error_message: str | None = None  # Alias for reason, kept for backward compatibility

    def __post_init__(self) -> None:
        """Sync error_message and reason fields."""
        # If error_message is provided but not reason, use error_message
        if self.error_message is not None and self.reason is None:
            self.reason = self.error_message
        # If reason is provided but not error_message, sync error_message
        elif self.reason is not None and self.error_message is None:
            self.error_message = self.reason


@dataclasses.dataclass
class ImportReport:
    """Summarizes the results of an import operation."""

    summary: dict[str, dict[str, int]] = dataclasses.field(
        default_factory=lambda: {
            "collections": {"created": 0, "updated": 0, "skipped": 0, "failed": 0},
            "cards": {"created": 0, "updated": 0, "skipped": 0, "failed": 0},
            "dashboards": {"created": 0, "updated": 0, "skipped": 0, "failed": 0},
        }
    )
    results: list[ImportReportItem] = dataclasses.field(default_factory=list)
    items: list[ImportReportItem] = dataclasses.field(default_factory=list)

    def __post_init__(self) -> None:
        """Sync items and results fields for backward compatibility."""
        # If items is provided but results is empty, use items for results
        if self.items and not self.results:
            self.results = self.items
        # If results is provided but items is empty, use results for items
        elif self.results and not self.items:
            self.items = self.results
        # If both are empty, make them point to the same list
        elif not self.items and not self.results:
            shared_list: list[ImportReportItem] = []
            object.__setattr__(self, "items", shared_list)
            object.__setattr__(self, "results", shared_list)

    def add(self, item: ImportReportItem) -> None:
        """Adds an item to the report and updates the summary."""
        self.results.append(item)
        # Keep items in sync
        if self.items is not self.results:
            self.items.append(item)
        entity_key = f"{item.entity_type}s"
        if entity_key in self.summary:
            self.summary[entity_key][item.status] += 1


# --- Unmapped ID Tracking ---


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

        Returns a dict with:
        - ``by_type``: per-type grouping with count and items
        - ``action_summary``: entities_skipped, fields_stripped, total_unmapped_ids
        """
        if not self.events:
            return {}

        by_type: dict[str, list[UnmappedIDEvent]] = {}
        for event in self.events:
            by_type.setdefault(event.id_type, []).append(event)

        result_by_type: dict[str, Any] = {}
        for id_type, events in by_type.items():
            # Group by (source_id, source_database_id)
            grouped: dict[tuple[int, int | None], list[UnmappedIDEvent]] = {}
            for e in events:
                key = (e.source_id, e.source_database_id)
                grouped.setdefault(key, []).append(e)

            items: list[dict[str, Any]] = []
            for (src_id, src_db_id), group_events in grouped.items():
                entry: dict[str, Any] = {
                    "source_id": src_id,
                    "source_database_id": src_db_id,
                    "source_context": group_events[0].source_context,
                    "affected_entities": [
                        {
                            "entity_type": e.entity_type,
                            "source_id": e.entity_source_id,
                            "name": e.entity_name,
                            "location": e.location,
                            "action_taken": e.action,
                        }
                        for e in group_events
                    ],
                }
                items.append(entry)

            result_by_type[id_type] = {
                "count": len(items),
                "items": items,
            }

        return {
            "by_type": result_by_type,
            "action_summary": {
                "entities_skipped": self.skipped_count,
                "fields_stripped": self.stripped_count,
                "total_unmapped_ids": len(
                    {(e.source_id, e.source_database_id, e.id_type) for e in self.events}
                ),
            },
        }

    @property
    def has_events(self) -> bool:
        """Whether any unmapped IDs were recorded."""
        return len(self.events) > 0

    @property
    def skipped_count(self) -> int:
        """Number of entities skipped due to unmapped IDs."""
        return len(
            {(e.entity_type, e.entity_source_id) for e in self.events if e.action == "skipped"}
        )

    @property
    def stripped_count(self) -> int:
        """Number of fields stripped due to unmapped IDs."""
        return len([e for e in self.events if e.action == "stripped"])
