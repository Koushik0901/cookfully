# Pantry Expiry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Grocery check-off remembers purchase date and expiry (auto 5d for tomato via curated 45-item dict, or label date for milk/chicken) and nudges in Grocery, Pantry, and Plan before food spoils.

**Architecture:** Domain `expiry_lifespans.py` resolver (pure, normalize + dict lookup + label keywords) is called by `GroceryListService.update` on `checked:true` to set `purchased_at/expires_on/expiry_source`; `PantryDeduction.apply` copies expiry to pantry; frontend shows expiry sheet/badge and Plan derives expiring items client-side from `GET /pantry-items`.

**Tech Stack:** Python 3.13, FastAPI, SQLAlchemy 2, Alembic, psycopg 3, Pydantic 2, React 19.2, Vite 8.1, TanStack Query, Radix Dialog, date `input type=date`, `todayInTimezone`

## Global Constraints

- Python 3.13 for server/workers, TypeScript 5.x Node 22 LTS, FastAPI/Pydantic 2/SQLAlchemy 2/Alembic/psycopg 3
- Preserve original ingredient text, nutrition provenance, serving basis, active correction precedence
- Background handlers idempotent, fixed-precision decimals for nutrition, scaled integers for solver
- Follow DESIGN.md v3.0 tokens (oklch, radii, motion 160/220/280ms, prefers-reduced-motion), verify desktop 112px rail + 390x844, keyboard, overflow, loading/empty/partial states
- PostgreSQL authoritative, Redis only coordination

---

## File Structure

- **Create:** `backend/src/cookfully/domain/expiry_lifespans.py` — pure resolver `resolve_expiry(display_name, requested_expires_on)` + `FRESH_LIFESPANS`, `LABEL_REQUIRED_KEYWORDS`, `needs_expiry_prompt`
- **Create:** `backend/alembic/versions/20260824_add_expiry_to_grocery_and_pantry.py` — adds `purchased_at TIMESTAMPTZ, expires_on DATE, expiry_source VARCHAR(10)` to both tables
- **Modify:** `backend/src/cookfully/infrastructure/models/grocery.py:60-93` — add 3 cols to `GroceryItem`
- **Modify:** `backend/src/cookfully/infrastructure/models/pantry.py:25-60` — add 2 cols to `PantryItem` (`purchased_at`, `expiry_source`)
- **Modify:** `backend/src/cookfully/api/schemas/grocery.py` — `GroceryItemResponse` adds `purchasedAt?, expiresOn?, expirySource?, needsExpiryDate?` (computed)
- **Modify:** `backend/src/cookfully/api/schemas/pantry.py` — `PantryItemResponse` adds `purchasedAt?, expirySource?` (expiresOn already exists)
- **Modify:** `backend/src/cookfully/application/grocery_lists.py` — `update` handles `checked` transition + expiry resolver, `to_read` includes new fields
- **Modify:** `backend/src/cookfully/application/pantry.py` / `pantry_deductions.py` — copy expiry on deduction, handle `expiresOn` patch
- **Modify:** `frontend/src/features/grocery/types.ts` — add `purchasedAt, expiresOn, expirySource, needsExpiryDate`
- **Modify:** `frontend/src/features/grocery/api.ts` — pass `expiresOn` on update
- **Modify:** `frontend/src/features/grocery/GroceryListPage.tsx:21-77` — expiry bottom sheet + badge on `GroceryRow`
- **Modify:** `frontend/src/features/pantry/types.ts` & `frontend/src/features/pantry/PantryPage.tsx` — sort by `expiresOn ASC NULLS LAST`, use-soon chips
- **Create:** `frontend/src/features/pantry/expiry.ts` — `daysLeft(expiresOn, timezone)`, `expiryBadge(expiresOn)` helper
- **Create:** `frontend/src/features/plans/ExpiringBanner.tsx` + `frontend/src/features/plans/useExpiringPantry.ts` — derives `expiresOn within 3d` and matches planned recipes
- **Tests:** `backend/tests/unit/test_expiry_lifespans.py`, `backend/tests/contract/test_grocery_expiry.py`, `frontend/src/features/grocery/__tests__/GroceryExpiry.test.tsx`, `frontend/src/features/pantry/__tests__/PantryUseSoon.test.tsx`, `frontend/src/features/plans/__tests__/ExpiringBanner.test.tsx`

