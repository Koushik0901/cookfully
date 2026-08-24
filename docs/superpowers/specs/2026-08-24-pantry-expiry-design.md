# Pantry Expiry — Grocery-remembered lifespan + label expiry + use-soon nudges — Design

Date: 2026-08-24
Status: Draft (approved in brainstorming 2026-08-24, Approach 1)
Related: IDEAS.md §3 Pantry expiry, docs/inspiration-review.md P6, DESIGN.md v3.0, pantry/grocery models

## 1. Goal & Story

When a shopper checks off groceries, the app should *remember* when they bought it and *know* when it will spoil, so food doesn't quietly go bad in the fridge.

- **Tomato (fresh):** shopper checks off "Tomatoes" → app knows tomato lasts ~5 days (curated internet lifespan) → remembers `purchased 2026-08-24 → expires 2026-08-29` → nudges at ≤3d / ≤2d / expired across Grocery, Pantry, and Plan ("Use your tomatoes before they go — also in Pasta on Tue").
- **Milk/chicken (label):** shopper checks off "Milk" → app asks "What's the expiry on the label?" at the store (date picker) → remembers that exact date → same nudges.
- No nag for staples (flour, salt, pasta) — no expiry tracked.

Persona test: "Does this help someone plan, cook, and eat better food with less friction?" Yes — reduces waste without making expiry admin.

## 2. Data Model & Migration

### Grocery (extend)

```sql
ALTER TABLE grocery_items ADD COLUMN purchased_at TIMESTAMPTZ;
ALTER TABLE grocery_items ADD COLUMN expires_on DATE;
ALTER TABLE grocery_items ADD COLUMN expiry_source VARCHAR(10)
  CHECK (expiry_source IN ('auto','label','manual'));
-- null expiry_source means no expiry tracked
```

### Pantry (augment existing expires_on)

```sql
ALTER TABLE pantry_items ADD COLUMN purchased_at TIMESTAMPTZ;
ALTER TABLE pantry_items ADD COLUMN expiry_source VARCHAR(10)
  CHECK (expiry_source IN ('auto','label','manual'));
-- reuses existing ix_pantry_items_owner_expires_on for use-soon sort
```

Alembic revision: `add_expiry_source_to_grocery_and_pantry` — adds nullable cols, no backfill, reversible. Existing rows remain `null` → no nudge.

Invariants:
- `expires_on` non-null implies `purchased_at` non-null and `expiry_source` non-null.
- `expiry_source='manual'` is never overwritten by auto resolver; user edit always wins.
- Un-check (`checked: true → false`) clears `purchased_at/expires_on/expiry_source` atomically.
- `PantryDeduction` copies `expires_on/purchased_at/expiry_source` from grocery → pantry on `apply`; `assumption` notes `"expiry copied from grocery (auto 5d)"` or `"expiry from label"`.

## 3. Domain Logic — `domain/expiry_lifespans.py`

Pure domain module, no DB/FastAPI deps, tested in isolation.

```python
FRESH_LIFESPANS: dict[str, int] = {
  # days, fridge-stored, conservative (USDA/extension-adjacent)
  "tomato": 5, "cherry tomato": 5, "lettuce": 4, "spinach": 3, "kale": 5, "arugula": 3,
  "carrot": 14, "cucumber": 5, "zucchini": 5, "broccoli": 5, "cauliflower": 7, "celery": 10,
  "pepper": 7, "bell pepper": 7, "mushroom": 4, "onion": 21, "potato": 21, "sweet potato": 14,
  "avocado": 4, "banana": 4, "apple": 21, "berries": 3, "strawberry": 3, "blueberry": 5,
  "raspberry": 3, "grapes": 7, "lemon": 14, "lime": 14, "orange": 14, "herbs": 3, "cilantro": 3,
  "parsley": 4, "basil": 3, "asparagus": 4, "green beans": 5, "peas": 4, "corn": 3,
  "cabbage": 14, "eggplant": 5, "garlic": 30, "ginger": 14, "leek": 7, "radish": 7,
}
# ~45 entries — draft list for owner final approval in spec review

LABEL_REQUIRED_KEYWORDS: set[str] = {
  "milk","cream","yogurt","cheese","chicken","beef","pork","fish","salmon","turkey","egg","tofu","juice"
}
```

- **Normalization:** uses existing `normalize_pantry_name(display_name)` (`casefold().strip()`) plus singular fallback (strip trailing `s`/`es`) so "Tomatoes" → "tomato".
- **Resolver `resolve_expiry(display_name, requested_expires_on=None)` → (expires_on, expiry_source, purchased_at):**
  - if `requested_expires_on` provided → `expiry_source='label'` (first prompt) or `'manual'` (edit), `purchased_at=now()`
  - elif normalized in `FRESH_LIFESPANS` → `expires_on = today + days`, `expiry_source='auto'`, `purchased_at=now()` (uses `utc_now()`)
  - elif any `LABEL_REQUIRED_KEYWORDS` token in normalized name → `needs_expiry=True` (caller prompts)
  - else → no expiry (`None`)
- Manual guard: if current `expiry_source='manual'`, resolver is not re-run on future checks.

`today` is `utc_now().date()` server-side; display computes `days_left` via `todayInTimezone(preferences.timezone)`.

## 4. API Contract

### PATCH /grocery-items/{itemId} (extend GroceryItemWriteRequest)

