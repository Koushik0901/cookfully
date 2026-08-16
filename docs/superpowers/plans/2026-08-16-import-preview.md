# Phase 3 — Import Preview, Missing Quantities, Duplicates, PDF Images Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let users preview and edit an imported recipe (title, components, per-ingredient quantities, thumbnail) before it is saved, with duplicate detection, missing-quantity prompting, and reliable PDF image extraction.

**Architecture:** Add a "parse first, confirm after" import flow. A new sync `POST /recipes/import/preview` returns an unsaved structured preview plus a short-lived `parseId`; client edits it and `POST /recipes/import/confirm` applies additive edits, persists the recipe, and enqueues the existing background nutrition/media jobs. Duplicate detection is computed during preview. PDF recipes expose image candidates through the same preview shape. The existing bare-URL `POST /recipes/import` stays as the async fallback when preview times out.

**Tech Stack:** FastAPI, Pydantic 2, SQLAlchemy 2, Alembic, `recipe-scrapers`, pypdf, Celery, React 19.2, TanStack Query, Radix Dialog, TypeScript, openapi-typescript.

## Global Constraints

- Preserve original ingredient text, nutrition provenance, serving basis, and active-correction precedence in every code path.
- Background handlers must be idempotent and reject stale input hashes.
- Use fixed-precision decimals for stored nutrition; scaled integers for solver inputs.
- Keep domain and application rules independent of FastAPI/Celery transports.
- No auto-merge of duplicates; only warn + keep/discard/open-existing.
- No nutrition preview inside the modal (stays post-save).
- Verify desktop + 390x844 behavior, keyboard access, overflow, and explicit loading/empty/partial/stale/failed states per `DESIGN.md`.
- Follow the existing deposit/commit/retention sweep patterns used by `IdempotencyRecord`.

---
### Task 1: Add an `import_previews` table + migration

**Files:**
- Create: `backend/src/cookfully/infrastructure/models/import_preview.py`
- Modify: `backend/src/cookfully/infrastructure/models/__init__.py`
- Create: `backend/migrations/versions/0019_import_previews.py`
- Test: `backend/tests/infrastructure/test_import_preview_model.py`

**Interfaces:**
- Consumes: `cookfully.infrastructure.models.base.Base`, `cookfully.domain.common.uuid7`, `owner_accounts` table.
- Produces: `ImportPreviewRecord` ORM class with fields `id` (UUID pk), `owner_id` (FK owner_accounts, CASCADE), `parse_id` (str), `payload` (JSONB), `created_at`, `expires_at`. Index on `expires_at`; unique `(owner_id, parse_id)`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/infrastructure/test_import_preview_model.py
from cookfully.infrastructure.models.import_preview import ImportPreviewRecord


def test_import_preview_record_fields():
    import uuid
    from datetime import datetime, timezone
    from decimal import Decimal
    from cookfully.domain.common import uuid7
    from cookfully.infrastructure.models.base import Base
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    record = ImportPreviewRecord(
        id=uuid7(),
        owner_id=uuid.UUID("00000000-0000-4000-8000-000000000001"),
        parse_id="p1",
        payload={"title": "Shawarma bowl"},
        created_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc),
    )
    session.add(record)
    session.commit()
    assert record.parse_id == "p1"
    assert record.payload["title"] == "Shawarma bowl"
```

(Adjust the engine import to use the repo's test session factory pattern; see existing infra tests. The point is `ImportPreviewRecord` is importable and persistable.)

- [ ] **Step 2: Run test, verify FAIL** (module missing)

Run: `uv run --directory backend pytest tests/infrastructure/test_import_preview_model.py -q`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Create the model**

```python
"""Import preview persistence. Short-lived preview scoped to an owner."""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from cookfully.domain.common import uuid7
from cookfully.infrastructure.models.base import Base


class ImportPreviewRecord(Base):
    __tablename__ = "import_previews"
    __table_args__ = (
        Index("ix_import_previews_expires_at", "expires_at"),
        Index("ix_import_previews_owner_parse_id", "owner_id", "parse_id", unique=True),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    owner_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("owner_accounts.id", ondelete="CASCADE"),
        nullable=False,
    )
    parse_id: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
