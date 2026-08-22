# Recipe Image Crop Rect Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the focal-point/zoom thumbnail framing with an exact normalized 4:3 crop rectangle, WYSIWYG across all render surfaces, with an Immich-style editor.

**Architecture:** One normalized rect (`x`, `y`, `width`, `height` as fixed-decimal strings) stored on the recipe; pure CSS math maps it onto any container; a rewritten `ThumbnailCropEditor` lets users drag/resize/reset the 4:3 selection. Default rect is the full image.

**Tech Stack:** Python 3.13 / FastAPI / Pydantic 2 / SQLAlchemy 2 / Alembic / PostgreSQL 18; React 19 / TypeScript 5 / Vitest / Testing Library.

**Spec:** `docs/superpowers/specs/2026-08-22-recipe-image-crop-rect-design.md`

## Global Constraints

- Fixed-precision decimals everywhere (6 places); canonical serialization strips trailing zeros server-side.
- No code comments (repo rule). Follow existing file style exactly.
- Frontend is intentionally type-broken between Task 1 (client regen) and Task 6 — do not run the full frontend gate until Task 6.
- Verification commands (from AGENTS.md):
  - `uv run --directory backend ruff format --check .`
  - `uv run --directory backend ruff check .`
  - `uv run --directory backend mypy src`
  - `uv run --directory backend pytest`
  - `pnpm --dir frontend lint && pnpm --dir frontend typecheck && pnpm --dir frontend test --run && pnpm --dir frontend build`

---

### Task 1: Backend crop-rect model end-to-end

The rename is atomic across backend layers to keep the suite green at the commit boundary.

**Files:**
- Modify: `backend/src/cookfully/domain/recipes.py` (ThumbnailCrop dataclass, ~lines 17–29)
- Create: `backend/migrations/versions/0026_recipe_thumbnail_crop_rect.py`
- Modify: `backend/src/cookfully/infrastructure/models/recipes.py:63-71`
- Modify: `backend/src/cookfully/api/schemas/recipes.py:135-167` and `667-671`
- Modify: `backend/src/cookfully/application/recipes.py:261-263, 338-341`
- Modify: `backend/src/cookfully/application/recipe_photos.py:128-131`
- Modify: `backend/src/cookfully/application/recipe_queries.py:294-297`
- Modify: `backend/src/cookfully/application/import_preview.py:200-203, 372-378`
- Test: `backend/tests/unit/test_thumbnail_crop.py` (new), `backend/tests/contract/test_recipe_api.py:207-228`, `backend/tests/unit/test_import_preview_coordinator.py`

**Interfaces:**
- Produces: domain `ThumbnailCrop(x, y, width, height)` of `Decimal`s, defaults `0/0/1/1`; Pydantic `ThumbnailCropRequest` with fields `x`, `y`, `width`, `height`; DB columns `recipes.thumbnail_x/y/width/height` as `Numeric(9,6)`.

- [ ] **Step 1: Write the failing domain test**

Create `backend/tests/unit/test_thumbnail_crop.py`:

```python
from decimal import Decimal

import pytest

from cookfully.domain.recipes import ThumbnailCrop


def test_default_is_full_image() -> None:
    crop = ThumbnailCrop()
    assert crop.x == Decimal("0")
    assert crop.y == Decimal("0")
    assert crop.width == Decimal("1")
    assert crop.height == Decimal("1")


def test_valid_partial_rect_accepted() -> None:
    crop = ThumbnailCrop(Decimal("0.25"), Decimal("0.125"), Decimal("0.5"), Decimal("0.375"))
    assert crop.width == Decimal("0.5")


@pytest.mark.parametrize(
    "kwargs",
    [
        {"x": Decimal("-0.1")},
        {"y": Decimal("1.1")},
        {"width": Decimal("0")},
        {"width": Decimal("1.2")},
        {"height": Decimal("0")},
        {"x": Decimal("0.75"), "width": Decimal("0.5")},
        {"y": Decimal("0.75"), "height": Decimal("0.5")},
    ],
)
def test_invalid_values_rejected(kwargs: dict) -> None:
    with pytest.raises(ValueError):
        ThumbnailCrop(**kwargs)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --directory backend pytest tests/unit/test_thumbnail_crop.py -v`
Expected: FAIL — `TypeError: __init__() got an unexpected keyword argument 'x'`

- [ ] **Step 3: Rewrite the domain value object**

Replace the `ThumbnailCrop` class in `backend/src/cookfully/domain/recipes.py`:

```python
@dataclass(frozen=True, slots=True)
class ThumbnailCrop:
    x: Decimal = Decimal("0.000000")
    y: Decimal = Decimal("0.000000")
    width: Decimal = Decimal("1.000000")
    height: Decimal = Decimal("1.000000")

    def __post_init__(self) -> None:
        for name in ("x", "y"):
            value = getattr(self, name)
            if not Decimal("0") <= value <= Decimal("1"):
                raise ValueError(f"thumbnail crop {name} must be between 0 and 1")
        for name in ("width", "height"):
            value = getattr(self, name)
            if not Decimal("0") < value <= Decimal("1"):
                raise ValueError(f"thumbnail crop {name} must be between 0 and 1")
        if self.x + self.width > Decimal("1"):
            raise ValueError("thumbnail crop extends past the right edge")
        if self.y + self.height > Decimal("1"):
            raise ValueError("thumbnail crop extends past the bottom edge")
```

Keep the existing imports/decorators style of that file.

- [ ] **Step 4: Run domain test**

Run: `uv run --directory backend pytest tests/unit/test_thumbnail_crop.py -v`
Expected: PASS (all)

- [ ] **Step 5: Create migration 0026**

