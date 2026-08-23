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
  if (rect.width <= 0 || rect.height <= 0) return { ...FULL_RECT };
  return {
    x: clamp(rect.x, 0, 1),
    y: clamp(rect.y, 0, 1),
    width: Math.min(rect.width, 1),
    height: Math.min(rect.height, 1),
  };
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
  const anchorX = clamp(anchorLeft ? rect.x : rect.x + rect.width, 0, 1);
  const anchorY = clamp(anchorTop ? rect.y : rect.y + rect.height, 0, 1);
  const rawWidth = Math.abs(pointerX - anchorX);
  const rawHeight = Math.abs(pointerY - anchorY);
  let width = rawWidth / CROP_ASPECT > rawHeight ? rawWidth : rawHeight * CROP_ASPECT;
  const availableWidth = anchorLeft ? 1 - anchorX : anchorX;
  const availableHeight = anchorTop ? 1 - anchorY : anchorY;
  const maxWidth = Math.min(availableWidth, availableHeight * CROP_ASPECT);
  const lower = Math.min(MIN_CROP_SIZE, maxWidth);
  width = clamp(width, lower, Math.max(lower, maxWidth));
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
  const lower = Math.min(MIN_CROP_SIZE, maxWidth);
  const clamped = clamp(width, lower, Math.max(lower, maxWidth));
  return { x: rect.x, y: rect.y, width: clamped, height: clamped / CROP_ASPECT };
}
