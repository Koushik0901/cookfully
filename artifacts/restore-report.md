# Clean-instance backup, export, and restore report

Date: 2026-08-10  
Result: **PASS**  
Database: PostgreSQL 18 Docker service, with a fresh randomly named schema and empty media/staging
directories for every restore case

## Commands and results

The database URL was assembled from the running disposable PostgreSQL container without printing its
password. The evidence command was:

```powershell
uv run --directory backend pytest `
  tests/integration/test_backup_restore.py::test_clean_instance_backup_export_restore_preserves_exact_safe_state `
  tests/integration/test_backup_restore.py::test_full_backup_restore_replays_later_erasure_without_resurrection `
  tests/integration/test_backup_restore.py::test_restore_fails_closed_for_missing_or_discontinuous_ledger `
  tests/integration/test_owner_erasure.py::test_older_backup_replays_owner_erasure_to_zero_resurrection `
  -q -s
```

Result: **4 passed in 5.69s**. The wider backup/export/owner-erasure group also passed **9 tests in
8.05s**. Ruff and strict mypy passed for the changed restore implementation and evidence tests.

Every test creates a fresh source schema through the standard isolated-database fixture. Every restore
creates a second empty schema, builds all current tables, requires an empty target media root, and
drops the disposable schemas after the comparison. No live application schema or user filesystem was
used.

## Ordinary backup/export/restore

Both the disaster-recovery backup and portable export were created from the same source graph and
verified before restore. The backup/current ledger cursors were both `0`; no replay was needed and the
restore report returned `active: true`, no resurrected recipe IDs, and no resurrected owner IDs.

Observed exact values after database round trip:

| Value | Source/export | Restored PostgreSQL |
| --- | --- | --- |
| Recipe yield | `2.000` | `2.000` |
| Ingredient quantity | `200.000000` | covered by zero-row-difference comparison |
| Active correction | `210.000000` | `210.000000` |
| Goal calories | `2200.000000` | `2200.000000` |
| Snapshot servings | `1.500` | `1.500` |
| Snapshot protein display precision | `60.1` | `60.1` |

The portable manifest declared stored scale 6 and serving scale 3. `backup compare` reported
`missingRows: 0` and `unexpectedRows: 0` across every included table.

The safe recipe image contained exactly 16 bytes (`safe-image-bytes`) in both archives and after
restore. An opt-in encrypted failed-import diagnostic was present in source storage and its database
metadata, but its storage key and bytes were absent from both backup and portable export and absent
from restored media.

Detached history survived unchanged: the meal entry kept `recipe_id: null` and title
`Deleted protein bowl`; the grocery source kept `ingredient_id: null` and original text
`200 g tofu from deleted recipe`.

Machine-readable line emitted by the run:

```json
{"backupCursor":0,"correctionDecimal":"210.000000","currentCursor":0,"detachedHistoryPreserved":true,"diagnosticsExcluded":true,"goalKcal":"2200.000000","missingRows":0,"safeMediaBytes":16,"snapshotServings":"1.500","unexpectedRows":0,"yieldQuantity":"2.000"}
```

## Recipe-owned erasure replay

The backup was anchored at cursor `0`. After backup creation, the live independent ledger appended
one `recipe_owned` record and advanced to cursor `1`. Restore verified the cursor-0 hash anchor,
replayed record `019fed62-2a4e-7c40-9f9e-baa799b9357e`, and returned:

- `active: true`
- `backupCursor: 0`, `currentCursor: 1`
- `resurrectedRecipeIds: []`
- comparison `missingRows: 0`, `unexpectedRows: 0`
- erased recipe, ingredients, corrections, and recipe media absent
- detached plan title and grocery source text retained

The UUID is evidence from this run and is expected to change on a later run; the cursor and
zero-resurrection invariants are stable.

## Owner-owned erasure replay

An older backup was created before full-owner erasure. The independent ledger then appended one
`owner_owned` record at cursor `1`. Restore verified and replayed record
`019fed62-350c-7d4b-a09e-78fef5ae9e2b`, returned `active: false`, and produced:

- `backupCursor: 0`, `currentCursor: 1`
- `resurrectedOwnerIds: []`
- `resurrectedRecipeIds: []`
- empty bootstrap state for every non-reference table
- zero restored managed-media files

This proves that an older backup cannot reactivate the erased owner. A new owner may be bootstrapped
only after the inactive restore report is reviewed.

## Fail-closed evidence

The same verified archive was attempted against two additional empty targets:

1. With no current ledger, restore raised `restore_ledger_required` before inserting any owner row.
2. With the ledger cursor tampered from `1` to `2`, continuity verification raised
   `restore_ledger_invalid` before inserting any owner row.

Both targets remained empty. Checksum, archive traversal, duplicate member, non-empty target,
non-empty media, and staging collision failures are covered by the adjacent backup/export contract
tests and remain fail-closed.

## Defect found and corrected

The first ordinary-media run exposed a circular foreign-key ordering defect: `media_assets.recipe_id`
was inserted before its recipe during restore. Earlier recipe-erasure evidence removed the media row
and could not reveal it. Restore now temporarily defers both sides of the recipe/media relationship,
inserts the complete graph, then reconnects media-to-recipe and recipe-to-image links. The passing
ordinary restore and 16-byte media comparison are regression evidence for this correction.
