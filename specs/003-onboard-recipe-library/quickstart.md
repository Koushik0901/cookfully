# Quickstart: A calmer first kitchen

## Prerequisites

- A running Cookfully API, worker, database, and media volume using the existing local development setup.
- One authenticated owner account.
- At least one recipe and one weekly plan fixture for grocery verification; also verify the zero-recipe state for first run.

## Manual acceptance journey

1. Sign in as an owner with no recipe and no resolved onboarding state. Confirm the first-run surface gives three concise actions and does not request health metrics.
2. Choose **Create recipe**. Enter a title, yield, ingredients, and method; select a JPEG, PNG, or WebP photo. Confirm the local preview is removable before saving.
3. Save the recipe. Confirm the photo appears on its detail, library card, plan picker, suggestion result, and Cook Mode; replace and remove it without changing the displayed nutrition, ingredients, or instructions.
4. Mark the recipe favorite, add it to two collections, and choose Dinner. Confirm that all organization is optional and that each library filter is focused and removable.
5. Add the recipe to this week's plan and generate groceries. Create two shopping stops; assign items, opting to remember one safe generated item. Refresh after changing the plan and confirm manual items, checked items, stop assignment, and ingredient sources survive.
6. Check every item, finish the shopping pass, and confirm the week is retained as completed. Attempt a refresh and verify Cookfully asks for an explicit reopen first. Reopen only if further shopping is needed.
7. Export owner data with media. Verify that the photo and new records are present. Exercise full-owner erasure in its existing isolated test process and verify no new table or media row survives.

## Required automated evidence

Run the appropriate affected checks before merge:

```powershell
uv run --directory backend ruff format --check .
uv run --directory backend ruff check .
uv run --directory backend mypy src
uv run --directory backend pytest
pnpm --dir frontend lint
pnpm --dir frontend typecheck
pnpm --dir frontend test --run
pnpm --dir frontend build
pnpm --dir frontend exec playwright test
```

Add contract, integration, and end-to-end coverage for onboarding resolution, photo validation/replacement/removal, collection/role filters, grocery-stop conflict/reconciliation, complete/reopen behavior, export, and erasure. Regenerate the OpenAPI document and frontend schema after finalizing route schemas, then verify no generated diff remains.