```
PATCH /grocery-items/{itemId}
If-Match: <version>
X-Idempotency-Key: <uuid>

{ "checked": true }                  // fresh tomato → server auto-sets expiry
{ "checked": true, "expiresOn": "2026-08-28" } // milk label → client provides after prompt
{ "expiresOn": "2026-08-30" }         // manual correction → becomes manual
```

- New optional write fields: `expiresOn: date | null` (client may set on label prompt or manual edit). `expirySource` and `purchasedAt` are server-set only — client-sent `expirySource` is ignored; server sets `auto`/`label`/`manual` based on resolver.
- On `checked: true` transition server runs `resolve_expiry`:
  - fresh hit → atomically sets `purchased_at=now(), expires_on=today+days, expiry_source='auto'`
  - label-required and no `expiresOn` provided → returns `200` with `item{..., expiresOn:null, expirySource:null, needsExpiryDate:true}` (computed response-only boolean, not stored) so UI knows to prompt; `checked` stays `true` regardless.
  - client re-PATCHes with `expiresOn` → server sets `expiry_source='label'` on first prompt, `'manual'` on later edits, and `purchased_at=now()` if not already set.
- `checked: false` → clears `purchased_at/expires_on/expiry_source` atomically.
- Still `If-Match: version` + `X-Idempotency-Key` guarded; replay returns stored response.
- Validation: `expiresOn` must satisfy `today <= expiresOn <= today+90` (covers potato/cheese); `422` only if `expiresOn` is out of range, never for missing label — missing just means no nudge.

### Reads (no breaking shape change, new nullable fields)

- `GET /meal-plans/{weekStart}/grocery-list` → each `GroceryItemResponse` now includes `purchasedAt?: datetime, expiresOn?: date, expirySource?: 'auto'|'label'|'manual'`
- `GET /pantry-items`, `POST /pantry-items`, `PATCH /pantry-items/{id}` → include `purchasedAt?, expirySource?` alongside existing `expiresOn`
- `POST /meal-plans/{weekStart}/grocery-list/pantry-deductions` copies expiry fields; `assumption` text records provenance.

## 5. Frontend Flow & UX

Tokens: `DESIGN.md` v3 oklch, `color-mix(primary-container ...)`, `prefers-reduced-motion`, 390×844 + desktop 112px rail supported.

### Grocery — at the store

- `GroceryRow` checkbox → `PATCH {checked:true}`. On `needsExpiryDate` response, open bottom sheet: "When does this expire? (check the label)" with `input type=date` (`min=today`, `max=today+90`, default `today+3` hint), `Save expiry` → `PATCH {expiresOn}` and `Skip` leaves untracked.
- Auto case: badge appears immediately beside quantity: `Expires Aug 29 • 4 days` (mint neutral while >3d). Tapping badge opens same sheet to correct → becomes `manual`.
- `aria-label` includes expiry for screen readers; keyboard tab reaches badge; sheet is focus-trapped.

### Pantry — home for expiry

- `GET /pantry-items` sorted client-side or via service `ORDER BY expires_on ASC NULLS LAST, normalized_food_name` (reuses `ix_pantry_items_owner_expires_on`).
- Row chips: `≤3d` mint "Expires in 3d", `≤2d` amber "Use soon — 2d left", `≤0d` urgent/expired. Edit sheet same as grocery; disclosure shows `expirySource` provenance ("Auto 5d • Tomato" / "From label" / "You set").

### Plan — closing the loop

- Derived `useExpiringPantry(threshold=3)` from `GET /pantry-items` (no new endpoint): items where `today <= expires_on <= today+3`.
- Match against planned recipes via existing `normalized_food_name` containment (same as pantry search). If any expiring items intersect a planned entry, banner above `WeekOverview`: "Use soon: tomatoes (2d) — also in *Pasta al Pomodoro* on Tue dinner" with `View in Pantry` link. If no intersection, banner shows Pantry use-soon list only. No auto-reorder of plan.

Empty/loading/error states mirror existing grocery/pantry patterns.

## 6. Edge Cases & Non-Goals

- No notifications/push, no background job in v1 — nudge is list/badge only.
- No fridge-vs-counter lifespans; table assumes fridge.
- No per-user lifespan editing UI; table is code-curated, item-level `manual` edit covers overrides.
- No barcode pack-size in v1.
- Timezone: `expires_on` is a `date`; `days_left` computed with owner timezone so "1 day left" matches their wall clock.
- Idempotency + optimistic locking preserved; `manual` never auto-overwritten.

## 7. Testing

- Backend unit: `TestExpiryLifespans` (45 entries, plural/casefold, label keywords), `TestGroceryExpiryFlow` (auto on tomato, label-required needs prompt, manual guard, uncheck clears, 90d bound, idempotency replay), `TestPantryUseSoonSort`.
- Backend contract: `PATCH /grocery-items checked` + `GET /pantry-items sort` + deduction copy.
- Frontend: `GroceryExpiry.test.tsx` (auto badge, label sheet, manual edit), `PantryUseSoon.test.tsx` (sort + chip), `PlanExpiringBanner.test.tsx` (only when expiring intersects plan).

## 8. Rollout

- Alembic migration, no backfill. Feature is progressive — `null` expiry = no UI.
- No feature flag needed; safe to ship behind existing `grocery:write` scope.
- Follow-up: measure whether `auto` lifespans feel right (adjust days in `FRESH_LIFESPANS`) before adding notifications or fridge/counter split.
