"""Import service for orchestrating Metabase content import."""

import datetime
import logging
from pathlib import Path
from typing import Any

from lib.client import MetabaseAPIError, MetabaseClient
from lib.config import ImportConfig
from lib.constants import MetabaseVersion
from lib.errors import MigrationError
from lib.handlers import (
    CardHandler,
    CollectionHandler,
    DashboardHandler,
    ImportContext,
    PermissionsHandler,
)
from lib.models import (
    Card,
    Collection,
    Dashboard,
    DatabaseMap,
    ImportReport,
    Manifest,
    ManifestMeta,
    PermissionGroup,
    UnmappedDatabase,
)
from lib.remapping import IDMapper, QueryRemapper
from lib.utils import read_json_file, write_json_file
from lib.version import validate_version_compatibility

logger = logging.getLogger("metabase_migration")


class ImportService:
    """Orchestrates the import of Metabase content from an export package."""

    def __init__(self, config: ImportConfig) -> None:
        """Initialize the ImportService.

        Args:
            config: The import configuration.
        """
        self.config = config
        self.client = MetabaseClient(
            base_url=config.target_url,
            username=config.target_username,
            password=config.target_password,
            session_token=config.target_session_token,
            personal_token=config.target_personal_token,
        )
        self.export_dir = Path(config.export_dir)
        self.manifest: Manifest | None = None
        self.db_map: DatabaseMap | None = None
        self.report = ImportReport()

        # These will be initialized after loading the manifest
        self._id_mapper: IDMapper | None = None
        self._query_remapper: QueryRemapper | None = None
        self._context: ImportContext | None = None

        # Backward compatibility: expose internal maps directly
        # These are populated after _load_export_package() is called
        self._collection_map: dict[int, int] = {}
        self._card_map: dict[int, int] = {}
        self._target_collections: list[dict[str, Any]] = []

    def _get_manifest(self) -> Manifest:
        """Returns manifest, ensuring it has been loaded."""
        if self.manifest is None:
            raise RuntimeError("Manifest not loaded")
        return self.manifest

    def _get_id_mapper(self) -> IDMapper:
        """Returns ID mapper, ensuring it has been initialized."""
        if self._id_mapper is None:
            raise RuntimeError("ID mapper not initialized")
        return self._id_mapper

    def _get_context(self) -> ImportContext:
        """Returns import context, ensuring it has been initialized."""
        if self._context is None:
            raise RuntimeError("Import context not initialized")
        return self._context

    def run_import(self) -> None:
        """Main entry point to start the import process."""
        logger.info(f"Starting Metabase import to {self.config.target_url}")
        logger.info(f"Loading export package from: {self.export_dir.resolve()}")

        try:
            self._load_export_package()

            if self.config.dry_run:
                self._perform_dry_run()
            else:
                self._perform_import()

        except MetabaseAPIError as e:
            logger.error(f"A Metabase API error occurred: {e}", exc_info=True)
            raise
        except (FileNotFoundError, ValueError) as e:
            logger.error(f"Failed to load export package: {e}", exc_info=True)
            raise
        except Exception as e:
            logger.error(f"An unexpected error occurred: {e}", exc_info=True)
            raise

    def _load_export_package(self) -> None:
        """Loads and validates the manifest and database mapping files."""
        manifest_path = self.export_dir / "manifest.json"
        if not manifest_path.exists():
            raise FileNotFoundError("manifest.json not found in the export directory.")

        manifest_data = read_json_file(manifest_path)
        self.manifest = self._parse_manifest(manifest_data)

        # Validate Metabase version compatibility (strict validation)
        self._validate_metabase_version()

        db_map_path = Path(self.config.db_map_path)
        if not db_map_path.exists():
            raise FileNotFoundError(f"Database mapping file not found at {db_map_path}")

        db_map_data = read_json_file(db_map_path)
        self.db_map = DatabaseMap(
            by_id=db_map_data.get("by_id", {}),
            by_name=db_map_data.get("by_name", {}),
            schema_suffix_replacement=db_map_data.get("schema_suffix_replacement", {}),
            extra_schemas=db_map_data.get("extra_schemas", []),
        )

        # Initialize mapping and context
        self._id_mapper = IDMapper(self.manifest, self.db_map, self.client)

        schema_rename = self._build_schema_rename_map()
        self._query_remapper = QueryRemapper(
            id_mapper=self._id_mapper,
            unmapped_ids_mode=self.config.unmapped_ids,
            schema_rename=schema_rename,
        )

        logger.info("Export package loaded successfully.")

    def _build_schema_rename_map(self) -> dict[str, str] | None:
        """Build schema rename map by scanning manifest database_metadata.

        Uses the schema_suffix_replacement from db_map.json. Collects all distinct
        schema names from the manifest, filters those ending with each source suffix,
        and generates old->new pairs by swapping the suffix.

        Returns:
            A mapping of old schema names to new schema names, or None if no renames.

        Raises:
            MigrationError: If suffix replacement entries are invalid.
        """
        if not self.db_map or not self.db_map.schema_suffix_replacement:
            return None

        if not self.manifest:
            return None

        suffix_replacements = self.db_map.schema_suffix_replacement

        # Validate suffix replacements
        for source_suffix, target_suffix in suffix_replacements.items():
            if not source_suffix or not target_suffix:
                raise MigrationError(
                    f"Invalid schema_suffix_replacement: empty suffix in "
                    f"'{source_suffix}' -> '{target_suffix}'"
                )
            if source_suffix == target_suffix:
                raise MigrationError(
                    f"Invalid schema_suffix_replacement: source and target "
                    f"suffix are identical: '{source_suffix}'"
                )

        # Collect all distinct schemas from manifest metadata
        all_schemas: set[str] = set()
        for db_metadata in self.manifest.database_metadata.values():
            for table in db_metadata.get("tables", []):
                schema = table.get("schema")
                if schema:
                    all_schemas.add(schema)

        # Include extra schemas from db_map
        if self.db_map.extra_schemas:
            all_schemas.update(self.db_map.extra_schemas)
            logger.info(
                f"Added {len(self.db_map.extra_schemas)} extra schema(s) from db_map: "
                f"{sorted(self.db_map.extra_schemas)}"
            )

        # For each suffix pair, find matching schemas and build rename map
        rename_map: dict[str, str] = {}
        for suffix_source, suffix_target in suffix_replacements.items():
            for schema in sorted(all_schemas):
                if schema.endswith(suffix_source):
                    base = schema[: -len(suffix_source)]
                    new_schema = base + suffix_target
                    rename_map[schema] = new_schema

        if rename_map:
            logger.info(
                f"Auto-discovered {len(rename_map)} schema rename(s) "
                f"from schema_suffix_replacement:"
            )
            for old, new in sorted(rename_map.items()):
                logger.info(f"  {old} -> {new}")
        else:
            logger.warning(
                "No schemas found matching suffixes in schema_suffix_replacement. "
                "No schema renames will be applied."
            )

        return rename_map if rename_map else None

    def _parse_manifest(self, manifest_data: dict[str, Any]) -> Manifest:
        """Parses raw manifest data into a Manifest object.

        Args:
            manifest_data: The raw manifest dictionary.

        Returns:
            The parsed Manifest object.
        """
        # Convert database keys from strings back to integers
        databases_dict = manifest_data.get("databases", {})
        databases_with_int_keys = {int(k): v for k, v in databases_dict.items()}

        database_metadata_dict = manifest_data.get("database_metadata", {})
        database_metadata_with_int_keys = {int(k): v for k, v in database_metadata_dict.items()}

        return Manifest(
            meta=ManifestMeta(**manifest_data["meta"]),
            databases=databases_with_int_keys,
            collections=[Collection(**c) for c in manifest_data.get("collections", [])],
            cards=[Card(**c) for c in manifest_data.get("cards", [])],
            dashboards=[Dashboard(**d) for d in manifest_data.get("dashboards", [])],
            permission_groups=[
                PermissionGroup(**g) for g in manifest_data.get("permission_groups", [])
            ],
            permissions_graph=manifest_data.get("permissions_graph", {}),
            collection_permissions_graph=manifest_data.get("collection_permissions_graph", {}),
            database_metadata=database_metadata_with_int_keys,
        )

    def _validate_metabase_version(self) -> None:
        """Validates Metabase version compatibility between export and target.

        Uses strict validation: source and target must be the same version.

        Raises:
            ValueError: If versions are incompatible or source version is missing.
        """
        manifest = self._get_manifest()
        source_version_str = manifest.meta.metabase_version
        target_version = self.config.metabase_version

        if source_version_str is None:
            logger.warning(
                "Export manifest does not contain Metabase version. "
                "This export was created with an older version of the toolkit. "
                f"Assuming target version '{target_version}' for compatibility check."
            )
            # For backward compatibility, assume the version matches if not specified
            return

        try:
            source_version = MetabaseVersion(source_version_str)
        except ValueError:
            raise ValueError(
                f"Export was created with unsupported Metabase version '{source_version_str}'. "
                f"Target version is '{target_version}'."
            ) from None

        logger.info(f"Export Metabase version: {source_version}")
        logger.info(f"Target Metabase version: {target_version}")

        validate_version_compatibility(source_version, target_version)

    def _validate_database_mappings(self) -> list[UnmappedDatabase]:
        """Validates that all databases referenced by cards have a mapping.

        Returns:
            List of unmapped databases.
        """
        manifest = self._get_manifest()
        id_mapper = self._get_id_mapper()
        unmapped: dict[int, UnmappedDatabase] = {}
        for card in manifest.cards:
            if card.archived and not self.config.include_archived:
                continue
            if card.database_id is None:
                continue
            target_db_id = id_mapper.resolve_db_id(card.database_id)
            if target_db_id is None:
                if card.database_id not in unmapped:
                    unmapped[card.database_id] = UnmappedDatabase(
                        source_db_id=card.database_id,
                        source_db_name=manifest.databases.get(card.database_id, "Unknown Name"),
                    )
                unmapped[card.database_id].card_ids.add(card.id)
        return list(unmapped.values())

    def _validate_target_databases(self) -> None:
        """Validates that all mapped database IDs exist in the target instance."""
        manifest = self._get_manifest()
        id_mapper = self._get_id_mapper()
        try:
            target_databases = self.client.get_databases()
            target_db_ids = {db["id"] for db in target_databases}

            mapped_target_ids = set()
            for source_db_id in manifest.databases.keys():
                target_id = id_mapper.resolve_db_id(source_db_id)
                if target_id:
                    mapped_target_ids.add(target_id)

            missing_ids = mapped_target_ids - target_db_ids

            if missing_ids:
                self._log_invalid_database_mapping(missing_ids, target_databases)
                raise ValueError(
                    f"Invalid database mapping: IDs {missing_ids} don't exist in target"
                )

            logger.info("All mapped database IDs are valid in the target instance.")

        except MetabaseAPIError as e:
            logger.error(f"Failed to validate database mappings: {e}")
            raise

    def _log_invalid_database_mapping(
        self, missing_ids: set[int], target_databases: list[dict[str, Any]]
    ) -> None:
        """Logs an error about invalid database mappings."""
        logger.error("=" * 80)
        logger.error("INVALID DATABASE MAPPING!")
        logger.error("=" * 80)
        logger.error("Your db_map.json references database IDs that don't exist in the target.")
        logger.error(f"Missing database IDs in target: {sorted(missing_ids)}")
        logger.error("")
        logger.error("Available databases in target instance:")
        for db in sorted(target_databases, key=lambda x: x["id"]):
            logger.error(f"  ID: {db['id']}, Name: '{db['name']}'")
        logger.error("")
        logger.error("SOLUTION: Update your db_map.json file with valid target IDs")
        logger.error("=" * 80)

    def _perform_dry_run(self) -> None:
        """Simulates the import process and reports on planned actions."""
        manifest = self._get_manifest()
        logger.info("--- Starting Dry Run ---")

        unmapped_dbs = self._validate_database_mappings()
        if unmapped_dbs:
            self._log_unmapped_databases_error(unmapped_dbs)
            raise ValueError("Unmapped databases found. Import cannot proceed.")

        logger.info("Database mappings are valid.")
        logger.info("\n--- Import Plan ---")
        logger.info(f"Conflict Strategy: {self.config.conflict_strategy.upper()}")

        # Apply filters if specified
        filtered_cards, filtered_collections, filtered_dashboards = (
            self._apply_manifest_filters(manifest)
        )

        logger.info("\nCollections:")
        for collection in sorted(filtered_collections, key=lambda c: c.path):
            logger.info(f"  [CREATE] Collection '{collection.name}' at path '{collection.path}'")

        logger.info("\nCards:")
        for card in sorted(filtered_cards, key=lambda c: c.file_path):
            if card.archived and not self.config.include_archived:
                continue
            logger.info(f"  [CREATE] Card '{card.name}' from '{card.file_path}'")

        if filtered_dashboards:
            logger.info("\nDashboards:")
            for dash in sorted(filtered_dashboards, key=lambda d: d.file_path):
                if dash.archived and not self.config.include_archived:
                    continue
                logger.info(f"  [CREATE] Dashboard '{dash.name}' from '{dash.file_path}'")

        logger.info("\n--- Dry Run Complete ---")

    def _compute_transitive_card_deps(
        self,
        initial_card_ids: set[int],
        card_by_id: dict[int, Card],
    ) -> set[int]:
        """Compute the transitive closure of card dependencies.

        Starting from `initial_card_ids`, follows card-to-card dependencies
        (source-table, source-card, template-tags, metrics) using
        `CardHandler._extract_card_dependencies` on the exported JSON files.

        Args:
            initial_card_ids: Seed card IDs to start from.
            card_by_id: Lookup of card ID → Card for all cards in the manifest.

        Returns:
            Full set of card IDs needed (seed + all transitive dependencies).
        """
        needed_card_ids: set[int] = set()
        to_process = list(initial_card_ids & set(card_by_id.keys()))

        while to_process:
            card_id = to_process.pop()
            if card_id in needed_card_ids:
                continue
            needed_card_ids.add(card_id)

            card = card_by_id.get(card_id)
            if card and card.file_path:
                try:
                    card_data = read_json_file(self.export_dir / card.file_path)
                    deps = CardHandler._extract_card_dependencies(card_data)
                    for dep_id in deps:
                        if dep_id in card_by_id and dep_id not in needed_card_ids:
                            to_process.append(dep_id)
                except Exception as e:
                    logger.warning(f"Could not extract dependencies for card {card_id}: {e}")

        return needed_card_ids

    def _compute_ancestor_collections(
        self,
        items: list[Card | Dashboard],
        collection_by_id: dict[int, Collection],
    ) -> set[int]:
        """Compute the set of ancestor collection IDs needed for a list of items.

        Walks each item's collection_id up through parent_id chains in the manifest.

        Args:
            items: Cards and/or dashboards whose ancestor collections are needed.
            collection_by_id: Lookup of collection ID → Collection from the manifest.

        Returns:
            Set of collection IDs that must be imported.
        """
        needed_collection_ids: set[int] = set()
        for item in items:
            coll_id = item.collection_id
            while coll_id and coll_id not in needed_collection_ids:
                needed_collection_ids.add(coll_id)
                coll = collection_by_id.get(coll_id)
                coll_id = coll.parent_id if coll else None
        return needed_collection_ids

    def _filter_manifest_by_card_ids(
        self,
    ) -> tuple[list[Card], list[Collection], list[Dashboard]]:
        """Filter manifest to only requested cards + transitive dependencies + ancestor collections.

        Returns:
            Tuple of (filtered_cards, filtered_collections, filtered_dashboards).
            Dashboards is always empty when filtering by card_ids only.
        """
        manifest = self._get_manifest()
        requested_ids = set(self.config.card_ids)

        card_by_id = {card.id: card for card in manifest.cards}

        # Warn about IDs not found in the manifest
        missing = requested_ids - set(card_by_id.keys())
        if missing:
            logger.warning(f"Requested card IDs not found in manifest: {sorted(missing)}")

        # Transitive dependency closure
        needed_card_ids = self._compute_transitive_card_deps(requested_ids, card_by_id)
        filtered_cards = [c for c in manifest.cards if c.id in needed_card_ids]

        # Ancestor collections
        collection_by_id = {c.id: c for c in manifest.collections}
        needed_collection_ids = self._compute_ancestor_collections(filtered_cards, collection_by_id)
        filtered_collections = [c for c in manifest.collections if c.id in needed_collection_ids]

        auto_included = len(needed_card_ids) - len(requested_ids & set(card_by_id.keys()))
        logger.info(
            f"Filtered import: {len(filtered_cards)} cards "
            f"({auto_included} auto-included dependencies), "
            f"{len(filtered_collections)} collections"
        )

        return filtered_cards, filtered_collections, []

    def _filter_manifest_by_dashboard_ids(
        self,
    ) -> tuple[list[Card], list[Collection], list[Dashboard]]:
        """Filter manifest for requested dashboards + their cards + dependencies + ancestor collections.

        Reads each dashboard's exported JSON to discover all referenced card IDs
        (from dashcards, series, parameter value sources), then computes the transitive
        card dependency closure and required ancestor collections.

        Returns:
            Tuple of (filtered_cards, filtered_collections, filtered_dashboards).
        """
        manifest = self._get_manifest()
        requested_dash_ids = set(self.config.dashboard_ids)

        card_by_id = {c.id: c for c in manifest.cards}

        # Filter dashboards
        filtered_dashboards = [d for d in manifest.dashboards if d.id in requested_dash_ids]

        missing_dash = requested_dash_ids - {d.id for d in manifest.dashboards}
        if missing_dash:
            logger.warning(f"Requested dashboard IDs not found in manifest: {sorted(missing_dash)}")

        # Collect all card IDs referenced by these dashboards
        needed_card_ids_from_dash: set[int] = set()
        for dash in filtered_dashboards:
            needed_card_ids_from_dash.update(dash.ordered_cards)
            if dash.file_path:
                try:
                    dash_data = read_json_file(self.export_dir / dash.file_path)
                    for dc in dash_data.get("dashcards", []):
                        if dc.get("card_id"):
                            needed_card_ids_from_dash.add(dc["card_id"])
                        for s in dc.get("series", []):
                            if isinstance(s, dict) and "id" in s:
                                needed_card_ids_from_dash.add(s["id"])
                    for param in dash_data.get("parameters", []):
                        vsc = param.get("values_source_config", {})
                        if vsc and vsc.get("card_id"):
                            needed_card_ids_from_dash.add(vsc["card_id"])
                except Exception as e:
                    logger.warning(f"Could not read dashboard {dash.id} for card refs: {e}")

        # Transitive card dependency closure
        needed_card_ids = self._compute_transitive_card_deps(
            needed_card_ids_from_dash, card_by_id
        )
        filtered_cards = [c for c in manifest.cards if c.id in needed_card_ids]

        # Ancestor collections for cards + dashboards
        collection_by_id = {c.id: c for c in manifest.collections}
        all_items: list[Card | Dashboard] = [*filtered_cards, *filtered_dashboards]
        needed_collection_ids = self._compute_ancestor_collections(all_items, collection_by_id)
        filtered_collections = [c for c in manifest.collections if c.id in needed_collection_ids]

        logger.info(
            f"Filtered import: {len(filtered_dashboards)} dashboards, "
            f"{len(filtered_cards)} cards, "
            f"{len(filtered_collections)} collections"
        )

        return filtered_cards, filtered_collections, filtered_dashboards

    def _apply_manifest_filters(
        self,
        manifest: Manifest,
    ) -> tuple[list[Card], list[Collection], list[Dashboard]]:
        """Apply card_ids / dashboard_ids filters from config and return filtered manifest lists.

        If neither filter is set, returns the full manifest lists unchanged.

        Args:
            manifest: The loaded manifest.

        Returns:
            Tuple of (cards, collections, dashboards) to import.
        """
        has_card_filter = self.config.card_ids is not None
        has_dash_filter = self.config.dashboard_ids is not None

        if has_card_filter and has_dash_filter:
            # Combine both filters, dedup by ID
            cards_a, colls_a, _ = self._filter_manifest_by_card_ids()
            cards_b, colls_b, dashs_b = self._filter_manifest_by_dashboard_ids()

            card_ids_seen: set[int] = set()
            filtered_cards: list[Card] = []
            for c in cards_a + cards_b:
                if c.id not in card_ids_seen:
                    filtered_cards.append(c)
                    card_ids_seen.add(c.id)

            coll_ids_seen: set[int] = set()
            filtered_collections: list[Collection] = []
            for c in colls_a + colls_b:
                if c.id not in coll_ids_seen:
                    filtered_collections.append(c)
                    coll_ids_seen.add(c.id)

            return filtered_cards, filtered_collections, dashs_b

        if has_card_filter:
            return self._filter_manifest_by_card_ids()

        if has_dash_filter:
            return self._filter_manifest_by_dashboard_ids()

        return manifest.cards, manifest.collections, manifest.dashboards

    def _perform_import(self) -> None:
        """Executes the full import process."""
        manifest = self._get_manifest()
        id_mapper = self._get_id_mapper()
        if self._query_remapper is None:
            raise RuntimeError("Query remapper not initialized")
        logger.info("--- Starting Import ---")

        unmapped_dbs = self._validate_database_mappings()
        if unmapped_dbs:
            self._log_unmapped_databases_error(unmapped_dbs)
            raise ValueError("Unmapped databases found. Import cannot proceed.")

        # Validate and build mappings
        logger.info("Validating database mappings against target instance...")
        self._validate_target_databases()

        logger.info("Building table and field ID mappings...")
        id_mapper.build_table_and_field_mappings()

        logger.info("Fetching existing collections from target...")
        target_collections = self.client.get_collections_tree(params={"archived": True})

        # Create the import context
        self._context = ImportContext(
            config=self.config,
            client=self.client,
            manifest=manifest,
            export_dir=self.export_dir,
            id_mapper=id_mapper,
            query_remapper=self._query_remapper,
            report=self.report,
            target_collections=target_collections,
        )

        # Run imports using handlers
        filtered_cards, filtered_collections, filtered_dashboards = (
            self._apply_manifest_filters(manifest)
        )

        self._import_collections(filtered_collections)

        # Pre-fetch collection items for O(1) conflict lookup
        # This must be done AFTER collections are imported so we have the collection mappings
        context = self._get_context()
        logger.info("Pre-fetching target collection items for conflict detection...")
        context.prefetch_collection_items()
        self._import_cards(filtered_cards)
        if filtered_dashboards:
            self._import_dashboards(filtered_dashboards)
        if self.config.apply_permissions and manifest.permission_groups:
            self._import_permissions()

        # Log summary and save report
        self._log_import_summary()
        self._save_report()

        if any(s["failed"] > 0 for s in self.report.summary.values()):
            logger.error("Import finished with one or more failures.")
            raise RuntimeError("Import finished with one or more failures.")
        else:
            logger.info("Import completed successfully.")

    def _import_collections(self, collections: list[Collection] | None = None) -> None:
        """Imports collections using the CollectionHandler.

        Args:
            collections: Collections to import. If None, imports all from manifest.
        """
        context = self._get_context()
        manifest = self._get_manifest()
        handler = CollectionHandler(context)
        handler.import_collections(collections if collections is not None else manifest.collections)

    def _import_cards(self, cards: list[Card] | None = None) -> None:
        """Imports cards using the CardHandler.

        Args:
            cards: Cards to import. If None, imports all from manifest.
        """
        context = self._get_context()
        manifest = self._get_manifest()
        handler = CardHandler(context)
        handler.import_cards(cards if cards is not None else manifest.cards)

    def _import_dashboards(self, dashboards: list[Dashboard] | None = None) -> None:
        """Imports dashboards using the DashboardHandler.

        Args:
            dashboards: Dashboards to import. If None, imports all from manifest.
        """
        context = self._get_context()
        manifest = self._get_manifest()
        handler = DashboardHandler(context)
        handler.import_dashboards(
            dashboards if dashboards is not None else manifest.dashboards
        )

    def _import_permissions(self) -> None:
        """Imports permissions using the PermissionsHandler."""
        context = self._get_context()
        logger.info("\nApplying permissions...")
        handler = PermissionsHandler(context)
        handler.import_permissions()

    def _log_unmapped_databases_error(self, unmapped_dbs: list[UnmappedDatabase]) -> None:
        """Logs an error about unmapped databases."""
        logger.error("=" * 80)
        logger.error("DATABASE MAPPING ERROR!")
        logger.error("=" * 80)
        logger.error("Found unmapped databases. Import cannot proceed.")
        logger.error("")
        for db in unmapped_dbs:
            logger.error(f"  Source Database ID: {db.source_db_id}")
            logger.error(f"  Source Database Name: '{db.source_db_name}'")
            logger.error(f"  Used by {len(db.card_ids)} card(s)")
            logger.error("")
        logger.error("SOLUTION: Add mappings to your db_map.json file")
        logger.error("=" * 80)

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
            report_dict = collector.to_report_dict()
            summary = report_dict["action_summary"]

            parts = []
            for id_type, type_data in report_dict["by_type"].items():
                ids = [str(item["source_id"]) for item in type_data["items"]]
                db_ids = {item["source_database_id"] for item in type_data["items"]} - {None}
                db_suffix = (
                    f" (in database{'s' if len(db_ids) > 1 else ''} "
                    f"{', '.join(str(d) for d in sorted(db_ids))})"
                    if db_ids
                    else ""
                )
                parts.append(
                    f"  - {len(ids)} {id_type} ID{'s' if len(ids) > 1 else ''}"
                    f"{db_suffix}: {', '.join(ids[:5])}{'...' if len(ids) > 5 else ''}"
                )

            logger.warning(
                f"\n⚠ {summary['total_unmapped_ids']} unmapped IDs caused "
                f"{summary['entities_skipped']} entities to be skipped and "
                f"{summary['fields_stripped']} fields to be stripped.\n"
                + "\n".join(parts)
                + "\n  Details: see import report → 'unmapped_ids' section"
            )

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
