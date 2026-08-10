# Inspiration Review Log

This log keeps comparisons with established self-hosted applications explicit and falsifiable. An
inspiration project is evidence that a pattern can work in its own context—not proof that the pattern
fits Vigor & Vine. Likewise, a local design is not preferred merely because it is already implemented.

For each material subsystem review:

1. inspect current official source code, API documentation, or maintained project documentation;
2. state the problem and relevant differences in persona, scale, compatibility burden, and threat model;
3. identify benefits, failure modes, and operational costs in both the reference and proposed designs;
4. record whether the pattern is adopted, adapted, or rejected and link the local contract/test evidence;
5. revisit the conclusion when either project materially changes.

## P5 external access and API keys — 2026-08-10

### Sources inspected

- [Mealie repository](https://github.com/mealie-recipes/mealie) and its maintained API-token workflow
- [Tandoor Recipes repository](https://github.com/TandoorRecipes/recipes) and bearer-token API usage
- [Immich authentication documentation](https://api.immich.app/authentication) and
  [API-key creation contract](https://api.immich.app/endpoints/api-keys/createApiKey)
- [Immich v1.136 API-key behavior change](https://github.com/immich-app/immich/discussions/20133)

### Objective comparison

Mealie and Tandoor prove that a self-hosted recipe application benefits from owner-managed,
long-lived credentials that work with small external integrations. Their comparatively broad token
authority reduces configuration friction, but it gives a leaked automation credential more power than
many integrations require. Recommending a separate non-admin account reduces exposure in a multi-user
system, but does not fit Vigor & Vine's deliberately single-owner model and would introduce a second
identity concept only to compensate for coarse tokens.

Immich's fine-grained API-key permissions and once-only secret presentation better match the local
least-privilege and recoverability requirements. Its history also demonstrates a liability: routes with
missing or ambiguous permission declarations can accidentally widen authority or require breaking
changes when corrected. Immich's large permission catalog is appropriate for its much broader asset
domain, but would be needless configuration burden here.

### Local decision

Adapt the strongest parts rather than copy one implementation:

- owner-created, named, revocable, expiring long-lived credentials;
- raw secret shown exactly once and only a hash stored;
- a small allowlist of domain scopes, defaulting to read-only;
- every MCP tool declares and enforces a scope; undeclared tools fail closed;
- mutations additionally require idempotency keys and optimistic versions;
- token use is rate-limited and audited without logging secrets or personal nutrition values.

Evidence is defined by `specs/001-nutrition-recipe-planner/contracts/mcp-tools.md` and tasks
T115–T127. This decision should be reconsidered if the product becomes broadly multi-user, because
resource ownership and delegated administration would then need a richer authorization model.

## P6 pantry matching and reversible grocery deductions — 2026-08-10

### Sources inspected

- [Mealie shopping-list documentation](https://docs.mealie.io/documentation/getting-started/features/)
  and its maintained repository food/unit model
- [Tandoor shopping documentation](https://docs.tandoor.dev/features/shopping/) and its maintained
  repository food/unit merge and rename behavior
- [Immich stable trash restore contract](https://api.immich.app/endpoints/trash/restoreTrash) and
  [trash settings](https://docs.immich.app/administration/system-settings/)

### Objective comparison

Mealie and Tandoor both validate the usefulness of linking recipes or meal plans to editable shopping
lists and of maintaining reusable food/unit identities. Those patterns reduce repeated entry and make
manual reconciliation understandable. Neither maintained feature description establishes a
nutrition-grade pantry ledger with exact remaining quantities, safe dimensional conversion, or
reversible subtraction. Treating their shopping behavior as proof for automatic pantry deductions
would therefore overstate the available evidence. Their flexible user-defined units are valuable for
recipe capture, but unsafe as an automatic conversion basis when density or package size is unknown.

Immich is not a food-domain reference, so its asset model should not be copied into pantry storage.
Its explicit trash/restore lifecycle does provide useful contrary evidence to irreversible convenience
actions: reversible state is operationally valuable, but it also requires clear state boundaries and
can fail when underlying state changes independently.

### Local decision

Adapt the editable identity and explicit restore ideas while keeping stricter arithmetic boundaries:

- normalize names for discovery but retain the user's display text;
- auto-match only exact unambiguous food identities; expose fuzzy matches for review;
- convert only within mass, volume, or count dimensions, never by an assumed density or package size;
- consume pantry quantities only through an explicit grocery deduction command;
- persist both sides of every six-decimal conversion and refuse reversal after intervening edits;
- keep unmatched, proposed, partial, and missing states visible instead of treating them as zero.

The first evidence is in tasks T128–T138 and their pantry/micronutrient unit and API contract tests.
This decision should be revisited if a future barcode/package model supplies trustworthy package
quantities or if the reference projects add a well-tested pantry ledger with stronger guarantees.

## P9 backup, maintenance, and full-owner erasure — 2026-08-10

### Sources inspected

- [Mealie backup and restore documentation](https://docs.mealie.io/documentation/getting-started/usage/backups-and-restoring/)
- [Tandoor backup documentation](https://docs.tandoor.dev/system/backup/) and
  [update guidance](https://docs.tandoor.dev/system/updating/)
- [Immich backup and restore documentation](https://docs.immich.app/administration/backup-and-restore/),
  [maintenance mode](https://docs.immich.app/administration/maintenance-mode/),
  [system integrity checks](https://docs.immich.app/administration/system-integrity/), and
  [user deletion lifecycle](https://docs.immich.app/administration/user-management/)

### Objective comparison

Mealie's integrated backup screen and explicit destructive-restore warning make a complex operation
approachable. Its documented recovery suggestion to edit a failed backup's JSON can rescue partial
data, but weakens reproducibility and is unsuitable for an erasure-sensitive activation gate unless
the edited artifact is revalidated. Tandoor is unusually candid that its application-level backup is
not yet a complete DR solution; separating PostgreSQL and media and telling operators to test restores
are sound, but consistency and replay remain the operator's responsibility.

Immich supplies the strongest operational reference: explicit maintenance mode, pre-restore points,
automatic rollback on restore failure, storage integrity markers, and delayed versus immediate user
deletion. Those mechanisms fit its multi-user, very-large-asset domain. Copying its delayed user
deletion into this single-owner planner would conflict with the clarified offline exact-confirmation
requirement, and filesystem marker checks alone do not prevent an older backup from resurrecting
previously erased data. None of the three maintained documents establishes an independent,
content-free, hash-chained erasure ledger that gates restored backups.

### Local decision

Adapt their clearest operational lessons—maintenance as an explicit state, destructive confirmation,
database-plus-filesystem completeness, restore integrity checks, rollback before irreversible
commit, and routine restore drills. Go further where the local privacy contract requires it:

- active API/worker/outbox processes hold shared database leases; erasure requires an exclusive lease;
- files move to same-volume quarantine before one durable `owner_owned` ledger append;
- pre-ledger failure rolls back, while post-ledger failure remains visibly maintenance-locked and
  resumes idempotently;
- the independently preserved ledger replays later erasures into every older backup before activation.

This is not asserted to be universally better. It adds a database lock, independent storage,
operator ceremony, and recovery states that smaller installations must understand. Reconsider it if
future evidence shows the ledger cannot be operated reliably, but do not weaken zero-resurrection
without changing the product's explicit privacy guarantee.

## P10 reference performance — 2026-08-10

### Sources inspected

- [Mealie maintained repository](https://github.com/mealie-recipes/mealie) and self-hosting feature documentation
- [Tandoor Recipes maintained repository](https://github.com/TandoorRecipes/recipes) and shopping documentation
- [Immich maintained repository](https://github.com/immich-app/immich) and backup/worker-oriented operator documentation

### Objective comparison

The three projects demonstrate that recipe libraries, editable shopping workflows, and asynchronous
media or data processing can operate in self-hosted container deployments. They differ materially in
user model, asset volume, query shape, nutrition arithmetic, and background workload. No maintained
source reviewed here publishes an apples-to-apples 10,000-recipe, 50-plan-entry benchmark on the local
4-vCPU/8-GiB profile. Absence of such a report is not evidence that they are slow, and the local pass is
not evidence that its architecture is generally superior.

### Local decision

Use their deployed shapes as workload prompts, then measure the actual local contract. T144 therefore
profiles HTTP reads/search, optimistic plan writes, persisted job acknowledgement and polling, grocery
reconciliation, and solver execution independently. Keep raw three-run results and maximums, disclose
the measurement boundary, and rerun before raising scale or concurrency. Evidence and limitations are
in `docs/performance.md` and `artifacts/performance-report.json`.
