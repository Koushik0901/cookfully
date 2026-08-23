# Recipe Image Crop Rect — Design

Date: 2026-08-22
Status: Approved (pending implementation plan)

## Problem

The recipe edit screen's thumbnail framing tool does not behave like a real crop tool. The stored
model is a focal point plus zoom (`focalX`, `focalY`, `zoom`) rendered through CSS
`object-position` percentages and `transform: scale()`. Because every render surface has its own
container aspect ratio (recipe cards ~4:3, detail hero ~2:1, home tiles), the same metadata yields
visibly different crops per surface. Zoom is not clamped against pan bounds, the corner resize
handles all map horizontal movement to one zoom axis, and the planned pure-math helper module was
never implemented. The user cannot choose an exact portion of the image.

## Goal

Let users select the exact portion of a recipe photo that becomes its thumbnail, Immich-style.
By default the full image is used.

## Decisions

- **Fixed 4:3 output.** The selection always matches the standard recipe-card ratio. Non-4:3
  surfaces re-cover the selected region symmetrically. This makes the card view truly WYSIWYG and
  keeps every other surface predictable without per-surface tuning.
- **Exact normalized rectangle replaces focal/zoom.** One rectangle in unit coordinates defines the
  framed region; rendering math maps it onto any container exactly.
- **Default is the full image.** Untouched recipes store `{x:0, y:0, width:1, height:1}` and render
  as today: the whole photo, cover-fitted by each container.
- **Existing framing data resets.** The app currently has only development/test data, so the
  migration drops old focal/zoom values instead of deriving rectangles from them.

## Data model & contract

### Domain value object

`backend/src/cookfully/domain/recipes.py` — `ThumbnailCrop` becomes:

```python
@dataclass(frozen=True, slots=True)
class ThumbnailCrop:
    x: Decimal = Decimal("0.000000")
    y: Decimal = Decimal("0.000000")
    width: Decimal = Decimal("1.000000")
    height: Decimal = Decimal("1.000000")
```

Validation: `0 <= x <= 1`, `0 <= y <= 1`, `0 < width <= 1`, `0 < height <= 1`,
`x + width <= 1`, `y + height <= 1`. Serialized as canonical fixed-decimal strings (6 places),
matching existing contract style.

The 4:3 aspect ratio is enforced in the editor UI only. Fixed 6-place decimals cannot represent
`h * 4/3` for every height, and strict server-side aspect validation would reject valid rounded
rectangles. The server guarantees bounds only.

### API schema

`ThumbnailCropRequest` fields become `x`, `y`, `width`, `height` with camelCase aliases
(`focalX`/`focalY`/`zoom` removed). The crop rides the same routes as today — recipe create/update
via `RecipeWriteRequest.thumbnail_crop`, multipart photo upload form field `thumbnailCrop`,
source-photo replace, PDF-thumbnail attach, and import confirm payloads. Out-of-bounds,
zero/negative size, overflow sums, and non-decimal input return 422 as today. The frontend client
is regenerated from OpenAPI via `scripts/generate-api-client.ps1`.

### Database

Alembic migration:

- Drop `recipes.thumbnail_focal_x`, `thumbnail_focal_y`, `thumbnail_zoom`.
- Add `recipes.thumbnail_x`, `thumbnail_y`, `thumbnail_width`, `thumbnail_height` as
  `Numeric(9,6) NOT NULL` with server defaults `0 / 0 / 1 / 1`.

No data carryover.

## Rendering

One universal CSS pattern driven by custom properties set in `RecipeMedia.tsx`
(`--crop-x/y/w/h`), replacing today's `object-position`/`scale()` rules in `features.css` and
`home.css`:

```css
/* container: position: relative; overflow: hidden */
.recipe-media img {
  position: absolute;
  width:  calc(100% / var(--crop-w));
  height: calc(100% / var(--crop-h));
  left:   calc(var(--crop-x) / var(--crop-w) * -100%);
  top:    calc(var(--crop-y) / var(--crop-h) * -100%);
  object-fit: cover;
}
```

The math maps the selected rect onto the container exactly: the image renders at
`container / rect` size, offset so the rect's top-left lands on the container origin. For the
default full-image rect it degenerates to a plain cover-fitted image — identical to current
behavior. Every surface (cards, hero, home tiles, draft preview, editor preview, import dialog)
shows the same chosen region; non-4:3 containers re-cover symmetrically.

## Editor UX (`ThumbnailCropEditor` rewrite)

Mounted in the same two places (editor Finish step, import dialog).

- **Viewport**: the full source image rendered contained (`object-fit: contain`) on a neutral
  backdrop; the 4:3 selection rectangle overlays it with the outside area dimmed.
- **Move**: drag inside the frame pans the selection, clamped to image bounds.
- **Resize**: four corner handles, aspect-locked to 4:3, clamped to bounds, minimum selection size
  ~15% of the image's smaller edge.
- **Reset**: restores the largest centered 4:3 fit for the current source aspect. For a 4:3 source
  this is the full image.
- **Initial selection**: when the stored crop is still the default full-image rect, the editor opens
  showing the largest centered 4:3 fit rather than a literal full-image overlay; applying without
  changes saves that fitted rectangle.
- **Keyboard**: the frame is focusable; arrow keys move the selection, Shift+arrow resizes;
  the accessible range-input fallback behind "Adjust framing" remains for precise numeric input.
- **Pure helpers**: new `frontend/src/features/recipes/thumbnailCrop.ts` exports
  `defaultFit(aspect)`, `move()`, `resizeCorner()`, clamp helpers, and 6-dp string rounding — no DOM
  dependencies, fully unit-testable.

## Backend persistence

Application modules swap field names (`recipes.py`, `recipe_photos.py`, `import_preview.py`);
import merge still preserves the existing crop; version guards and stale-hash rejection are
untouched. No new endpoint.

## Error handling

- Invalid rects (out of bounds, zero/negative size, sum overflow, malformed decimals) → 422 from
  Pydantic validation, consistent with existing crop errors.
- The editor clamps every interaction, so invalid states are unreachable through normal use.
- Missing/null crop on legacy payloads falls back to the default full-image rect.

## Testing

- Backend: update `test_recipe_api.py` contract test to round-trip rect values and assert 422 bound
  cases; extend `test_recipe_photo_service.py` to assert persisted columns; update import-preview
  coordinator fixtures to the new payload keys.
- Frontend: unit tests for `thumbnailCrop.ts` (default fit for wide/tall/square sources, move and
  resize clamping, aspect lock, rounding); component tests for drag-move, handle-resize aspect lock,
  Reset, and keyboard interaction; assert `RecipeMedia` emits correct CSS variables; update
  fixtures hardcoding old defaults.
- Full AGENTS.md verification gate: ruff format/check, mypy, pytest, frontend lint/typecheck/
  vitest/build.

## Docs

- Record an inspiration-review.md entry analyzing Immich's actual crop-editor interaction pattern
  and Cookfully's adopt/adapt decision.
- Update DESIGN.md where it references thumbnail framing controls.

## Rejected alternatives

- **Fixing the focal+zoom model**: least invasive, but cannot express an independently chosen exact
  region, and WYSIWYG depends on every render site duplicating cover-crop math correctly — the same
  failure mode that made the feature feel broken.
- **Backend-generated cropped derivatives**: most exact and fastest to serve, but contradicts the
  stored principle of persisting framing without rewriting original media and adds derivative
  lifecycle machinery unnecessary at self-host scale.
