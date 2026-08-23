import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { RecipeMedia } from "../RecipeMedia";

describe("<RecipeMedia>", () => {
  it("emits crop rect custom properties from thumbnail metadata", () => {
    const { container } = render(
      <RecipeMedia
        recipe={{ title: "Test", imageUrl: "https://example.com/p.webp", thumbnailCrop: { x: "0.25", y: "0.125", width: "0.5", height: "0.375" } }}
      />,
    );
    const img = container.querySelector("img")!;
    expect(img.style.getPropertyValue("--crop-x")).toBe("0.25");
    expect(img.style.getPropertyValue("--crop-y")).toBe("0.125");
    expect(img.style.getPropertyValue("--crop-width")).toBe("0.5");
    expect(img.style.getPropertyValue("--crop-height")).toBe("0.375");
  });

  it("falls back to the full-image rect when no crop is stored", () => {
    const { container } = render(<RecipeMedia recipe={{ title: "Test", imageUrl: "https://example.com/p.webp" }} />);
    const img = container.querySelector("img")!;
    expect(img.style.getPropertyValue("--crop-x")).toBe("0");
    expect(img.style.getPropertyValue("--crop-y")).toBe("0");
    expect(img.style.getPropertyValue("--crop-width")).toBe("1");
    expect(img.style.getPropertyValue("--crop-height")).toBe("1");
  });
});