Create `backend/migrations/versions/0026_recipe_thumbnail_crop_rect.py`. Copy the exact header comment/import conventions from `0025_food_embedding_index.py`:

```python
"""replace thumbnail focal/zoom metadata with a crop rectangle"""

revision: str = "0026_recipe_thumbnail_crop_rect"
down_revision: str | None = "0025_food_embedding_index"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("recipes", "thumbnail_focal_x")
    op.drop_column("recipes", "thumbnail_focal_y")
    op.drop_column("recipes", "thumbnail_zoom")
    op.add_column(
        "recipes",
        sa.Column("thumbnail_x", sa.Numeric(9, 6), nullable=False, server_default=sa.text("0")),
    )
    op.add_column(
        "recipes",
        sa.Column("thumbnail_y", sa.Numeric(9, 6), nullable=False, server_default=sa.text("0")),
    )
    op.add_column(
        "recipes",
        sa.Column("thumbnail_width", sa.Numeric(9, 6), nullable=False, server_default=sa.text("1")),
    )
    op.add_column(
        "recipes",
        sa.Column("thumbnail_height", sa.Numeric(9, 6), nullable=False, server_default=sa.text("1")),
    )


def downgrade() -> None:
    op.add_column(
        "recipes",
        sa.Column("thumbnail_zoom", sa.Numeric(9, 6), nullable=False, server_default=sa.text("1")),
    )
    op.add_column(
        "recipes",
        sa.Column("thumbnail_focal_y", sa.Numeric(9, 6), nullable=False, server_default=sa.text("0.5")),
    )
    op.add_column(
        "recipes",
        sa.Column("thumbnail_focal_x", sa.Numeric(9, 6), nullable=False, server_default=sa.text("0.5")),
    )
    for name in ("thumbnail_height", "thumbnail_width", "thumbnail_y", "thumbnail_x"):
        op.drop_column("recipes", name)
```