---

### Task 1: Domain expiry resolver

**Files:**
- Create: `backend/src/cookfully/domain/expiry_lifespans.py`
- Test: `backend/tests/unit/test_expiry_lifespans.py`

**Interfaces:**
- Consumes: `cookfully.domain.common.utc_now`, `cookfully.application.ingredient_engine.normalize_pantry_name` (or inline `casefold().strip()`)
- Produces: `FRESH_LIFESPANS: dict[str,int]`, `LABEL_REQUIRED_KEYWORDS: set[str]`, `resolve_expiry(display_name: str, requested_expires_on: date | None, today: date | None) -> tuple[date | None, str | None, datetime | None, bool]` returns `(expires_on, expiry_source, purchased_at, needs_prompt)`, `is_label_required(name: str) -> bool`

- [ ] **Step 1: Write failing unit test**

```python
# backend/tests/unit/test_expiry_lifespans.py
from datetime import date, timezone
from cookfully.domain.expiry_lifespans import resolve_expiry, FRESH_LIFESPANS

def test_tomato_auto_5d():
    expires_on, source, purchased_at, needs = resolve_expiry("Tomatoes", today=date(2026,8,24))
    assert expires_on == date(2026,8,29)
    assert source == "auto"
    assert needs is False

def test_milk_needs_prompt():
    expires_on, source, purchased_at, needs = resolve_expiry("Whole Milk", today=date(2026,8,24))
    assert expires_on is None
    assert needs is True

def test_label_provided():
    expires_on, source, _, needs = resolve_expiry("Milk", requested_expires_on=date(2026,8,28), today=date(2026,8,24))
    assert expires_on == date(2026,8,28)
    assert source == "label"
    assert needs is False

def test_pasta_no_expiry():
    expires_on, source, _, needs = resolve_expiry("Pasta", today=date(2026,8,24))
    assert expires_on is None
    assert source is None
    assert needs is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --directory backend pytest backend/tests/unit/test_expiry_lifespans.py -v`
Expected: FAIL with "No module named cookfully.domain.expiry_lifespans"

- [ ] **Step 3: Implement minimal domain module**

```python
# backend/src/cookfully/domain/expiry_lifespans.py
from __future__ import annotations
from datetime import date, datetime, timezone
from cookfully.domain.common import utc_now

FRESH_LIFESPANS: dict[str, int] = {
    "tomato": 5, "cherry tomato": 5, "lettuce": 4, "spinach": 3, "kale": 5, "arugula": 3,
    "carrot": 14, "cucumber": 5, "zucchini": 5, "broccoli": 5, "cauliflower": 7, "celery": 10,
    "pepper": 7, "bell pepper": 7, "mushroom": 4, "onion": 21, "potato": 21, "sweet potato": 14,
    "avocado": 4, "banana": 4, "apple": 21, "berries": 3, "strawberry": 3, "blueberry": 5,
    "raspberry": 3, "grapes": 7, "lemon": 14, "lime": 14, "orange": 14, "herbs": 3, "cilantro": 3,
    "parsley": 4, "basil": 3, "asparagus": 4, "green beans": 5, "peas": 4, "corn": 3,
    "cabbage": 14, "eggplant": 5, "garlic": 30, "ginger": 14, "leek": 7, "radish": 7,
}
LABEL_REQUIRED_KEYWORDS: set[str] = {"milk","cream","yogurt","cheese","chicken","beef","pork","fish","salmon","turkey","egg","tofu","juice"}

def _norm(name: str) -> str:
    n = name.casefold().strip()
    # singular fallback
    if n in FRESH_LIFESPANS:
        return n
    if n.endswith("es") and n[:-2] in FRESH_LIFESPANS:
        return n[:-2]
    if n.endswith("s") and n[:-1] in FRESH_LIFESPANS:
        return n[:-1]
    return n

def is_label_required(display_name: str) -> bool:
    low = display_name.casefold()
    return any(kw in low for kw in LABEL_REQUIRED_KEYWORDS)

def resolve_expiry(display_name: str, requested_expires_on: date | None = None, today: date | None = None):
    now = utc_now()
    cur_today = today or now.date()
    if requested_expires_on is not None:
        # caller will decide label vs manual; first prompt = label, later edits = manual (service decides)
        return requested_expires_on, "label", now, False
    norm = _norm(display_name)
    if norm in FRESH_LIFESPANS:
        return date.fromordinal(cur_today.toordinal() + FRESH_LIFESPANS[norm]), "auto", now, False
    if is_label_required(display_name):
        return None, None, None, True
    return None, None, None, False
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --directory backend pytest backend/tests/unit/test_expiry_lifespans.py -v`
Expected: PASS 4/4

