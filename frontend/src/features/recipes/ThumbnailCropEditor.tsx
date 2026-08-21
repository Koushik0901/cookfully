import { type PointerEvent, useRef, useState } from "react";

import type { ThumbnailCropWrite } from "./types";

const defaultCrop: ThumbnailCropWrite = { focalX: "0.5", focalY: "0.5", zoom: "1" };

export function ThumbnailCropEditor({
  imageUrl,
  value = defaultCrop,
  onChange,
}: {
  imageUrl: string;
  value?: ThumbnailCropWrite;
  onChange: (value: ThumbnailCropWrite) => void;
}) {
  const [focused, setFocused] = useState(false);
  const drag = useRef<{ mode: "move" | "resize"; x: number; y: number; focalX: number; focalY: number; zoom: number; width: number; height: number } | null>(null);
  const crop = { ...defaultCrop, ...value };
  const update = (key: keyof ThumbnailCropWrite, next: string) => onChange({ ...crop, [key]: next });
  const beginDrag = (event: PointerEvent<HTMLDivElement>) => {
    if (event.button !== 0) return;
    const bounds = event.currentTarget.getBoundingClientRect();
    const mode = event.target instanceof Element && event.target.closest("[data-crop-resize]") ? "resize" : "move";
    drag.current = { mode, x: event.clientX, y: event.clientY, focalX: Number(crop.focalX), focalY: Number(crop.focalY), zoom: Number(crop.zoom), width: bounds.width, height: bounds.height };
    event.currentTarget.setPointerCapture(event.pointerId);
  };
  const moveDrag = (event: PointerEvent<HTMLDivElement>) => {
    if (!drag.current) return;
    if (drag.current.mode === "resize") {
      const nextZoom = Math.min(3, Math.max(1, drag.current.zoom + (event.clientX - drag.current.x) / drag.current.width * 2));
      onChange({ ...crop, zoom: nextZoom.toFixed(2) });
      return;
    }
    const nextX = Math.min(1, Math.max(0, drag.current.focalX - (event.clientX - drag.current.x) / drag.current.width));
    const nextY = Math.min(1, Math.max(0, drag.current.focalY - (event.clientY - drag.current.y) / drag.current.height));
    onChange({ ...crop, focalX: nextX.toFixed(6), focalY: nextY.toFixed(6) });
  };
  return (
    <section className="thumbnail-crop-editor" aria-label="Adjust thumbnail crop">
      <div className="thumbnail-crop-editor__preview" onPointerDown={beginDrag} onPointerMove={moveDrag} onPointerUp={() => { drag.current = null; }} onPointerCancel={() => { drag.current = null; }}>
        <img
          src={imageUrl}
          alt=""
          style={{
            objectPosition: `${Number(crop.focalX) * 100}% ${Number(crop.focalY) * 100}%`,
            transform: `scale(${crop.zoom})`,
          }}
        />
        <div className="thumbnail-crop-editor__frame" aria-label="Crop frame" style={{ transform: `scale(${(1 / Math.max(1, Number(crop.zoom))).toFixed(3)})` }}>
          <span className="thumbnail-crop-editor__handle thumbnail-crop-editor__handle--nw" data-crop-resize="nw" />
          <span className="thumbnail-crop-editor__handle thumbnail-crop-editor__handle--ne" data-crop-resize="ne" />
          <span className="thumbnail-crop-editor__handle thumbnail-crop-editor__handle--sw" data-crop-resize="sw" />
          <span className="thumbnail-crop-editor__handle thumbnail-crop-editor__handle--se" data-crop-resize="se" />
        </div>
      </div>
      <div className="thumbnail-crop-editor__controls">
        <button type="button" className="text-link" onClick={() => setFocused((open) => !open)} aria-expanded={focused}>
          {focused ? "Hide framing controls" : "Adjust framing"}
        </button>
        {focused ? (
          <div className="thumbnail-crop-editor__sliders">
            <label>Horizontal focus<input type="range" min="0" max="1" step="0.01" value={String(crop.focalX)} onChange={(event) => update("focalX", event.currentTarget.value)} /></label>
            <label>Vertical focus<input type="range" min="0" max="1" step="0.01" value={String(crop.focalY)} onChange={(event) => update("focalY", event.currentTarget.value)} /></label>
            <label>Zoom<input type="range" min="1" max="3" step="0.01" value={String(crop.zoom)} onChange={(event) => update("zoom", event.currentTarget.value)} /></label>
          </div>
        ) : null}
      </div>
    </section>
  );
}
