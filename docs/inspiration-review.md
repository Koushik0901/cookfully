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
