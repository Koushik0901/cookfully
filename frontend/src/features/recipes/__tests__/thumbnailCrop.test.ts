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
