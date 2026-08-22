import { fireEvent, render, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ThumbnailCropEditor } from "../ThumbnailCropEditor";
import { defaultFit, parseRect, serializeRect } from "../thumbnailCrop";

function setup(value?: Parameters<typeof ThumbnailCropEditor>[0]["value"]) {
  const onChange = vi.fn();
  const view = render(<ThumbnailCropEditor imageUrl="https://example.com/photo.webp" value={value} onChange={onChange} />);
  const image = view.container.querySelector("img")!;
  Object.defineProperty(image, "naturalWidth", { value: 1600 });
  Object.defineProperty(image, "naturalHeight", { value: 900 });
  fireEvent(image, new Event("load"));
  fireEvent.click(view.getByRole("button", { name: "Adjust framing" }));
  const q = {
    frame: () => view.container.querySelector<HTMLElement>(".thumbnail-crop-editor__frame")!,
    stage: () => view.container.querySelector<HTMLElement>(".thumbnail-crop-editor__stage")!,
    button: (name: string) => within(view.container).getByRole("button", { name }),
    slider: (name: string) => within(view.container).getByRole("slider", { name }) as HTMLInputElement,
    handle: (corner: string) => view.container.querySelector<HTMLElement>(`[data-crop-resize='${corner}']`)!,
  };
  return { onChange, q };
}

describe("ThumbnailCropEditor", () => {
  it("shows the largest centered 4:3 fit for a wide image when the stored rect is the default", () => {
    const { q } = setup({ x: "0", y: "0", width: "1", height: "1" });
    const fit = defaultFit(16 / 9);
    expect(q.slider("Horizontal position").valueAsNumber).toBeCloseTo(fit.x, 6);
    expect(q.slider("Vertical position").valueAsNumber).toBeCloseTo(fit.y, 6);
    expect(Number(q.frame().style.width.replace("%", "")) / 100).toBeCloseTo(fit.width, 6);
  });

  it("resets to the fitted rect", () => {
    const { onChange, q } = setup();
    fireEvent.click(q.button("Reset"));
    expect(onChange).toHaveBeenLastCalledWith(serializeRect(defaultFit(16 / 9)));
  });

  it("moves the selection with arrow keys", () => {
    const { onChange, q } = setup({ x: "0.200000", y: "0.100000", width: "0.500000", height: "0.750000" });
    fireEvent.keyDown(q.frame(), { key: "ArrowRight" });
    const call = onChange.mock.lastCall![0];
    expect(Number(call.x)).toBeCloseTo(0.21, 6);
    expect(Number(call.y)).toBeCloseTo(0.1, 6);
  });

  it("resizes with shift+arrow keys keeping the 4:3 aspect", () => {
    const { onChange, q } = setup({ x: "0.100000", y: "0.100000", width: "0.400000", height: "0.300000" });
    fireEvent.keyDown(q.frame(), { key: "ArrowRight", shiftKey: true });
    const call = onChange.mock.lastCall![0];
    expect(Number(call.width)).toBeGreaterThan(0.4);
    expect(parseRect(call).height / parseRect(call).width).toBeCloseTo(0.75, 6);
  });

  it("commits slider changes", () => {
    const { onChange, q } = setup({ x: "0.000000", y: "0.000000", width: "0.750000", height: "1.000000" });
    fireEvent.change(q.slider("Horizontal position"), { target: { value: "0.12" } });
    expect(Number(onChange.mock.lastCall![0].x)).toBeCloseTo(0.12, 6);
  });

  it("drags the selection via pointer move", () => {
    const { onChange, q } = setup({ x: "0.200000", y: "0.200000", width: "0.500000", height: "0.375000" });
    const stage = q.stage();
    stage.getBoundingClientRect = () => ({ left: 0, top: 0, width: 100, height: 100 } as DOMRect);
    const pointer = (type: string, init: MouseEventInit) => stage.dispatchEvent(new MouseEvent(type, { bubbles: true, ...init }));
    pointer("pointerdown", { button: 0, clientX: 10, clientY: 10 });
    pointer("pointermove", { clientX: 15, clientY: 12 });
    pointer("pointerup", {});
    const call = onChange.mock.lastCall![0];
    expect(Number(call.x)).toBeCloseTo(0.25, 6);
    expect(Number(call.y)).toBeCloseTo(0.22, 6);
  });

  it("resizes from a corner handle keeping the aspect locked", () => {
    const { onChange, q } = setup({ x: "0.100000", y: "0.100000", width: "0.400000", height: "0.300000" });
    const stage = q.stage();
    stage.getBoundingClientRect = () => ({ left: 0, top: 0, width: 100, height: 100 } as DOMRect);
    const pointer = (type: string, init: MouseEventInit) => q.handle("se").dispatchEvent(new MouseEvent(type, { bubbles: true, ...init }));
    pointer("pointerdown", { button: 0, clientX: 50, clientY: 40 });
    stage.dispatchEvent(new MouseEvent("pointermove", { bubbles: true, clientX: 80, clientY: 70 }));
    const call = onChange.mock.lastCall![0];
    expect(parseRect(call).height / parseRect(call).width).toBeCloseTo(0.75, 6);
    expect(parseRect(call).x).toBeCloseTo(0.1, 6);
    expect(parseRect(call).y).toBeCloseTo(0.1, 6);
  });

  it("clamps movement inside the image bounds", () => {
    const { onChange, q } = setup({ x: "0.500000", y: "0.500000", width: "0.500000", height: "0.375000" });
    const stage = q.stage();
    stage.getBoundingClientRect = () => ({ left: 0, top: 0, width: 100, height: 100 } as DOMRect);
    const pointer = (type: string, init: MouseEventInit) => stage.dispatchEvent(new MouseEvent(type, { bubbles: true, ...init }));
    pointer("pointerdown", { button: 0, clientX: 10, clientY: 10 });
    pointer("pointermove", { clientX: 500, clientY: 500 });
    const call = onChange.mock.lastCall![0];
    expect(Number(call.x)).toBeCloseTo(0.5, 6);
    expect(Number(call.y)).toBeCloseTo(0.625, 6);
  });
});
