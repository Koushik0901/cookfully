import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { BrandMark } from "../index";

describe("BrandMark", () => {
  it("renders new mark with aria-hidden", () => {
    const { container } = render(<BrandMark />);
    const img = container.querySelector("img.brand-mark") as HTMLImageElement;
    expect(img).toBeTruthy();
    expect(img.getAttribute("aria-hidden")).toBe("true");
    expect(img.getAttribute("alt")).toBe("");
    expect(img.src).toMatch(/cookfully-mark|cookfully-logo/);
  });
});
