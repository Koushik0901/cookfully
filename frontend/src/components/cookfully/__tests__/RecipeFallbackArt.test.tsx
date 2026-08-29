import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { RecipeFallbackArt } from "../RecipeFallbackArt";

describe("RecipeFallbackArt", () => {
  it("spreads every title across the fallback collection", () => {
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
        {titles.map((title) => <RecipeFallbackArt key={title} title={title} />)}
      </>,
    );

    const savoryKinds = [...container.querySelectorAll(".recipe-fallback-art")]
      .map((image) => image.getAttribute("data-fallback-kind"));
    expect(new Set(savoryKinds).size).toBeGreaterThan(1);
  });
});
