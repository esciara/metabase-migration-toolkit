# Single Card & Dashboard Export/Import - Study

Analysis and implementation roadmap for adding single-card and single-dashboard export/import to the Metabase migration toolkit.

**Recommendation**: PROCEED — highly feasible, ~200 lines of code, 9-14 hours, zero breaking changes.

## Documents

| Document | Read time | Content |
|----------|-----------|---------|
| [KEY_FINDINGS.md](KEY_FINDINGS.md) | 5-10 min | Executive summary: feasibility, dependency graph, required code changes, effort estimate |
| [single_card_dashboard_analysis.md](single_card_dashboard_analysis.md) | 30+ min | Comprehensive technical deep-dive (988 lines). Section 10 has all file locations & line numbers |
| [IMPLEMENTATION_ROADMAP.md](IMPLEMENTATION_ROADMAP.md) | 30 min | Step-by-step implementation plan with copy-paste-ready code snippets |

## Key insight

The import side requires **zero changes** — it's manifest-driven and already works with any manifest (full or partial). Only the export side needs new entry points to accept `--card-ids` / `--dashboard-ids` and build minimal collection trees.

## Analysis date

2026-03-27