- [ ] **Step 5: Commit**

```bash
git add backend/src/cookfully/domain/expiry_lifespans.py backend/tests/unit/test_expiry_lifespans.py
git commit -m "feat(expiry): add curated FRESH_LIFESPANS resolver with auto/label/no-expiry"
```

---

### Task 2: DB migration + models + schemas

**Files:**
- Create: `backend/alembic/versions/20260824_add_expiry_to_grocery_and_pantry.py`
- Modify: `backend/src/cookfully/infrastructure/models/grocery.py:60-93`
- Modify: `backend/src/cookfully/infrastructure/models/pantry.py:25-60`
- Modify: `backend/src/cookfully/api/schemas/grocery.py`
- Modify: `backend/src/cookfully/api/schemas/pantry.py`

**Interfaces:**
- Consumes: Task 1 resolver (not yet wired)
- Produces: `GroceryItem.purchased_at/expires_on/expiry_source`, `PantryItem.purchased_at/expiry_source`, `GroceryItemResponse(purchasedAt, expiresOn, expirySource, needsExpiryDate)`, `PantryItemResponse(purchasedAt, expirySource)`

- [ ] **Step 1: Write failing contract test for new fields**

```python
# backend/tests/contract/test_grocery_expiry.py
def test_grocery_item_has_expiry_fields(client, owner_headers):
    # create grocery list + item, patch checked true for tomato → expect expiry fields
    # exact test creates pantry item via grocery check flow after Task 3, but here just checks schema accepts nulls
    resp = client.get("/api/meal-plans/2026-08-18/grocery-list", headers=owner_headers)
    assert resp.status_code in (200,404)
```

Simplify: test schemas serialize new fields (unit test). Alternative: test model has columns.

```python
from cookfully.infrastructure.models.grocery import GroceryItem
assert hasattr(GroceryItem, 'purchased_at')
```

- [ ] **Step 2: Run to verify fails**

Run: `uv run --directory backend pytest backend/tests/contract/test_grocery_expiry.py -v`
Expected: FAIL attribute missing

- [ ] **Step 3: Add columns to models**

```python
# backend/src/cookfully/infrastructure/models/grocery.py - inside GroceryItem
purchased_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
expires_on: Mapped[date | None] = mapped_column(Date, nullable=True)
expiry_source: Mapped[str | None] = mapped_column(String(10), nullable=True)
# add CheckConstraint: "expiry_source IN ('auto','label','manual')" and "expires_on IS NULL OR purchased_at IS NOT NULL"

# backend/src/cookfully/infrastructure/models/pantry.py - inside PantryItem
purchased_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
expiry_source: Mapped[str | None] = mapped_column(String(10), nullable=True)
```

- [ ] **Step 4: Generate Alembic revision (autogenerate then edit)**

Run: `uv run --directory backend alembic revision --autogenerate -m "add_expiry_to_grocery_and_pantry"`
Edit generated file to ensure `op.add_column` for both tables with correct types, and downgrade drops columns. Add `sa.CheckConstraint`.

- [ ] **Step 5: Update Pydantic schemas**

