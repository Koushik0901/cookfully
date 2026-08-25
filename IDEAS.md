# IDEAS.md — Reconstructed 2026-08-23

> **Note:** Original file was never tracked in git (`git log --all --name-only` shows no `IDEAS.md` ever) and no copy remains on disk, in `Code/Backups`, dangling blobs, or Recycle Bin. This draft is reconstructed 2026-08-23 from `docs/inspiration-review.md`, `docs/superpowers/specs/*`, `AGENTS.md` recent changes, and `critique-UI.md` / `DESIGN.md` to give you an editable starting point. Review and prune.

## How to use
- Keep this as a private scratchpad — do not treat items here as committed scope.
- Promote an idea to a real spec via `speckit.specify` only when persona test passes: "Does this help someone plan, cook, and eat better food with less friction?"
- Record Mealie/Tandoor/Immich comparisons in `docs/inspiration-review.md` before adopting.

---

## 1. Nutrition & ingredient intelligence (follow-ups to P1–P3)
- [ ] **Generic unit conversions** — Tandoor-style `UnitConversion(food=null)` for pinch/dash/clove/bunch. Deferred: currently solved via `owner_foods.typical_serving_g` (see `inspiration-review.md: Non-standard unit handling`). Revisit if volume demands.
- [x] **Package/branded quantities** — `food_references.serving_size_g` + `serving_unit` + `GYM_BRANDED_CATEGORIES` gated USDA branded import done (`backend/src/cookfully/infrastructure/models/reference_foods.py`).
- [ ] **Barcode scan** — extend to barcode scan with verified package weight before enabling auto-pantry deduction. *Not started.*
- [x] **Density-aware volume bridging** — `volume_assumptions.py:7` conservative densities (`DEFAULT 0.7`, honey 1.4, oil 0.91, cooked/raw rice) done; per-food density table deferred until vetted source.
- [ ] **Owner food frequency prior** — if staple subset emerges, add per-owner popularity prior to disambiguate banana vs banana powder ties (revisit `inspiration-review.md: Ingredient→food matching`).
- [x] **Atwater energy fallback** — SR Legacy codes 203/204/205/208 + Atwater synthesis when energy missing done (`AGENTS.md: Nutrition pipeline fix`, `backend/src/cookfully/domain/nutrition.py`). Audit log when synthesized vs USDA-provided remains todo.

## 2. Needle2 — inline repair evolution (current: hidden gap-only 600ms parallel race)
- [x] **Inline Repair Gateway** — `InlineRepairGateway` gap-only merge, never overwrite, `confidence is None` fail-closed (`backend/src/cookfully/application/inline_repair.py`).
- [x] **Import preview parallel** — `SafeFetcher` HTML + tok-aware `_window` (~100 tok heuristic, second window if has_more + budget>120ms).
- [x] **Bulk pantry** — `BulkPantryCreateResponse {items, created}` union (`POST /pantry-items`).
- [x] **CmdK inline preview** — `We think you mean — Add?` at 0.80 (preview B).
- [x] **Cook voice-ready** — `cooking_action` Literal + `transcript=prompt` basics + confident `how much X?`.
- [x] **Threshold sweep `--real`** — `scripts/needle_threshold_sweep.py --real` probes real Needle when `/models/needle2.cact` present else synthetic fallback; `artifacts/needle-threshold-report.json` (`chosen 0.75`, `p95 31ms`) done. Hardware run to re-verify before 100% already done in prod promotion.
- [ ] **Heuristic tok→real tokenizer** — replace `tiktoken` try / `//4` fallback with Needle's own tok count once exposed.
- [ ] **LoRA per-owner correction** — deferred; evaluate only if inline+bulk still leaves >1% false_overwrite.

## 3. Planner & grocery
- [x] **Three-view planner polish** — Week (`WeekOverview.tsx`) / Day (`DayMealBoard.tsx`/`DayTabs.tsx`) / Prep (`PrepOverview.tsx`) done (`inspiration-review.md: Food-first weekly planning`).
- [x] **Direct-manipulation dnd-kit** — `@dnd-kit/react 0.5` in `frontend/package.json` done; pointer + keyboard drag with Move dialog fallback + AT announce (see `inspiration-review.md: kitchen-first shell`). Polish “use soon” nudge into Plan placement remains todo.
- [x] **Shopping stops memory** — `grocery_shopping_stops.py` + `remembered placements` done (`specs/003-onboard-recipe-library`).
- [ ] **Pantry expiry** — do not invent “use soon” urgency until pantry-expiry domain model exists; then wire to `Use soon` mint surface.

