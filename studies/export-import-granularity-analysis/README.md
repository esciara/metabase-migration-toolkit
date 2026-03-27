# Export/Import Granularity Analysis - Documentation Index

This directory contains a comprehensive analysis of the export/import/sync feature's granularity in the Metabase Migration Toolkit.

## Files in This Analysis

### 1. **EXECUTIVE_SUMMARY.md** ⭐ START HERE
- **Best for**: Quick overview and key findings
- **Length**: 218 lines
- **Contents**:
  - Direct answers to all 7 core questions
  - Key findings and limitations
  - Workarounds for finer granularity
  - Code location reference table
  - Architecture overview with diagrams

**Start with this file for a complete but concise understanding.**

### 2. **QUICK_REFERENCE.md**
- **Best for**: Quick lookup and CLI examples
- **Length**: 147 lines
- **Contents**:
  - Core findings in bullet points
  - Configuration parameter table
  - CLI usage examples
  - Code location quick index
  - Single-page reference format

**Use this for quick parameter lookup and CLI command examples.**

### 3. **EXPORT_IMPORT_GRANULARITY_ANALYSIS.md**
- **Best for**: Deep dive with detailed code analysis
- **Length**: 581 lines
- **Contents**:
  - Thorough explanation of each mechanism
  - Actual code snippets with line numbers
  - Flow diagrams and visualizations
  - Comparison matrices (Export vs Import vs Sync)
  - Design rationale and architectural decisions
  - Detailed configuration examples

**Use this when you need the complete picture with code references.**

### 4. **CODE_REFERENCES.md**
- **Best for**: Developers and code navigation
- **Length**: 351 lines
- **Contents**:
  - Exact file locations and line numbers
  - Method signatures and key code blocks
  - Configuration class definitions
  - CLI argument parsing details
  - Search patterns for finding relevant code
  - Architecture summary
  - Test file references

**Use this for precise code locations and implementation details.**

---

## Quick Navigation

### I want to understand the granularity...
→ Start with **EXECUTIVE_SUMMARY.md**

### I want to use the tools...
→ See **QUICK_REFERENCE.md** for CLI examples

### I want all the details...
→ Read **EXPORT_IMPORT_GRANULARITY_ANALYSIS.md**

### I want to find specific code...
→ Consult **CODE_REFERENCES.md**

---

## Key Findings at a Glance

### ✅ What IS Possible
- Export entire collections with `--root-collections`
- Export multiple collections: `--root-collections 1,2,5`
- Toggle dashboards: `--include-dashboards`
- Toggle archived items: `--include-archived`
- Toggle permissions: `--include-permissions`
- Import with conflict resolution: `--conflict skip|overwrite|rename`
- Dry-run mode for import: `--dry-run`

### ❌ What's NOT Possible
- Export individual cards
- Export individual dashboards
- Exclude specific cards from a collection
- Filter by card/dashboard name or tags
- Scope import to specific collections
- Selectively import subsets from a manifest

### ⚠️ Important Limitations
- **Minimum scope**: Collection (not card or dashboard)
- **Import has no scoping**: Always imports entire manifest
- **All-or-nothing toggles**: `--include-dashboards`, `--include-archived`, `--include-permissions`
- **No per-item control**: Cannot exclude specific items within a collection
- **No single-item export**: Not planned or requested in codebase

---

## Core Questions Answered

| # | Question | Answer | Reference |
|---|----------|--------|-----------|
| 1 | Can you export/import a single card or dashboard? | NO - minimum is collection | EXECUTIVE_SUMMARY.md |
| 2 | How is export scope determined? | Via `--root-collections` CLI arg | EXECUTIVE_SUMMARY.md |
| 3 | Is there a `root_collection` parameter? | YES: `root_collection_ids` | EXECUTIVE_SUMMARY.md |
| 4 | What's the minimum scope? | A single collection with ALL contents | EXECUTIVE_SUMMARY.md |
| 5 | Iterate all or individual items? | All collections (filtered), ALL items within | EXECUTIVE_SUMMARY.md |
| 6 | Card/dashboard/item filtering? | NO filtering - only collection & toggles | EXECUTIVE_SUMMARY.md |
| 7 | TODOs or feature requests? | NONE found - not planned | EXPORT_IMPORT_GRANULARITY_ANALYSIS.md |

---

## Usage Examples

### Export single collection
```bash
python export_metabase.py --source-url https://source.com \
  --source-username admin --source-password pwd \
  --export-dir ./export --root-collections 42
```

### Export multiple collections
```bash
python export_metabase.py --source-url https://source.com \
  --source-username admin --source-password pwd \
  --export-dir ./export --root-collections 1,2,5,10
```

### Import with dry-run
```bash
python import_metabase.py --target-url https://target.com \
  --target-username admin --target-password pwd \
  --export-dir ./export --db-map db_map.json --dry-run
```

### Sync with collection filtering
```bash
python sync_metabase.py --source-url https://source.com \
  --target-url https://target.com \
  --source-username admin --source-password pwd \
  --target-username admin --target-password pwd \
  --root-collections 1,2 --export-dir ./export \
  --db-map db_map.json
```

---

## Architecture Summary

```
Export:
  - Scope: Collection-level via --root-collections
  - Filtering: Collections yes, items no
  - Result: Manifest with ALL items from filtered collections

Import:
  - Scope: No filtering - imports everything
  - Conflict: Strategies available (skip/overwrite/rename)
  - Result: Target has everything from manifest

Sync:
  - Phase 1: Export with optional --root-collections
  - Phase 2: Import everything from result (no selective import)
  - Result: Target synced with filtered source
```

---

## Analysis Methodology

This analysis was conducted by:
1. Reading all export/import/sync entry points
2. Examining config models and CLI argument parsing
3. Tracing export service logic and filtering mechanisms
4. Analyzing import service for selective processing
5. Reviewing manifest structure and dependencies
6. Searching for TODO/FIXME comments about granularity
7. Checking test files for feature hints
8. Documenting exact line numbers and code locations

**Files analyzed**: 25+ Python files, 3000+ lines of code
**Configuration classes examined**: ExportConfig, ImportConfig, SyncConfig
**Service methods traced**: 15+ key methods across export/import services

---

## Related Code

**Config definitions** (lib/config.py):
- ExportConfig: lines 132-192
- ImportConfig: lines 210-286
- SyncConfig: lines 500-665

**Export service** (lib/services/export_service.py):
- run_export(): lines 82-145
- _traverse_collections(): lines 189-263
- _process_collection_items(): lines 265-300

**Import service** (lib/services/import_service.py):
- run_import(): lines 87-108
- _perform_import(): lines 304-361

---

## Conclusion

The export/import/sync feature is **intentionally designed around collection-level granularity**. This is a deliberate architectural choice that:
- Reflects Metabase's collection-based organization
- Handles card dependencies automatically
- Provides manifest-based import/export
- Aligns with typical use cases (department/team migration)

**There is no per-card or per-dashboard export capability, and none is planned.**

For users needing finer granularity, options include:
1. Reorganizing collections before export
2. Manually editing manifest.json (advanced)
3. Requesting this as a feature

---

**Generated**: March 27, 2026
**Analysis Scope**: Metabase Migration Toolkit - Export/Import/Sync Features
**Total Documentation**: 1,297 lines across 4 files