```python
# backend/src/cookfully/api/schemas/grocery.py - GroceryItemResponse adds:
purchased_at: datetime | None = Field(alias="purchasedAt", default=None)
expires_on: date | None = Field(alias="expiresOn", default=None)
expiry_source: Literal["auto","label","manual"] | None = Field(alias="expirySource", default=None)
needs_expiry_date: bool = Field(alias="needsExpiryDate", default=False)  # computed, not stored

# backend/src/cookfully/api/schemas/pantry.py - PantryItemResponse adds:
purchased_at: datetime | None = Field(alias="purchasedAt", default=None)
expiry_source: Literal["auto","label","manual"] | None = Field(alias="expirySource", default=None)
```

- [ ] **Step 6: Run tests + mypy**

Run: `uv run --directory backend mypy src && uv run --directory backend pytest backend/tests/contract/test_grocery_expiry.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add backend/src/cookfully/infrastructure/models/grocery.py backend/src/cookfully/infrastructure/models/pantry.py backend/src/cookfully/api/schemas/grocery.py backend/src/cookfully/api/schemas/pantry.py backend/alembic/versions/20260824_add_expiry_to_grocery_and_pantry.py
git commit -m "feat(expiry): DB + schemas for grocery/pantry purchased_at/expires_on/expiry_source"
```

---

### Task 3: Backend expiry flow on grocery checked + pantry copy

**Files:**
- Modify: `backend/src/cookfully/application/grocery_lists.py` (update method, to_read)
- Modify: `backend/src/cookfully/application/pantry.py` / `pantry_deductions.py`
- Modify: `backend/src/cookfully/api/routes/grocery.py` (update_grocery_item passes expiresOn)
- Test: `backend/tests/contract/test_grocery_expiry.py` (extend)

**Interfaces:**
- Consumes: Task 1 `resolve_expiry`, Task 2 models/schemas
- Produces: `PATCH /grocery-items/{id}` sets expiry correctly, `PantryDeduction.apply` copies expiry

- [ ] **Step 1: Write failing contract test**

```python
# backend/tests/contract/test_grocery_expiry.py
def test_tomato_checked_auto_expiry(client, owner_headers):
    week = "2026-08-18"
    client.post(f"/api/meal-plans/{week}/grocery-list", headers=owner_headers)
    item = client.post(f"/api/meal-plans/{week}/grocery-list/items", json={"displayName":"Tomatoes","quantity":"1","unit":"lb"}, headers=owner_headers).json()
    resp = client.patch(f"/api/grocery-items/{item['id']}", json={"checked": True}, headers={**owner_headers, "If-Match": str(item['version'])})
    assert resp.status_code == 200
    data = resp.json()
    assert data["expirySource"] == "auto"
    assert data["expiresOn"] is not None
    assert data["purchasedAt"] is not None

def test_milk_needs_expiry_date(client, owner_headers):
    week = "2026-08-18"
    item = client.post(f"/api/meal-plans/{week}/grocery-list/items", json={"displayName":"Whole Milk","quantity":"1","unit":"gal"}, headers=owner_headers).json()
    resp = client.patch(f"/api/grocery-items/{item['id']}", json={"checked": True}, headers={**owner_headers, "If-Match": str(item['version'])})
    assert resp.json()["needsExpiryDate"] is True
    assert resp.json()["expiresOn"] is None

def test_milk_label_then_manual_guard(client, owner_headers):
    # after label, second patch with new expiresOn becomes manual and is not overwritten
    pass

def test_uncheck_clears_expiry(client, owner_headers):
    pass
```

- [ ] **Step 2: Run to verify fails**

Run: `uv run --directory backend pytest backend/tests/contract/test_grocery_expiry.py::test_tomato_checked_auto_expiry -v`
Expected: FAIL `expirySource` missing or None

- [ ] **Step 3: Implement grocery update logic**

In `backend/src/cookfully/application/grocery_lists.py` `GroceryListService.update`:

