import { type KeyboardEvent, type PointerEvent, useState, useRef } from "react";

import { type Corner, CROP_ASPECT, MIN_CROP_SIZE, defaultFit, isDefaultRect, moveRect, parseRect, resizeToPoint, serializeRect, setWidth } from "./thumbnailCrop";
import type { ThumbnailCropWrite } from "./types";

const HANDLES: Corner[] = ["nw", "ne", "sw", "se"];
const DEFAULT_RECT = { x: "0", y: "0", width: "1", height: "1" } as const;

export function ThumbnailCropEditor({
  imageUrl,
  value,
  onChange,
}: {
  imageUrl: string;
  value?: ThumbnailCropWrite;
  onChange: (value: ThumbnailCropWrite) => void;
}) {
  const [aspect, setAspect] = useState(CROP_ASPECT);
  const [slidersOpen, setSlidersOpen] = useState(false);
  const drag = useRef<{ mode: "move" | Corner; startX: number; startY: number; rect: ReturnType<typeof parseRect> } | null>(null);

  const stored = parseRect(value ?? DEFAULT_RECT);
  const crop = isDefaultRect(stored) ? defaultFit(aspect) : stored;

  const beginDrag = (event: PointerEvent<HTMLDivElement>) => {
    if (event.button !== 0) return;
    const handle = event.target instanceof Element ? event.target.closest("[data-crop-resize]") : null;
    drag.current = { mode: (handle?.getAttribute("data-crop-resize") as Corner | null) ?? "move", startX: event.clientX, startY: event.clientY, rect: crop };
    event.currentTarget.setPointerCapture?.(event.pointerId);
  };
  const moveDrag = (event: PointerEvent<HTMLDivElement>) => {
    const current = drag.current;
    if (!current) return;
    const bounds = event.currentTarget.getBoundingClientRect();
    if (bounds.width === 0 || bounds.height === 0) return;
    if (current.mode === "move") {
      onChange(serializeRect(moveRect(current.rect, (event.clientX - current.startX) / bounds.width, (event.clientY - current.startY) / bounds.height)));
      return;
    }
    const pointerX = Math.min(1, Math.max(0, (event.clientX - bounds.left) / bounds.width));
    const pointerY = Math.min(1, Math.max(0, (event.clientY - bounds.top) / bounds.height));
    onChange(serializeRect(resizeToPoint(current.rect, current.mode, pointerX, pointerY)));
  };
  const endDrag = () => {
    drag.current = null;
  };

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const step = event.shiftKey ? 0.05 : 0.01;
    let next: ReturnType<typeof parseRect> | null = null;
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
    inset: "auto",
  };

  return (
    <section className="thumbnail-crop-editor" aria-label="Adjust thumbnail crop">
      <div className="thumbnail-crop-editor__preview">
        <img
          src={imageUrl}
          alt=""
          draggable={false}
          onLoad={(event) => {
            const image = event.currentTarget;
            if (image.naturalWidth > 0 && image.naturalHeight > 0) setAspect(image.naturalWidth / image.naturalHeight);
          }}
        />
        <div
          role="group"
          aria-label="Crop area"
          className="thumbnail-crop-editor__stage"
          onPointerDown={beginDrag}
          onPointerMove={moveDrag}
          onPointerUp={endDrag}
          onPointerCancel={endDrag}
        >
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
