import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { RecipeFallbackArt } from "../RecipeFallbackArt";

describe("RecipeFallbackArt", () => {
  it("keeps specific breakfast cues while varying generic savory recipes", () => {
    const titles = [
      "Rice Paper Bacon",
      "Big Mac",
      "Soy Curl Chick’N",
      "Seitan Turkey Deli Slices",
      "Tofu Fried Chick’N",
      "Marry Me Tofu",
    ];
    const { container } = render(
      <>
        <RecipeFallbackArt title="Exact oats" />
        {titles.map((title) => <RecipeFallbackArt key={title} title={title} />)}
      </>,
    );

    expect(container.querySelector('[data-fallback-kind="breakfast"]')).toBeInTheDocument();
    const savoryKinds = [...container.querySelectorAll(".recipe-fallback-art")]
      .slice(1)
      .map((image) => image.getAttribute("data-fallback-kind"));
    expect(new Set(savoryKinds).size).toBeGreaterThan(1);
  });
});