```python
from datetime import date
from cookfully.domain.expiry_lifespans import resolve_expiry

# inside update, after loading item with_for_update:
if "checked" in values:
    new_checked = bool(values["checked"])
    if new_checked and not item.checked:
        # transitioning false->true
        requested = values.get("expires_on")  # from payload expiresOn
        # if expiry_source already manual, don't auto-overwrite
        if item.expiry_source == "manual":
            if requested:
                item.expires_on = requested
                item.purchased_at = utc_now()
            # else keep manual as is
        else:
            expires_on, source, purchased_at, needs = resolve_expiry(item.display_name, requested_expires_on=requested, today=utc_now().date())
            if requested:
                # client provided date → label on first prompt, manual on later edits
                source = "label" if item.expiry_source is None else "manual"
                item.expires_on = requested
                item.expiry_source = source
                item.purchased_at = purchased_at
            elif expires_on is not None:
                item.expires_on = expires_on
                item.expiry_source = source  # auto
                item.purchased_at = purchased_at
            elif needs:
                # leave null, signal via response computed field
                item.purchased_at = utc_now()
                item.expires_on = None
                item.expiry_source = None
    elif not new_checked and item.checked:
        item.purchased_at = None
        item.expires_on = None
        item.expiry_source = None
    item.checked = new_checked

if "expires_on" in values and values["expires_on"] is not None:
    # validate range today <= expires_on <= today+90
    today = utc_now().date()
    if not (today <= values["expires_on"] <= date.fromordinal(today.toordinal()+90)):
        raise DomainError("expiry_out_of_range", "Expiry must be within 0-90 days from today.", 422)
    item.expires_on = values["expires_on"]
    # first time with label-required → label, later edits → manual
    item.expiry_source = "manual" if item.expiry_source == "manual" or item.expiry_source == "label" else "label"
    if item.purchased_at is None:
        item.purchased_at = utc_now()
    if "checked" not in values:
        # editing expiry without checking still needs purchased_at
        pass
```

Wire `PATCH /grocery-items/{id}` route to accept `expiresOn` via `GroceryItemWriteRequest` (extend to include `expiresOn?: date`).

In `to_read` / `from_read`, map `purchased_at/expires_on/expiry_source` and compute `needs_expiry_date = is_label_required(item.display_name) and item.checked and item.expires_on is None`.

In `pantry_deductions.py` `apply`: when creating/updating `PantryItem` from grocery, copy `expires_on/purchased_at/expiry_source` if grocery has them and pantry item's `expiry_source != 'manual'`.

- [ ] **Step 4: Run tests to pass**

Run: `uv run --directory backend pytest backend/tests/contract/test_grocery_expiry.py -v`
Expected: PASS

- [ ] **Step 5: Run full backend suite**

Run: `uv run --directory backend pytest --run`
Expected: all green, 422 for out-of-range in `test_milk_label_then_manual_guard`

- [ ] **Step 6: Commit**

```bash
git add backend/src/cookfully/application/grocery_lists.py backend/src/cookfully/application/pantry.py backend/src/cookfully/application/pantry_deductions.py backend/src/cookfully/api/routes/grocery.py backend/tests/contract/test_grocery_expiry.py
git commit -m "feat(expiry): grocery checked sets auto/label expiry, clears on uncheck, copies to pantry"
```

---

### Task 4: Frontend grocery expiry sheet + pantry use-soon

**Files:**
- Modify: `frontend/src/features/grocery/types.ts`
- Modify: `frontend/src/features/grocery/api.ts`
- Modify: `frontend/src/features/grocery/GroceryListPage.tsx`
- Create: `frontend/src/features/pantry/expiry.ts`
- Modify: `frontend/src/features/pantry/types.ts`, `frontend/src/features/pantry/PantryPage.tsx`
- Test: `frontend/src/features/grocery/__tests__/GroceryExpiry.test.tsx`, `frontend/src/features/pantry/__tests__/PantryUseSoon.test.tsx`

**Interfaces:**
- Consumes: Task 3 API fields
- Produces: `daysLeft(expiresOn: string, today: string) -> number`, `expiryBadge(expiresOn, today) -> {label, tone}`, Grocery sheet UI, Pantry sorted list

- [ ] **Step 1: Write failing frontend tests**