## 4. Recipe library & discovery
- [x] **Cookbooks / collections** — owner-named many-to-many collections + favorites (`RecipeCollectionManager.tsx`) + 4 meal roles done; arbitrary tags/cuisine/diet/occasion taxonomies deferred until domain model supports them.
- [ ] **Search facets** — keep Immich-like advanced facets contextual to search, not permanent global form.
- [ ] **Recipe order: cuisine/time/diet filters** — only after metadata exists and can be trusted (`inspiration-review.md: Food-first weekly planning`).
- [x] **Source URL dedup merge** — `POST /recipes/import/merge` stale-version guarded done (`AGENTS.md: Import merge + editor preview`; `backend/src/cookfully/api/routes/recipes.py:import/merge`).
- [x] **Editor preview** — `RecipeDraftPreview` Edit/Preview toggle done.
- [x] **PDF thumbnails** — selected PDF thumbnail persists via `PUT /recipes/{id}/photo/attach` (`imageSourceKind: pdf_thumbnail`) done.

## 5. App shell & quality
- [x] **112px labelled strip** — desktop/tablet prototype adopted (`frontend/src/styles/shell.css`, `frontend/src/app/App.tsx`) done (`critique-UI.md`); 390x844 / keyboard / overflow / loading/empty/partial/estimated/manual/stale/failed states verified per `DESIGN.md`.
- [x] **Command palette** — navigation + recipe lookup + kitchen actions done (`frontend/src/app/CommandPalette.tsx`, `frontend/src/features/intelligence/api.ts:CommandPalette.infer`); natural-language planning deferred.
- [x] **05-media hardening** — `deploy/compose.production.yaml:12-19` `read_only/tmpfs /tmp` + `intelligence-model-data:/models` + `no-new-privileges` + `intelligence-net internal:true` done (prod promoted `c3ae251`).
- [x] **Perf benchmark** — 10k recipes / 50 plan entries on 4vCPU/8GiB done (`artifacts/performance-report.json` + `docs/performance.md`).
- [x] **Import preview + thumbnail framing** — human-readable stage progress, provenance/collection context, focal-point/zoom metadata done (`AGENTS.md: Instant recipe feedback`).
- [x] **Owner foods + branded import** — `owner_foods` CRUD + lexical priority over USDA, `/app/foods` library done.
- [x] **Cook mode + portion scaling** — full-screen `/app/recipes/:id/cook` wake-lock + serving adjustment with macro recalc done.

## 6. New requests — 2026-08-23 (user added) — shipped 2026-08-23 via PR #8 `f5d6beb`
- [x] **Grocery item icons — replace generic C/B initials** — 9 SVGs traced from `frontend/public/media/grocery-icons/Screenshot*.png` → `produce/dairy/bakery/meat/pantry/frozen/beverage/household/other.svg` (`viewBox 0 0 24`, `currentColor`, svgo), `GroceryIcon.tsx` keyword map (`frozen` before `dairy`, `oats?|oatmeal`), `GroceryListPage.tsx:67` `2.5rem` token tile `color-mix primary-container`, `aria-hidden`, fallback `other`. Fix: imports hoisted, `ComponentType<SVGProps>`, `767.98px` dead-zone, `grocery-item__content` class. Done `442c8e6`+`75011d2`+`35300b4`.
- [x] **Recipes mobile 1-per-row** — `frontend/src/styles/redesign.css:322-327` + `features.css:625-630` `max-width:767.98px → 1fr` / `min-width:768px → repeat(2,1fr)`, gap `1rem`/`1.75rem`, desktop unchanged. Card `4:3` + fallback art scales, `RecipeMetadata` wraps, `responsive.spec.ts` 390×844 1-col / 1024 2-col (no `waitForTimeout`). Done `25911be`+`8b092fc`.
- [x] **Logo sync (tweak 3)** — rail new mark `cookfully-mark.svg` (555×565, `2410e53`) already via `BrandMark` `src="/brand/cookfully-mark.svg"` (`App.tsx:196/219`, `providers.tsx:21/40`, `GlobalErrorBoundary:25`); `BrandMark.test.tsx` + PIL verify PNGs 180/192/512/maskable 32/48 correct, no regeneration needed (conditional per spec). Done `7af2b48`.

## 7. Deferred / rejected (revisit only with evidence)
- Remote ML server list / arbitrary code exec for models — rejected (`inspiration-review.md: Installation-level model settings`).
- Generic rainbow macro dashboard on Home — rejected; macros stay as tinted chips with basis/coverage disclosure.
- Multi-user quotas / admin panel — rejected for single-owner; only Account/Security/API-access Settings kept.

---

## Sources that fed this reconstruction
- `docs/inspiration-review.md` — all P5/P6/P9/P10 + first-run + ingredient→food + stale-nutrition + pantry matching sections
- `docs/superpowers/specs/2026-08-23-needle2-inline-repair-design.md` + `2026-08-24-*` + `docs/superpowers/plans/*`
- `AGENTS.md` Recent Changes (import merge + editor preview + PDF thumbs; instant feedback; food matching v2; nutrition pipeline; owner foods; branded import; cook mode + portion scaling; sessions)
- `critique-UI.md` Home reference + `DESIGN.md` tokens
- `deploy/compose.production.yaml`, `deploy/.env.example`, `scripts/needle_threshold_sweep.py`, `artifacts/needle-threshold-report.json`