(Add `import sqlalchemy as sa` / `from alembic import op` per 0025's convention.)

- [ ] **Step 6: Rename infrastructure model columns**

In `backend/src/cookfully/infrastructure/models/recipes.py`, replace lines 63–71, mirroring the existing `mapped_column` style:

```python
    thumbnail_x: Mapped[Decimal] = mapped_column(
        Numeric(9, 6), nullable=False, default=Decimal("0.000000"), server_default=text("0")
    )
    thumbnail_y: Mapped[Decimal] = mapped_column(
        Numeric(9, 6), nullable=False, default=Decimal("0.000000"), server_default=text("0")
    )
    thumbnail_width: Mapped[Decimal] = mapped_column(
        Numeric(9, 6), nullable=False, default=Decimal("1.000000"), server_default=text("1")
    )
    thumbnail_height: Mapped[Decimal] = mapped_column(
        Numeric(9, 6), nullable=False, default=Decimal("1.000000"), server_default=text("1")
    )
```

- [ ] **Step 7: Rename application-layer field accesses**

`backend/src/cookfully/application/recipes.py:261-263` →

```python
                thumbnail_x=(write.thumbnail_crop or ThumbnailCrop()).x,
                thumbnail_y=(write.thumbnail_crop or ThumbnailCrop()).y,
                thumbnail_width=(write.thumbnail_crop or ThumbnailCrop()).width,
                thumbnail_height=(write.thumbnail_crop or ThumbnailCrop()).height,
```

`backend/src/cookfully/application/recipes.py:338-341` →

```python
            if write.thumbnail_crop is not None:
                recipe.thumbnail_x = write.thumbnail_crop.x
                recipe.thumbnail_y = write.thumbnail_crop.y
                recipe.thumbnail_width = write.thumbnail_crop.width
                recipe.thumbnail_height = write.thumbnail_crop.height
```

`backend/src/cookfully/application/recipe_photos.py:128-131` →

```python
                    recipe.thumbnail_x = crop.x
                    recipe.thumbnail_y = crop.y
                    recipe.thumbnail_width = crop.width
                    recipe.thumbnail_height = crop.height
```

`backend/src/cookfully/application/recipe_queries.py:294-297` →

```python
            thumbnail_crop=ThumbnailCrop(
                recipe.thumbnail_x,
                recipe.thumbnail_y,
                recipe.thumbnail_width,
                recipe.thumbnail_height,
            ),
```

`backend/src/cookfully/application/import_preview.py:200-203` →

```python
            thumbnail_crop=ThumbnailCrop(
                existing.thumbnail_x,
                existing.thumbnail_y,
                existing.thumbnail_width,
                existing.thumbnail_height,
            ),
```

`backend/src/cookfully/application/import_preview.py:372-378` →

```python
def _thumbnail_crop(value: object) -> ThumbnailCrop | None:
    if not isinstance(value, dict):
        return None
    return ThumbnailCrop(
        Decimal(str(value.get("x", "0"))),
        Decimal(str(value.get("y", "0"))),
        Decimal(str(value.get("width", "1"))),
        Decimal(str(value.get("height", "1"))),
    )
```

- [ ] **Step 8: Update Pydantic schemas**

In `backend/src/cookfully/api/schemas/recipes.py` replace `_crop_fraction`…`ThumbnailCropRequest` (lines 135–167). Add `model_validator` to the pydantic imports if absent:

```python
def _crop_fraction(value: object) -> Decimal:
    parsed = _fixed_decimal(value, places=6)
    if parsed < 0 or parsed > 1:
        raise ValueError("crop position must be between 0 and 1")
    return parsed


def _crop_size(value: object) -> Decimal:
    parsed = _fixed_decimal(value, places=6)
    if parsed <= 0 or parsed > 1:
        raise ValueError("crop size must be greater than 0 and at most 1")
    return parsed


CropFraction = Annotated[
    Decimal,
    BeforeValidator(_crop_fraction),
    PlainSerializer(lambda value: canonical_decimal(value), return_type=str),
]
CropSize = Annotated[
    Decimal,
    BeforeValidator(_crop_size),
    PlainSerializer(lambda value: canonical_decimal(value), return_type=str),
]


class ThumbnailCropRequest(ApiModel):
    x: CropFraction = Field(default=Decimal("0.000000"))
    y: CropFraction = Field(default=Decimal("0.000000"))
    width: CropSize = Field(default=Decimal("1.000000"))
    height: CropSize = Field(default=Decimal("1.000000"))

    @model_validator(mode="after")
    def _within_bounds(self) -> "ThumbnailCropRequest":
        if self.x + self.width > Decimal("1"):
            raise ValueError("thumbnail crop extends past the right edge")
        if self.y + self.height > Decimal("1"):
            raise ValueError("thumbnail crop extends past the bottom edge")
        return self

    def to_domain(self) -> ThumbnailCrop:
        return ThumbnailCrop(self.x, self.y, self.width, self.height)
```

Delete `_crop_zoom` and `CropZoom`. Update `from_read` (lines 667–671):

```python
            thumbnail_crop=ThumbnailCropRequest(
                x=value.thumbnail_crop.x,
                y=value.thumbnail_crop.y,
                width=value.thumbnail_crop.width,
                height=value.thumbnail_crop.height,
            ),
```

- [ ] **Step 9: Update backend tests**

`backend/tests/contract/test_recipe_api.py:207-228`: change the create payload crop to

```python
{"x": "0.250000", "y": "0.125000", "width": "0.500000", "height": "0.500000"}
```

and response assertions to the canonical strings `"0.25"`, `"0.125"`, `"0.5"`, `"0.5"` under keys `x`, `y`, `width`, `height`. Extend the invalid-input cases to assert 422 for: `x: "1.100000"`; `width: "0"`; and a full valid payload except `y: "0.75", height: "0.5"` (bounds overflow).

`backend/tests/unit/test_import_preview_coordinator.py` (lines ~68–69, 179, 215): replace every `{"focalX": ..., "focalY": ..., "zoom": ...}` fixture with

```python
{"x": "0.125", "y": "0.25", "width": "0.5", "height": "0.375"}
```

(Grep the file for `focalX` to catch all sites.)

- [ ] **Step 10: Run backend gate**

Run: `uv run --directory backend ruff format --check . && uv run --directory backend ruff check . && uv run --directory backend mypy src && uv run --directory backend pytest`
Expected: all green. Fix any remaining `focal`/`zoom` references the compiler flags.

- [ ] **Step 11: Commit**

```bash
git add -A backend/
git commit -m "feat: store thumbnail framing as a normalized 4:3 crop rect"
```

---

### Task 2: OpenAPI contract + regenerate client

**Files:**
- Modify: `specs/001-nutrition-recipe-planner/contracts/openapi.yaml:2298-2305`
- Regenerated: `frontend/src/app/api/generated/schema.ts`

**Interfaces:**
- Produces: generated `ThumbnailCropRequest`/`RecipeResponse` types with `x`, `y`, `width`, `height` string fields (used by Tasks 3–6).

- [ ] **Step 1: Update the contract schema block**

Replace the `ThumbnailCrop` schema (lines 2298–2305):

```yaml
    ThumbnailCrop:
      type: object
      additionalProperties: false
      required: [x, y, width, height]
      properties:
        x: { type: string, pattern: "^(0|1|0\\.[0-9]{1,6})$" }
        y: { type: string, pattern: "^(0|1|0\\.[0-9]{1,6})$" }
        width: { type: string, pattern: "^(0\\.[0-9]{1,6}|1)$" }
        height: { type: string, pattern: "^(0\\.[0-9]{1,6}|1)$" }
```

- [ ] **Step 2: Regenerate the client**

Run: `pwsh scripts/generate-api-client.ps1`
Expected output: `Generated committed client schema from OpenAPI 3.1 contract for API v0.2.x.`

Verify: `rg -n "focalX" frontend/src/app/api/generated/schema.ts` returns nothing.

- [ ] **Step 3: Commit**

```bash
git add specs/001-nutrition-recipe-planner/contracts/openapi.yaml frontend/src/app/api/generated/schema.ts
git commit -m "chore: regenerate api client for crop rect contract"
```

---

### Task 3: Frontend pure helpers `thumbnailCrop.ts`

**Files:**
- Create: `frontend/src/features/recipes/thumbnailCrop.ts`
- Test: `frontend/src/features/recipes/__tests__/thumbnailCrop.test.ts` (new)

**Interfaces:**
- Produces (consumed by Tasks 4–5):

```ts
export interface CropRect { x: number; y: number; width: number; height: number }
export type Corner = "nw" | "ne" | "sw" | "se";
export const CROP_ASPECT: number;      // 4/3
export const MIN_CROP_SIZE: number;    // 0.15
export function parseRect(value?: Partial<Record<"x"|"y"|"width"|"height", string>> | null): CropRect
export function serializeRect(rect: CropRect): Required<Record<"x"|"y"|"width"|"height", string>>
export function isDefaultRect(rect: CropRect): boolean
export function defaultFit(aspect: number): CropRect   // aspect = width/height
export function moveRect(rect: CropRect, dx: number, dy: number): CropRect
export function resizeToPoint(rect: CropRect, corner: Corner, nx: number, ny: number): CropRect
export function setWidth(rect: CropRect, width: number): CropRect
```

- [ ] **Step 1: Write the failing tests**

Create `frontend/src/features/recipes/__tests__/thumbnailCrop.test.ts`:

```ts
import { describe, expect, it } from "vitest";

import {
  CROP_ASPECT,
  MIN_CROP_SIZE,
  defaultFit,
  isDefaultRect,
  moveRect,
  parseRect,
  resizeToPoint,
  serializeRect,
  setWidth,
} from "../thumbnailCrop";

describe("defaultFit", () => {
  it("returns the full image for a 4:3 source", () => {
    expect(defaultFit(CROP_ASPECT)).toEqual({ x: 0, y: 0, width: 1, height: 1 });
  });
  it("centers a horizontal band inside a wide source", () => {
    const fit = defaultFit(16 / 9);
    expect(fit).toEqual({ x: 0.125, y: 0, width: 0.75, height: 1 });
  });
  it("centers a vertical slice inside a tall source", () => {
    const fit = defaultFit(3 / 4);
    expect(fit).toEqual({ x: 0, y: (1 - (3 / 4) / CROP_ASPECT) / 2, width: 1, height: (3 / 4) / CROP_ASPECT });
  });
  it("falls back to full image for non-positive or NaN aspects", () => {
    expect(defaultFit(NaN)).toEqual({ x: 0, y: 0, width: 1, height: 1 });
    expect(defaultFit(-1)).toEqual({ x: 0, y: 0, width: 1, height: 1 });
  });
});

describe("moveRect", () => {
  const rect = { x: 0.1, y: 0.1, width: 0.75, height: 1 };
  it("clamps movement to the left edge", () => {
    expect(moveRect(rect, -5, 0).x).toBe(0);
  });
  it("clamps movement to the right edge", () => {
    expect(moveRect(rect, 5, 0).x).toBe(0.25);
  });
});

describe("resizeToPoint", () => {
  const rect = { x: 0.25, y: 0.25, width: 0.5, height: 1 };
  it("keeps aspect locked while dragging the se corner", () => {
    const next = resizeToPoint(rect, "se", 0.75, 0.75);
    expect(next.width / CROP_ASPECT).toBeCloseTo(next.height, 6);
    expect(next.x).toBe(0.25);
    expect(next.y).toBe(0.25);
  });
  it("anchors the opposite corner when resizing nw", () => {
    const next = resizeToPoint(rect, "nw", 0.05, 0.05);
    expect(next.x + next.width).toBeCloseTo(0.75, 6);
    expect(next.y + next.height).toBeCloseTo(1, 6);
  });
  it("enforces the minimum size near edges", () => {
    const tiny = resizeToPoint(rect, "se", 0.26, 0.26);
    expect(tiny.width).toBeGreaterThanOrEqual(MIN_CROP_SIZE);
  });
  it("never exceeds image bounds when dragging past them", () => {
    const next = resizeToPoint(rect, "se", 5, 5);
    expect(next.x + next.width).toBeLessThanOrEqual(1);
    expect(next.y + next.height).toBeLessThanOrEqual(1);
  });
});

describe("setWidth", () => {
  it("anchors top-left and respects bounds", () => {
    const next = setWidth({ x: 0.5, y: 0, width: 0.5, height: 1 }, 1);
    expect(next.x + next.width).toBeLessThanOrEqual(1);
  });
  it("clamps below the minimum size", () => {
    expect(setWidth({ x: 0, y: 0, width: 0.5, height: 1 }, 0.01).width).toBe(MIN_CROP_SIZE);
  });
});

describe("parse/serialize/isDefault", () => {
  it("round-trips through fixed-decimal strings", () => {
    const rect = { x: 0.123457, y: 0.5, width: 0.75, height: 1 };
    expect(parseRect(serializeRect(rect))).toEqual({
      x: Number((0.123457).toFixed(6)),
      y: 0.5,
      width: 0.75,
      height: 1,
    });
  });
  it("detects the default full-image rect", () => {
    expect(isDefaultRect({ x: 0, y: 0, width: 1, height: 1 })).toBe(true);
    expect(isDefaultRect(defaultFit(16 / 9))).toBe(false);
  });
  it("falls back to the full rect on malformed input", () => {
    expect(parseRect({ x: "abc" })).toEqual({ x: 0, y: 0, width: 1, height: 1 });
    expect(parseRect(null)).toEqual({ x: 0, y: 0, width: 1, height: 1 });
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pnpm --dir frontend test --run src/features/recipes/__tests__/thumbnailCrop.test.ts`
Expected: FAIL — cannot resolve `../thumbnailCrop`.

- [ ] **Step 3: Implement the module**

Create `frontend/src/features/recipes/thumbnailCrop.ts`:

```ts
export interface CropRect {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface CropWrite {
  x?: string;
  y?: string;
  width?: string;
  height?: string;
}

export type Corner = "nw" | "ne" | "sw" | "se";

export const CROP_ASPECT = 4 / 3;
export const MIN_CROP_SIZE = 0.15;

const FULL_RECT: CropRect = { x: 0, y: 0, width: 1, height: 1 };

function clamp(value: number, low: number, high: number): number {
  return Math.min(high, Math.max(low, value));
}

export function parseRect(value?: CropWrite | null): CropRect {
  const rect = {
    x: Number(value?.x ?? "0"),
    y: Number(value?.y ?? "0"),
    width: Number(value?.width ?? "1"),
    height: Number(value?.height ?? "1"),
  };
  if (![rect.x, rect.y, rect.width, rect.height].every(Number.isFinite)) return { ...FULL_RECT };
  if (
    rect.width <= 0 ||
    rect.height <= 0 ||
    rect.x < 0 ||
    rect.y < 0 ||
    rect.x + rect.width > 1 ||
    rect.y + rect.height > 1
  ) {
    return { ...FULL_RECT };
  }
  return rect;
}

export function serializeRect(rect: CropRect): Required<CropWrite> {
  return {
    x: rect.x.toFixed(6),
    y: rect.y.toFixed(6),
    width: rect.width.toFixed(6),
    height: rect.height.toFixed(6),
  };
}

export function isDefaultRect(rect: CropRect): boolean {
  return rect.x === 0 && rect.y === 0 && rect.width === 1 && rect.height === 1;
}

export function defaultFit(aspect: number): CropRect {
  if (!Number.isFinite(aspect) || aspect <= 0) return { ...FULL_RECT };
  if (aspect >= CROP_ASPECT) {
    const width = CROP_ASPECT / aspect;
    return { x: (1 - width) / 2, y: 0, width, height: 1 };
  }
  const height = aspect / CROP_ASPECT;
  return { x: 0, y: (1 - height) / 2, width: 1, height };
}

export function moveRect(rect: CropRect, dx: number, dy: number): CropRect {
  return {
    ...rect,
    x: clamp(rect.x + dx, 0, 1 - rect.width),
    y: clamp(rect.y + dy, 0, 1 - rect.height),
  };
}

export function resizeToPoint(rect: CropRect, corner: Corner, pointerX: number, pointerY: number): CropRect {
  const anchorLeft = corner === "ne" || corner === "se";
  const anchorTop = corner === "se" || corner === "sw";
  const anchorX = anchorLeft ? rect.x : rect.x + rect.width;
  const anchorY = anchorTop ? rect.y : rect.y + rect.height;
  const rawWidth = Math.abs(pointerX - anchorX);
  const rawHeight = Math.abs(pointerY - anchorY);
  let width = rawWidth / CROP_ASPECT > rawHeight ? rawWidth : rawHeight * CROP_ASPECT;
  const availableWidth = anchorLeft ? 1 - anchorX : anchorX;
  const availableHeight = anchorTop ? 1 - anchorY : anchorY;
  const maxWidth = Math.min(availableWidth, availableHeight * CROP_ASPECT);
  width = clamp(width, MIN_CROP_SIZE, Math.max(MIN_CROP_SIZE, maxWidth));
  const height = width / CROP_ASPECT;
  return {
    x: anchorLeft ? anchorX : anchorX - width,
    y: anchorTop ? anchorY : anchorY - height,
    width,
    height,
  };
}

export function setWidth(rect: CropRect, width: number): CropRect {
  const maxWidth = Math.min(1 - rect.x, (1 - rect.y) * CROP_ASPECT);
  const clamped = clamp(width, MIN_CROP_SIZE, Math.max(MIN_CROP_SIZE, maxWidth));
  return { x: rect.x, y: rect.y, width: clamped, height: clamped / CROP_ASPECT };
}
```

Note: `isDefaultRect` takes a `CropRect` here; callers pass `parseRect(value)` first (Task 5 does this).

- [ ] **Step 4: Run tests**

Run: `pnpm --dir frontend test --run src/features/recipes/__tests__/thumbnailCrop.test.ts`
Expected: PASS. If a resize/bounds expectation differs, fix the helper — never weaken the test.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/features/recipes/thumbnailCrop.ts frontend/src/features/recipes/__tests__/thumbnailCrop.test.ts
git commit -m "feat: add pure crop rect helpers for thumbnail framing"
```

---

### Task 4: Rendering — RecipeMedia vars + render-site CSS

**Files:**
- Modify: `frontend/src/components/cookfully/RecipeMedia.tsx`
- Modify: `frontend/src/styles/features.css` (lines ~145, ~296, and `.thumbnail-crop-editor` blocks stay for Task 5)
- Modify: `frontend/src/styles/home.css` (lines ~66, ~144, ~157, ~183)
- Test: `frontend/src/components/cookfully/__tests__/*RecipeMedia*` (create if none exists; check directory first)

- [ ] **Step 1: Update RecipeMedia.tsx**

Replace the source interface and inline style:

```tsx
export interface RecipeMediaSource {
  title: string;
  imageUrl?: string | null;
  thumbnailCrop?: {
    x: string | number;
    y: string | number;
    width: string | number;
    height: string | number;
  } | null;
}
```

and in the component body:

```tsx
  const crop = recipe.thumbnailCrop ?? { x: "0", y: "0", width: "1", height: "1" };
```

```tsx
      style={{
        "--crop-x": String(crop.x),
        "--crop-y": String(crop.y),
        "--crop-width": String(crop.width),
        "--crop-height": String(crop.height),
      } as CSSProperties}
```

Everything else in the file stays.

- [ ] **Step 2: Update CSS render sites**

Apply this universal pattern to each media container. For every container block listed, ensure the container has `position: relative; overflow: hidden;` and replace its `img` rule:

Container/img pairs to update:
- `features.css` `.recipe-card__media` / `.recipe-card__media img` (~line 145)
- `features.css` `.recipe-hero__media` / `.recipe-hero__media img` (~line 296)
- `home.css` `.home-tonight__photo` / `.home-tonight__photo img` (~line 66)
- `home.css` `.home-recommendation__media` / `.home-recommendation__media img` (~line 144)
- `home.css` `.home-recent-recipe__media` / `.home-recent-recipe__media img` (~line 157)

New img rule (identical everywhere):

```css
SELECTOR img {
  position: absolute;
  width: calc(100% / var(--crop-width, 1));
  height: calc(100% / var(--crop-height, 1));
  left: calc(var(--crop-x, 0) / var(--crop-width, 1) * -100%);
  top: calc(var(--crop-y, 0) / var(--crop-height, 1) * -100%);
  object-fit: cover;
}
```

Remove `object-position` and the `transform: scale(var(--thumbnail-zoom, 1))` declarations from all five rules. In `home.css:183` change the hover rule to:

```css
.home-recent-recipe:hover img { transform: scale(1.035); }
```

Also grep `features.css` for `.recipe-editor__hero-media img` and apply the same pattern if present.

- [ ] **Step 3: Verify visually against the running stack (optional but cheap)**

The Docker stack serves the old bundle; skip runtime verification until Task 6. Static checks only here:

Run: `pnpm --dir frontend typecheck`
Expected: errors ONLY from stale fixtures referencing `focalX`/`focalY`/`zoom` (fixed in Task 6). No errors in `RecipeMedia.tsx` or CSS-consuming components.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/cookfully/RecipeMedia.tsx frontend/src/styles/features.css frontend/src/styles/home.css
git commit -m "feat: render thumbnails from exact crop rect metadata"
```

---

### Task 5: ThumbnailCropEditor rewrite

**Files:**
- Modify: `frontend/src/features/recipes/ThumbnailCropEditor.tsx` (full rewrite)
- Modify: `frontend/src/styles/features.css` (replace existing `.thumbnail-crop-editor` rules)
- Test: `frontend/src/features/recipes/__tests__/ThumbnailCropEditor.test.tsx` (full rewrite)

**Interfaces:**
- Consumes: everything exported from `./thumbnailCrop` (Task 3).
- Produces: unchanged component signature `{ imageUrl, value?, onChange }` where values are `{x,y,width,height}` strings.

- [ ] **Step 1: Rewrite the component**

Full new `ThumbnailCropEditor.tsx`:

```tsx
import { type KeyboardEvent, type PointerEvent, useEffect, useRef, useState } from "react";

import {
  CROP_ASPECT,
  MIN_CROP_SIZE,
  type Corner,
  defaultFit,
  isDefaultRect,
  moveRect,
  parseRect,
  resizeToPoint,
  serializeRect,
  setWidth,
} from "./thumbnailCrop";
import type { ThumbnailCropWrite } from "./types";

const HANDLES: Corner[] = ["nw", "ne", "sw", "se"];

export function ThumbnailCropEditor({
  imageUrl,
  value,
  onChange,
}: {
  imageUrl: string;
  value?: ThumbnailCropWrite;
  onChange: (value: ThumbnailCropWrite) => void;
}) {
  const previewRef = useRef<HTMLDivElement>(null);
  const drag = useRef<{ mode: "move" | Corner; startX: number; startY: number } | null>(null);
  const [aspect, setAspect] = useState(CROP_ASPECT);
  const [slidersOpen, setSlidersOpen] = useState(false);

  useEffect(() => {
    const node = previewRef.current;
    if (!node) return;
    const observer = new ResizeObserver(() => node.dispatchEvent(new Event("resize")));
    observer.observe(node);
    window.addEventListener("resize", measure);
    function measure() {
      node!.style.setProperty("--preview-width", `${node!.clientWidth}px`);
    }
    measure();
    return () => {
      observer.disconnect();
      window.removeEventListener("resize", measure);
    };
  }, []);

  const stored = parseRect(value);
  const crop = isDefaultRect(stored) ? defaultFit(aspect) : stored;

  const onPointerDown = (event: PointerEvent<HTMLDivElement>) => {
    if (event.button !== 0) return;
    const target = event.target instanceof Element ? event.target.closest("[data-crop-resize]") : null;
    const mode = (target?.getAttribute("data-crop-resize") as Corner | null) ?? "move";
    drag.current = { mode, startX: event.clientX, startY: event.clientY };
    event.currentTarget.setPointerCapture(event.pointerId);
  };

  const onPointerMove = (event: PointerEvent<HTMLDivElement>) => {
    const current = drag.current;
    if (!current) return;
    const bounds = event.currentTarget.getBoundingClientRect();
    if (bounds.width === 0 || bounds.height === 0) return;
    if (current.mode === "move") {
      onChange(
        serializeRect(
          moveRect(crop, (event.clientX - current.startX) / bounds.width, (event.clientY - current.startY) / bounds.height),
        ),
      );
      return;
    }
    onChange(
      serializeRect(
        resizeToPoint(
          crop,
          current.mode,
          (event.clientX - bounds.left) / bounds.width,
          (event.clientY - bounds.top) / bounds.height,
        ),
      ),
    );
  };

  const endDrag = () => {
    drag.current = null;
  };

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const step = event.shiftKey ? 0.05 : 0.01;
    let next = null;
    if (event.shiftKey) {
      if (event.key === "ArrowRight" || event.key === "ArrowUp") next = setWidth(crop, crop.width + step * 2);
      else if (event.key === "ArrowLeft" || event.key === "ArrowDown") next = setWidth(crop, crop.width - step * 2);
    } else if (event.key === "ArrowLeft") next = moveRect(crop, -step, 0);
    else if (event.key === "ArrowRight") next = moveRect(crop, step, 0);
    else if (event.key === "ArrowUp") next = moveRect(crop, 0, -step);
    else if (event.key === "ArrowDown") next = moveRect(crop, 0, step);
    if (!next) return;
    event.preventDefault();
    onChange(serializeRect(next));
  };

  const frameStyle = {
    left: `${crop.x * 100}%`,
    top: `${crop.y * 100}%`,
    width: `${crop.width * 100}%`,
    height: `${crop.height * 100}%`,
  };

  return (
    <section className="thumbnail-crop-editor" aria-label="Adjust thumbnail crop">
      <div className="thumbnail-crop-editor__preview" ref={previewRef} style={{ aspectRatio: String(aspect) }}>
        <img
          src={imageUrl}
          alt=""
          onLoad={(event) => {
            const image = event.currentTarget;
            if (image.naturalWidth > 0 && image.naturalHeight > 0) {
              setAspect(image.naturalWidth / image.naturalHeight);
            }
          }}
        />
        <div className="thumbnail-crop-editor__stage" aria-label="Crop area" onPointerDown={onPointerDown} onPointerMove={onPointerMove} onPointerUp={endDrag} onPointerCancel={endDrag}>
          <div className="thumbnail-crop-editor__frame" style={frameStyle} tabIndex={0} aria-label="Thumbnail selection" onKeyDown={onKeyDown}>
            {HANDLES.map((corner) => (
              <span key={corner} className={`thumbnail-crop-editor__handle thumbnail-crop-editor__handle--${corner}`} data-crop-resize={corner} />
            ))}
          </div>
        </div>
      </div>
      <div className="thumbnail-crop-editor__controls">
        <button type="button" className="text-link" onClick={() => onChange(serializeRect(defaultFit(aspect)))}>
          Reset
        </button>
        <button type="button" className="text-link" onClick={() => setSlidersOpen((open) => !open)} aria-expanded={slidersOpen}>
          {slidersOpen ? "Hide framing controls" : "Adjust framing"}
        </button>
        {slidersOpen ? (
          <div className="thumbnail-crop-editor__sliders">
            <label>
              Horizontal position
              <input
                type="range"
                min="0"
                max={Math.max(0, 1 - crop.width)}
                step="0.01"
                value={crop.x}
                onChange={(event) => onChange(serializeRect({ ...crop, x: Number(event.currentTarget.value) }))}
              />
            </label>
            <label>
              Vertical position
              <input
                type="range"
                min="0"
                max={Math.max(0, 1 - crop.height)}
                step="0.01"
                value={crop.y}
                onChange={(event) => onChange(serializeRect({ ...crop, y: Number(event.currentTarget.value) }))}
              />
            </label>
            <label>
              Size
              <input
                type="range"
                min={MIN_CROP_SIZE}
                max="1"
                step="0.01"
                value={crop.width}
                onChange={(event) => onChange(serializeRect(setWidth(crop, Number(event.currentTarget.value))))}
              />
            </label>
          </div>
        ) : null}
      </div>
    </section>
  );
}
```

If the `useEffect` observer block above conflicts with repo lint rules (e.g., no nested function declarations), simplify to only `window.addEventListener("resize", …)` plus an initial no-op — the stage uses percentage positioning so JS measurement is not required for correctness. Keep whichever variant passes lint cleanly; prefer deleting the effect entirely since nothing consumes `--preview-width`.

- [ ] **Step 2: Replace the editor CSS**

In `frontend/src/styles/features.css`, find the existing `.thumbnail-crop-editor` rules and replace them with:

```css
.thumbnail-crop-editor__preview {
  position: relative;
  overflow: hidden;
  background: var(--color-surface-sunken, #eee);
  touch-action: none;
}

.thumbnail-crop-editor__preview img {
  display: block;
  width: 100%;
  height: 100%;
}

.thumbnail-crop-editor__stage {
  position: absolute;
  inset: 0;
  cursor: move;
  touch-action: none;
}

.thumbnail-crop-editor__frame {
  position: absolute;
  outline: 2px solid var(--color-accent, #333);
  box-shadow: 0 0 0 9999px rgb(0 0 0 / 45%);
  cursor: move;
}

.thumbnail-crop-editor__frame:focus-visible {
  outline: 3px solid var(--color-accent-strong, #111);
}

.thumbnail-crop-editor__handle {
  position: absolute;
  width: 14px;
  height: 14px;
  border: 2px solid var(--color-accent, #333);
  background: var(--color-surface, #fff);
  border-radius: 50%;
}

.thumbnail-crop-editor__handle--nw { top: -7px; left: -7px; cursor: nwse-resize; }
.thumbnail-crop-editor__handle--ne { top: -7px; right: -7px; cursor: nesw-resize; }
.thumbnail-crop-editor__handle--sw { bottom: -7px; left: -7px; cursor: nesw-resize; }
.thumbnail-crop-editor__handle--se { bottom: -7px; right: -7px; cursor: nwse-resize; }
```

Adapt custom-property names to the tokens actually defined in the stylesheet/DESIGN.md (check neighboring rules).

- [ ] **Step 3: Rewrite the component tests**

Full new `frontend/src/features/recipes/__tests__/ThumbnailCropEditor.test.tsx`:

```tsx
import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ThumbnailCropEditor } from "../ThumbnailCropEditor";
import { CROP_ASPECT, defaultFit, parseRect, serializeRect } from "../thumbnailCrop";

function setup(value?: Parameters<typeof ThumbnailCropEditor>[0]["value"]) {
  const onChange = vi.fn();
  render(<ThumbnailCropEditor imageUrl="https://example.com/photo.webp" value={value} onChange={onChange} />);
  const image = screen.getByAltText("");
  Object.defineProperty(image, "naturalWidth", { value: 1600 });
  Object.defineProperty(image, "naturalHeight", { value: 900 });
  fireEvent(image, new Event("load"));
  return onChange;
}

afterEach(() => {
  vi.clearAllMocks();
});

describe("ThumbnailCropEditor", () => {
  it("shows the largest centered 4:3 fit for a wide image when the stored rect is the default", () => {
    setup({ x: "0", y: "0", width: "1", height: "1" });
    const fit = defaultFit(16 / 9);
    expect(screen.getByRole("slider", { name: "Horizontal position" })).toHaveValue(fit.x);
  });

  it("resets to the fitted rect", () => {
    const onChange = setup();
    fireEvent.click(screen.getByRole("button", { name: "Reset" }));
    expect(onChange).toHaveBeenLastCalledWith(serializeRect(defaultFit(CROP_ASPECT)));
  });

  it("moves the selection with arrow keys", () => {
    const onChange = setup({ x: "0.200000", y: "0.100000", width: "0.500000", height: "0.750000" });
    fireEvent.keyDown(screen.getByRole("group", { name: "Crop area" }).querySelector(".thumbnail-crop-editor__frame")!, {
      key: "ArrowRight",
    });
    const call = onChange.mock.lastCall![0];
    expect(Number(call.x)).toBeCloseTo(0.21, 6);
    expect(Number(call.y)).toBeCloseTo(0.1, 6);
  });

  it("resizes with shift+arrow keys", () => {
    const onChange = setup({ x: "0.100000", y: "0.100000", width: "0.400000", height: "0.300000" });
    fireEvent.keyDown(screen.getByRole("group", { name: "Crop area" }).querySelector(".thumbnail-crop-editor__frame")!, {
      key: "ArrowRight",
      shiftKey: true,
    });
    const call = onChange.mock.lastCall![0];
    expect(Number(call.width)).toBeGreaterThan(0.4);
    expect(parseRect(call).height / parseRect(call).width).toBeCloseTo(0.75, 6);
  });

  it("commits slider changes", () => {
    const onChange = setup({ x: "0.000000", y: "0.000000", width: "0.750000", height: "1.000000" });
    fireEvent.change(screen.getByRole("slider", { name: "Horizontal position" }), { target: { value: "0.12" } });
    expect(Number(onChange.mock.lastCall![0].x)).toBeCloseTo(0.12, 6);
  });
});
```

Adjust roles/assertions to what actually renders (e.g., if `role="group"` isn't emitted by a plain div, add `role="presentation"` queries via container.querySelector instead). Never weaken assertions about geometry.

- [ ] **Step 4: Run the editor tests**

Run: `pnpm --dir frontend test --run src/features/recipes/__tests__/ThumbnailCropEditor.test.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/features/recipes/ThumbnailCropEditor.tsx frontend/src/features/recipes/__tests__/ThumbnailCropEditor.test.tsx frontend/src/styles/features.css
git commit -m "feat: rewrite thumbnail editor as draggable 4:3 crop tool"
```

---

### Task 6: Wire-up + green frontend suite

**Files:**
- Modify: `frontend/src/features/recipes/RecipeEditorPage.tsx:43,195`
- Modify: `frontend/src/features/recipes/RecipeImportDialog.tsx:22`
- Modify: `frontend/src/features/recipes/types.ts` (only if it re-declares crop shapes rather than deriving from generated types)
- Modify fixtures: `frontend/src/features/recipes/__tests__/recipe-editor-model.test.ts:18`, `recipe-library-density.test.tsx:31,50`, `recipe-ui.test.tsx:58`, `frontend/src/app/App.test.tsx:93`

- [ ] **Step 1: Update default factories**

Both files define:

```tsx
const defaultThumbnailCrop = (): ThumbnailCropWrite => ({ focalX: "0.5", focalY: "0.5", zoom: "1" });
```

Replace both with:

```tsx
const defaultThumbnailCrop = (): ThumbnailCropWrite => ({ x: "0", y: "0", width: "1", height: "1" });
```

- [ ] **Step 2: Update fixtures**

Grep the four test files for `focalX|focalY|zoom` and replace crop literals with rect equivalents (any valid rect, e.g. `{ x: "0.25", y: "0.125", width: "0.5", height: "0.375" }`, preserving what each assertion checks).

- [ ] **Step 3: Typecheck drives out stragglers**

Run: `pnpm --dir frontend typecheck`
Fix any remaining `focalX`/`focalY`/`zoom` references anywhere in `frontend/src` (grep to confirm zero remain outside generated history).

- [ ] **Step 4: Full frontend suite**

Run: `pnpm --dir frontend lint && pnpm --dir frontend typecheck && pnpm --dir frontend test --run && pnpm --dir frontend build`
Expected: all green.

- [ ] **Step 5: Commit**

```bash
git add -A frontend/
git commit -m "feat: wire crop rect through editor, import dialog, and fixtures"
```

---

### Task 7: Docs + full verification gate

**Files:**
- Modify: `docs/inspiration-review.md`
- Modify: `DESIGN.md` (only where it describes thumbnail framing controls)

- [ ] **Step 1: Inspiration review entry**

Append a dated section to `docs/inspiration-review.md` following the existing entry format, covering: the problem (per-surface focal/zoom drift made framing non-WYSIWYG), Immich's observed crop-editor pattern (contained image preview, dimmed exterior, aspect-locked corner-handle resizing, reset-to-fit), benefits (exact user intent, predictable rendering), liabilities (server trusts client geometry; no pixel derivatives means large originals are downloaded then cropped client-side), and the decision: adopt the interaction pattern, adapt it to a normalized rect contract persisted beside original media (no destructive rewriting), reject backend derivative generation for now.

- [ ] **Step 2: DESIGN.md pass**

Grep `DESIGN.md` for focal/framing/crop references; update copy to describe the 4:3 selection tool (drag, corner handles, Reset, keyboard arrows + Shift+arrows, sliders fallback).

- [ ] **Step 3: Full verification gate**

Run (all must pass):

```powershell
uv run --directory backend ruff format --check .
uv run --directory backend ruff check .
uv run --directory backend mypy src
uv run --directory backend pytest
pnpm --dir frontend lint
pnpm --dir frontend typecheck
pnpm --dir frontend test --run
pnpm --dir frontend build
```

- [ ] **Step 4: Manual smoke via running stack**

Rebuild the local Docker web/api images (`docker compose -f deploy/compose.yaml up -d --build api worker web`) and verify at http://localhost:8080: upload/edit a photo, drag the frame, resize from corners, keyboard-navigate the frame, Reset, save; confirm card + hero + home tiles show the chosen region; confirm untouched recipes still show the whole image cover-fitted.

- [ ] **Step 5: Commit**

```bash
git add docs/inspiration-review.md DESIGN.md
git commit -m "docs: record immich crop-editor comparison and design updates"
```