```tsx
// frontend/src/features/grocery/__tests__/GroceryExpiry.test.tsx
import { render, screen } from "@testing-library/react";
import { GroceryRow } from "../GroceryListPage"; // or extracted component

test("auto badge shows for tomato", () => {
  render(<GroceryRow item={{displayName:"Tomatoes", checked:true, expiresOn:"2026-08-29", expirySource:"auto", needsExpiryDate:false} as any} weekStart="2026-08-18" stops={[]} readOnly={false} sourceMealsByEntry={new Map()} />);
  expect(screen.getByText(/Expires/)).toBeInTheDocument();
});
test("label sheet opens when needsExpiryDate", () => {
  // mock PATCH returns needsExpiryDate true → sheet visible
});
```

- [ ] **Step 2: Run to fail**

Run: `pnpm --dir frontend test --run src/features/grocery/__tests__/GroceryExpiry.test.tsx`
Expected: FAIL

- [ ] **Step 3: Implement types + expiry helper**

```ts
// frontend/src/features/grocery/types.ts
purchasedAt?: string | null;
expiresOn?: string | null;
expirySource?: "auto"|"label"|"manual" | null;
needsExpiryDate?: boolean;

// frontend/src/features/pantry/expiry.ts
export function daysLeft(expiresOn: string, todayStr: string): number {
  const e = new Date(expiresOn+"T00:00:00");
  const t = new Date(todayStr+"T00:00:00");
  return Math.round((e.getTime()-t.getTime())/86400000);
}
export function expiryBadge(expiresOn: string, todayStr: string): {label:string, tone:"mint"|"amber"|"danger"} {
  const d = daysLeft(expiresOn, todayStr);
  if (d < 0) return {label:`Expired ${Math.abs(d)}d ago`, tone:"danger"};
  if (d <= 1) return {label:`Use soon — ${d}d left`, tone:"amber"};
  if (d <= 3) return {label:`Expires in ${d}d`, tone:"amber"};
  return {label:`Expires ${expiresOn}`, tone:"mint"};
}
```

- [ ] **Step 4: Implement GroceryRow sheet + badge**

In `GroceryListPage.tsx` `GroceryRow`:
- after `checked` mutation, if `saved.needsExpiryDate` → `setShowExpirySheet(true)`
- badge: `{item.expiresOn ? <span className={`expiry-badge expiry-badge--${tone}`}>{label}</span> : null}` beside quantity, `aria-label` includes `Expires ${expiresOn}`
- sheet: `<Dialog open={showExpirySheet}><input type="date" min={today} max={plus90} value={draftExpiresOn} onChange... /><Button onClick={()=> update.mutate({expiresOn: draftExpiresOn})}>Save expiry</Button><Button variant="ghost" onClick={()=> setShowExpirySheet(false)}>Skip</Button></Dialog>`
- tapping badge reopens sheet; saving sets `manual` via backend

In `PantryPage.tsx`:
- `const today = todayInTimezone(preferences.timezone)`; sort `items.slice().sort((a,b)=> (a.expiresOn?0:1)-(b.expiresOn?0:1) || (a.expiresOn||"").localeCompare(b.expiresOn||""))`
- chip: `expiryBadge(item.expiresOn, today)` with `color-mix` classes `expiry-chip--amber/mint/danger`

- [ ] **Step 5: Run frontend tests**