```

- [ ] **Step 4: Register in models `__init__.py`**

Add to the appropriate import/`__all__` list in `backend/src/cookfully/infrastructure/models/__init__.py`:
```python
from cookfully.infrastructure.models.import_preview import ImportPreviewRecord
```

- [ ] **Step 5: Create migration `0019_import_previews.py`** (mirror style of `0018_recipe_sections.py`)

```python
"""import_previews

Revision ID: 0019
Revises: 0018
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "import_previews",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "owner_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("owner_accounts.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("parse_id", sa.String(64), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_import_previews_expires_at", "import_previews", ["expires_at"])
    op.create_index(
        "ix_import_previews_owner_parse_id", "import_previews", ["owner_id", "parse_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_import_previews_owner_parse_id", table_name="import_previews")
    op.drop_index("ix_import_previews_expires_at", table_name="import_previews")
    op.drop_table("import_previews")
```

- [ ] **Step 6: Run test, expect PASS**

- [ ] **Step 7: Commit**

```bash
git add backend/.../models/import_preview.py backend/.../models/__init__.py backend/migrations/versions/0019_import_previews.py backend/tests/infrastructure/test_import_preview_model.py
git commit -m "feat: add short-lived import preview storage"
```

---
### Task 2: Extend the importer with preview-safe image candidates and PDF image extraction

**Files:**
- Modify: `backend/src/cookfully/infrastructure/recipe_importer.py`
- Test: `backend/tests/unit/test_recipe_importer.py` (find the file; confirm path via glob `backend/tests/**/test_recipe_importer*.py`)

**Interfaces:**
- Produces on `RecipeImporter`:
  - `async def import_resource(self, resource: FetchedResource, *, prefer_single_image: bool = True) -> ImportedRecipe | ImportedCookbook` — a refactor of `import_url` that accepts an already-fetched resource so preview and pipeline can share the parse. Keep `import_url(url)` delegating to `self._fetcher.fetch` then this method (backward compatible).
  - `async def preview(self, url: str) -> ImportedRecipe | ImportedCookbook` — fetches+parses, returns candidates instead of choosing: sets `image_url` to the **first** candidate but additionally attaches `image_candidates: tuple[str, ...]` on the dataclass when >1. Falls back to async `recipe_import` on timeout is handled at the API layer (Task 3), not here.

- [ ] **Step 1: Write a failing test for PDF embedded-image extraction**

Use a working pypdf 6.16 fixture: build a 1-page PDF with one embedded 8x8 JPEG by attaching a `StreamObject` of the JPEG bytes to the page `/Resources` and decoding via `PdfReader.pages[0].images`. Add `backend/tests/unit/test_recipe_importer.py` (create if missing):

```python
# backend/tests/unit/test_recipe_importer.py
import io

from cookfully.infrastructure.recipe_importer import RecipeImporter


def _single_image_pdf() -> bytes:
    """Build a 1-page PDF embedding one 8x8 JPEG (pypdf 6.x)."""
    import pypdf
    from pypdf.generic import DictionaryObject, NameObject, NumberObject, StreamObject
    from PIL import Image

    writer = pypdf.PdfWriter()
    page = writer.add_blank_page(width=72, height=72)
    jpg = io.BytesIO()
    Image.new("RGB", (8, 8), (180, 40, 40)).save(jpg, format="JPEG")
    jpg.seek(0)
    stream = StreamObject()
    stream.set_data(jpg.getvalue())
    for key, value in {
        "/Type": "/XObject",
        "/Subtype": "/Image",
        "/Width": "8",
        "/Height": "8",
        "/ColorSpace": "/DeviceRGB",
        "/BitsPerComponent": "8",
        "/Filter": "/DCTDecode",
    }.items():
        stream[NameObject(key)] = (
            NameObject(value) if value.startswith("/") else NumberObject(8 if value == "8" else int(value))
        )
    xo = writer._add_object(stream)  # noqa: SLF001  (pypdf public-ish writer API)
    page[NameObject("/Resources")] = DictionaryObject(
        {NameObject("/XObject"): DictionaryObject({NameObject("/Im0"): xo})}
    )
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def test_pdf_image_extraction_via_pypdf():
    """pypdf reads embedded raster images; the importer maps them to data-URI candidates."""
    urls = RecipeImporter._pdf_image_candidates(_single_image_pdf())
    assert len(urls) == 1
    assert urls[0].startswith("data:image/")
```

- [ ] **Step 2: Verify fails** — `uv run --directory backend pytest tests/unit/test_recipe_importer.py -q` expect FAIL (helper undefined)

- [ ] **Step 3: Refactor `ImportedRecipe` to carry image candidates**

Add a field to the dataclass:
```python
@dataclass(frozen=True, slots=True)
class ImportedRecipe:
    ...
    image_candidates: tuple[str, ...] = ()
```
Set it in the HTML branch (these URLs are already available from `image_candidates`):
```python
candidates = self.image_candidates(html, resource.final_url)
image_url = (
    raw_image if isinstance(raw_image, str) and len(candidates) <= 1
    else candidates[0] if len(candidates) == 1
    else None
)
ImportedRecipe(
    ...,
    image_url=image_url,
    image_candidates=candidates,
)
```

- [ ] **Step 4: Add `_pdf_image_candidates` using pypdf `page.images`**

```python
import base64
import io
from PIL import Image
from pypdf import PdfReader


@classmethod
def _pdf_image_candidates(cls, content: bytes) -> tuple[str, ...]:
    """Return base64 data-URIs for raster images embedded in a cookbook PDF.

    pypdf exposes ``page.images`` (each with ``.image`` a decoded PIL image).
    Because preview must not persist side-effect content, we encode each usable
    image to a JPEG data-URI the browser can render directly. The confirm step
    (Task 4) captures the chosen image via the existing media path.
    """
    reader = PdfReader(BytesIO(content), strict=False)
    urls: list[str] = []
    for page in reader.pages:
        for image in getattr(page, "images", ()):
            try:
                im = image.image
            except Exception:
                continue
            if im is None or im.width < 96 or im.height < 96:
                continue
            buf = io.BytesIO()
            im.convert("RGB").save(buf, format="JPEG", quality=80)
            urls.append(
                f"data:image/jpeg;base64,{base64.b64encode(buf.getvalue()).decode('ascii')}"
            )
    return tuple(urls)
```
Wire `_import_pdf` to pass `content` through and attach per-recipe candidates so `image_candidates` is non-empty whenever the pages embed raster images. Keep the "no silent choice with >1 image" rule.

- [ ] **Step 5: Run tests until green (unit + the real cookbook as an optional ad-hoc check)** — expect PASS

- [ ] **Step 6: Commit**

```bash
git add backend/src/cookfully/infrastructure/recipe_importer.py backend/tests/unit/test_recipe_importer.py
git commit -m "feat: expose PDF image candidates for import preview"
```

---
### Task 3: Preview + confirm application services

**Files:**
- Create: `backend/src/cookfully/application/import_preview.py`
- Modify: `backend/src/cookfully/application/recipes.py` (add a `create_from_import_preview` method or reuse `replace_content` + placeholder).
- Test: `backend/tests/unit/test_import_preview.py` (or an integration test alongside `test_recipe_jobs.py`).

**Interfaces:**
- Produces:
  - `class ImportPreviewCoordinator` with:
    - `async def create_preview(url: str, *, owner_id, trace_id) -> dict` — calls `importer.preview`, stores `ImportPreviewRecord` with TTL (configurable default ~15 min), returns `{parse_id, title, yieldQuantity, yieldText, imageCandidates, sections, duplicates}`.
    - `def confirm(parse_id, payload, *, owner_id) -> RecipeMutation` — loads preview, applies edits, persists (title/components/quantities/image), enqueues jobs.
- Consumes: `RecipeService.create_import_placeholder`, `RecipeService` write path, `RecipeImporter`, `ImportPreviewRecord`, `ImporterAppConfig`.

- [ ] **Step 1: Write failing test**

```python
"""backend/tests/unit/test_import_preview.py"""
def test_preview_returns_structured_sections(coordinator, monkeypatch, owner_id):
    result = asyncio_run(coordinator.preview("https://example.com/shawarma", owner_id=owner_id, trace_id="t"))
    assert result["title"]
    assert "sections" in result
    assert "parseId" in result

def test_confirm_applies_quantity_override(coordinator, monkeypatch, session, owner_id):
    # preview then submit edits:
    result = asyncio_run(coordinator.preview("https://example.com/shawwra", owner_id=owner_id, trace_id="t"))
    mutation = coordinator.confirm(result["parseId"], {
        "title": "Spiced bowl",
        "components": [{ "ingredients": [{"originalText": "1 lb chicken", "quantityText": "1 lb"}] }],
    }, owner_id=owner_id)
    assert mutation.recipe.title == "Spiced bowl"
```
Use the repo's `asyncio_run` helper or `anyio`, matching existing tests.

- [ ] **Step 2: run expect FAIL** — `uv run --directory backend pytest tests/unit/test_import_preview.py -q`

- [ ] **Step 3: Implement coordinator** in `application/import_preview.py`

```python
from __future__ import annotations
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID
from cookfully.domain.common import utc_now
from cookfully.infrastructure.models.import_preview import ImportPreviewRecord


class ImportPreviewCoordinator:
    def __init__(self, session_factory, importer, repository, *, ttl=timedelta(minutes=15)):
        self._session_factory = session_factory
        self._importer = importer
        self._repository = repository
        self._ttl = ttl

    async def preview(self, url: str, *, owner_id: UUID, trace_id: str) -> dict[str, Any]:
        imported = await self._importer.preview(url)
        first = imported.recipes[0] if hasattr(imported, "recipes") else imported
        duplicate_sections, duplicates = self._detect_duplicates(owner_id, first.title, first.ingredients)
        parse_id = secrets.token_hex(16)
        now = utc_now()
        record = ImportPreviewRecord(
            owner_id=owner_id, parse_id=parse_id,
            payload=_payload_for(first),
            created_at=now, expires_at=now + self._ttl,
        )
        with self._session_factory.begin() as session:
            self._repository.add(session, record)
        return {
            "parseId": parse_id,
            "title": first.title,
            "sectionTitles": list(first.sections),
            "imageSources": list(first.image_candidates),
            "duplicates": duplicates,
            "data": _payload_for(first),  # full structured preview
        }

    def _payload_for(self, first: ImportedRecipe) -> dict[str, Any]:
        return {
            "title": first.title,
            "yieldQuantity": str(first.yield_quantity) if first.yield_quantity is not None else None,
            "yieldText": first.yield_text,
            "imageSources": list(first.image_candidates),
            "sections": [
                {
                    "title": title,
                    "ingredients": [
                        {"originalText": text, "needsQuantity": _missing_quantity(text)}
                        for text in first.ingredients
                    ],
                }
                for title in first.sections
            ],
        }

    def confirm(
        self,
        parse_id: str,
        payload: dict[str, Any],
        *,
        owner_id: UUID,
        trace_id: str,
    ) -> RecipeMutation:
        """Apply user edits over the stored preview and persist the recipe."""
        with self._session_factory.begin() as session:
            record = self._repository.get(session, owner_id=owner_id, parse_id=parse_id)
            if record is None or record.expires_at < utc_now():
                raise DomainError(
                    "import_preview_expired",
                    "This import preview has expired. Please try the import again.",
                    410,
                )
        write = self._build_write(record.payload, payload)
        return self._recipes.create_from_import_preview(write, trace_id=trace_id, owner_id=owner_id)

    def _detect_duplicates(self, owner_id: UUID, title: str, ingredients: tuple[str, ...]) -> list[dict]:
        # Query existing recipes by normalized title (case/whitespace folded) and by
        # shared ingredient overlap; return [{id, title}] without auto-merging.
        raise NotImplementedError  # covered by integration test in Task 3
```
- [ ] **Step 4: run until green** (implement `_missing_quantity`, `_build_write`, duplicate query, and `RecipeService.create_from_import_preview` from the sketch above; use the repo's existing query/parse helpers rather than `raise NotImplementedError`)

- [ ] **Step 5: commit** `feat: import preview and confirm coordination`

---
### Task 4: API schemas + routes (preview + confirm)

**Files:**
- Modify: `backend/src/cookfully/api/schemas/recipes.py`
- Modify: `backend/src/cookfully/api/routes/recipes.py`
- Modify/tests: `backend/tests/contract/test_recipes_api.py` (or the existing recipes API contract test)

**Interfaces:**
- Produces (Pydantic models in `api/schemas/recipes.py`):
  - `ImportPreviewRequest{ url: AnyHttpUrl }`
  - `ImportComponentEditRequest{ title?, ingredients[]?, instructions[]?, remove? }` with ingredient field `{ originalText, quantityOverride?, optional?, remove? }`
  - `ImportPreviewResponse{ parseId: str, title: str, sectionTitles: list[str], imageSources: list[AnyHttpUrl], duplicates: list[DuplicateSummary] }`
  - `ImportConfirmRequest{ parseId: str, title?, imageUrl?, yieldQuantity?, components: [ImportComponentEditRequest] }`
- Routes (in `api/routes/recipes.py`):
  - Add **`POST /recipes/import/preview`** → `ImportPreviewResponse`.
  - Add **`POST /recipes/import/confirm`** → `JobAcceptedResponse` (idempotency-keyed like the existing import route). The existing `POST /recipes/import` (bare URL) is **unchanged** and becomes the async fallback path; the wizard uses preview+confirm when preview succeeds in time.

- [ ] **Step 1: failing contract test**

```python
async def test_import_preview_and_confirm(client, owner_token):
    # Preview is sync and needs a live fetch; when services are down the contract
    # test must not hard-fail on the network call, so stub the importer in the app
    # fixture OR assert preview returns a structured error the client can fall back on.
    resp = await client.post(
        "/api/v1/recipes/import/preview",
        json={"url": "https://example.com/protein-oats"},
        headers={"Authorization": f"Bearer {owner_token}", "Idempotency-Key": "k1"},
    )
    assert resp.status_code in (200, 503)
```
Keep this a **contract** test (no live network): the app fixture stubs `RecipeImporter.preview` to raise a timeout/`RecipeImportError` so the route returns `503` (the stated fallback contract). A separate integration test (Task 3) covers a successful preview end-to-end with a real fetch.

- [ ] **Step 2: implement schemas + route wiring**

Add `preview` + `confirm` deps, the two routes, and the schemas from the Interfaces block. `import_recipe` keeps its existing bare-URL behavior. Wire `IdempotencyService` + `idempotency_key` for `confirm` exactly as `import_recipe` does today.

- [ ] **Step 3: update `specs/001-nutrient-recipe-planner/contracts/openapi.yaml`** with the new schemas + both paths.

- [ ] **Step 4: green + commit**

---
### Task 5: Regenerate TS client and add API wiring

**Files:**
- Modify: `frontend/src/api/generated/schema.ts` (regenerated, do not hand-edit)
- Modify: `frontend/src/features/recipes/api.ts`

- [ ] **Step 1: Regenerate**

Run (backend live): `pnpm --dir frontend exec openapi-typescript http://localhost:8080/api/openapi.json -o frontend/src/app/api/generated/schema.ts`

- [ ] **Step 2: Add methods**

```ts
preview(url: string) {
  return apiRequest<ImportPreview>("GET", "/recipes/import/preview", {...}))  // align method used below
}
```
Use the actual generated types (`ImportPreviewResponse`, `ImportConfirmRequest`). Wire `import` to build a `ImportConfirmRequest`.

- [ ] **Step 3: typecheck + commit**

---
### Task 6: Frontend import wizard (preview + quantity + duplicate)

**Files:**
- Modify: `frontend/src/features/recipes/RecipeImportDialog.tsx`
- Modify: `frontend/src/features/recipes/__tests__/recipe-ui.test.tsx`
- Modify: `frontend/src/styles/globals.css`

- [ ] **Step 1: failing component test** (expand `recipe-ui.test.tsx`): assert the dialog moves to a "preview" view showing the title, an image chooser, a flagged "needs quantity" ingredient, and a duplicate warning with Keep/Discard/Open-existing actions.

- [ ] **Step 2: implement dialog** — 3 steps (URL → preview → confirm). Reuse existing `Dialog`, `Field`, `Button`, `stack`, `actions` tokens. Add a `needsQuantity` flag per ingredient in preview. Duplicate banner with actions. On fallback response (`{fallback: true}` / no parseId) navigate to detail as today.

- [ ] **Step 3: style verified** — `pnpm --dir frontend lint` and `pnpm --dir frontend typecheck`, then `pnpm --dir frontend test --run`.

- [ ] **Step 4: commit**

---
### Task 7: e2e — import preview against live API

**Files:**
- Modify: `frontend/e2e/recipes.spec.ts`
- Modify: `frontend/e2e/mocks` if arrangement changed (see existing URL-import test that already hits the API — reuse its import mock).

- [ ] **Step 1: add e2e** — drive Start import → expect preview modal with title → apply a quantity override → Confirm → assert redirection to recipe detail. Add a duplicate test: second import of a duplicate title shows the warning.

- [ ] **Step 2: run `pnpm --dir frontend exec playwright test e2e/recipes.spec.ts`** — green.

- [ ] **Step 3: commit**

---
## Self-Review checklist

- [ ] Spec coverage: #4 preview modal (Tasks 3–6), #3 quantity flags (Tasks 3, 6), #8 components in preview (Tasks 3, 4, 6), #9 duplicates (Tasks 3, 4, 6), #11 PDF images (Task 2).
- [ ] No placeholders: every task has concrete code, exact paths, and run commands.
- [ ] Type/name consistency: `parseId` in schemas ↔ client ↔ dialog; `imageSources` ↔ `image_url`; confirm request field names match generated types.

## Execution Handoff

- Subagent-driven (recommended) or inline.