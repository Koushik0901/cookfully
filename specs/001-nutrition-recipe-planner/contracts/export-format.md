# Backup and Portable Export Contract

## Two Artifacts

1. **Disaster-recovery backup**: operator-facing archive with PostgreSQL dump, media, manifest,
   checksums, application/schema versions, and restore instructions.
2. **Portable export**: user-facing ZIP with versioned JSON documents and media files. It is stable
   across application internals and suitable for migration or independent inspection.

Neither artifact includes password hashes, sessions, API/MCP token hashes, encryption keys, provider
credentials, raw prompts/responses, failed-import diagnostic HTML, detailed job diagnostics, or expired
job payloads.

## Portable ZIP Layout

```text
vigor-vine-export-YYYYMMDDTHHMMSSZ.zip
├── manifest.json
├── data/
│   ├── recipes.ndjson
│   ├── ingredients.ndjson
│   ├── nutrition-estimates.ndjson
│   ├── nutrition-corrections.ndjson
│   ├── goals.ndjson
│   ├── meal-plans.ndjson
│   ├── meal-plan-entries.ndjson
│   ├── grocery-lists.ndjson
│   └── grocery-items.ndjson
└── media/
    └── <sha256>.<safe-extension>
```

P4-P6 add versioned optional files for suggestion history and pantry records; older importers ignore
unknown optional files.

## Manifest

```json
{
  "format": "vigor-vine-portable-export",
  "schemaVersion": 1,
  "createdAt": "2026-08-09T18:00:00Z",
  "applicationVersion": "0.1.0",
  "nutritionMethodologyVersion": "1",
  "referenceDatasets": [
    {"provider": "usda_fdc", "datasetType": "foundation", "releaseId": "..."}
  ],
  "files": [
    {"path": "data/recipes.ndjson", "records": 42, "sha256": "..."}
  ]
}
```

Every NDJSON record includes `schemaVersion`, stable ID, created/updated timestamps, and the public
domain fields defined in `data-model.md`. Nutrients and ingredient quantities serialize as canonical
decimal strings with at most six fractional places; servings use at most three; plan snapshot calories
use whole-kilocalorie strings and macros use one-decimal strings. Dates and timestamps use ISO 8601.
Null means unavailable; decimal string `"0"` or `"0.0"` remains a true zero.

Permanently deleted recipes are absent. Historical MealPlanEntry snapshots and GroceryItem source text
remain with a null recipe link so exports preserve the meaning of prior plans without recreating erased
recipe ingredients, estimates, corrections, or media.

## Import and Restore Rules

- Validate archive traversal, file allowlist, uncompressed size, record limits, manifest checksums,
  schema version, and referenced media before writing authoritative state.
- Stage portable imports under a generated import ID and report create/update/conflict counts before
  commit. Existing IDs require an explicit merge policy.
- Disaster recovery restores only into an empty compatible instance unless the operator selects an
  explicit destructive replacement workflow outside the application UI.
- A failed validation or import leaves existing data unchanged and records a safe diagnostic report.
- Restore verification must cover every core entity, active correction, meal snapshot, grocery manual
  state, and media checksum.
- Operator restore guidance MUST disclose that a backup can predate an owner erasure and require the
  operator to reapply documented post-backup erasures before returning the instance to service.