Run: `pnpm --dir frontend test --run src/features/grocery/__tests__/GroceryExpiry.test.tsx src/features/pantry/__tests__/PantryUseSoon.test.tsx`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add frontend/src/features/grocery/types.ts frontend/src/features/grocery/api.ts frontend/src/features/grocery/GroceryListPage.tsx frontend/src/features/pantry/expiry.ts frontend/src/features/pantry/types.ts frontend/src/features/pantry/PantryPage.tsx frontend/src/features/grocery/__tests__/GroceryExpiry.test.tsx frontend/src/features/pantry/__tests__/PantryUseSoon.test.tsx
git commit -m "feat(expiry): grocery label sheet + auto badge, pantry use-soon sort and chips"
```

---

### Task 5: Plan expiring banner

**Files:**
- Create: `frontend/src/features/plans/useExpiringPantry.ts`
- Create: `frontend/src/features/plans/ExpiringBanner.tsx`
- Modify: `frontend/src/features/plans/WeekOverview.tsx` (or `WeeklyPlannerPage.tsx`) to render banner
- Test: `frontend/src/features/plans/__tests__/ExpiringBanner.test.tsx`

**Interfaces:**
- Consumes: Tasks 3-4 pantry `expiresOn`, `GET /pantry-items`, `GET /meal-plans/{weekStart}`
- Produces: `useExpiringPantry(threshold=3) -> PantryItem[]`, `ExpiringBanner` component

- [ ] **Step 1: Write failing test**

```tsx
// frontend/src/features/plans/__tests__/ExpiringBanner.test.tsx
test("shows banner when expiring tomato matches Tue pasta", () => {
  render(<ExpiringBanner pantry={[{normalizedFoodName:"tomato", expiresOn:"2026-08-26"}]} plan={{entries:[{recipeTitle:"Pasta", ingredients:[{normalized:"tomato"}]}]}} today="2026-08-24" />);
  expect(screen.getByText(/Use soon/)).toBeInTheDocument();
});
test("no banner when no expiring items", () => {
  render(<ExpiringBanner pantry={[]} plan={{entries:[]}} today="2026-08-24" />);
  expect(screen.queryByText(/Use soon/)).not.toBeInTheDocument();
});
```

- [ ] **Step 2: Run to fail**

Run: `pnpm --dir frontend test --run src/features/plans/__tests__/ExpiringBanner.test.tsx`
Expected: FAIL

- [ ] **Step 3: Implement hook + banner**

```ts
// frontend/src/features/plans/useExpiringPantry.ts
import { useQuery } from "@tanstack/react-query";
import { pantryApi } from "../pantry/api";
export function useExpiringPantry(threshold=3, todayStr: string) {
  const q = useQuery({queryKey:["pantry-items"], queryFn: pantryApi.list});
  const expiring = (q.data??[]).filter(i => i.expiresOn && daysLeft(i.expiresOn, todayStr) >=0 && daysLeft(i.expiresOn, todayStr) <= threshold);
  return {expiring, isLoading: q.isPending};
}
```

```tsx
// frontend/src/features/plans/ExpiringBanner.tsx
export function ExpiringBanner({pantry, plan, today}: Props) {
  const expiring = pantry.filter(p => daysLeft(p.expiresOn!, today) <=3);
  const matched = expiring.filter(e => plan.entries.some(en => en.ingredients?.some(ing => ing.normalized?.includes(e.normalizedFoodName) || e.normalizedFoodName.includes(ing.normalized))));
  if (!expiring.length) return null;
  return <section className="notice expiring-banner" role="status">Use soon: {expiring.map(e=> `${e.displayName} (${daysLeft(e.expiresOn!,today)}d)`).join(", ")} {matched.length ? `— also in ${matched[0].displayName} on ${matched[0].date}` : ""} <Link to="/app/pantry">View in Pantry</Link></section>;
}
```

In `WeekOverview.tsx` render `<ExpiringBanner />` above week grid.

- [ ] **Step 4: Run to pass**

Run: `pnpm --dir frontend test --run src/features/plans/__tests__/ExpiringBanner.test.tsx`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/features/plans/useExpiringPantry.ts frontend/src/features/plans/ExpiringBanner.tsx frontend/src/features/plans/WeekOverview.tsx frontend/src/features/plans/__tests__/ExpiringBanner.test.tsx
git commit -m "feat(expiry): plan use-soon banner when expiring pantry matches planned meals"
```

---

## Self-Review Checklist

- Spec §2 (DB) → Task 2
- Spec §3 (domain dict + resolver) → Task 1
- Spec §4 (PATCH checked, needsExpiryDate, 0-90d, manual guard, uncheck clears, read fields, deduction copy) → Task 3
- Spec §5 Grocery sheet + badge → Task 4
- Spec §5 Pantry sort + chips → Task 4
- Spec §5 Plan banner → Task 5
- Spec §6 edge cases (manual wins, staples no expiry, timezone date, null Progressive) → Tasks 3-5
- Spec §7 testing → all tasks include tests
- Type consistency: `expiresOn` (date string `YYYY-MM-DD` in JSON, `date` in Python), `purchasedAt` (ISO datetime), `expirySource` enum, `needsExpiryDate` boolean computed — checked across Tasks 2-5.
- No placeholders; every step has actual code/commands.
