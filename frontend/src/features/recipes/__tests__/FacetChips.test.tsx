import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { FacetChips } from "../FacetChips";
import { facetLabel } from "../facets";

afterEach(cleanup);

describe("recipe facets", () => {
  it("labels confident tags plainly and unsure ones as probable", () => {
    expect(facetLabel({ key: "vegetarian", probability: "0.93" })).toBe("Vegetarian");
    expect(facetLabel({ key: "freezes_well", probability: "0.6" })).toBe("Probably freezes well");
  });

  it("words diet tags as certain from 0.7 and other tags from 0.8, matching the server", () => {
    expect(facetLabel({ key: "vegetarian", probability: "0.7" })).toBe("Vegetarian");
    expect(facetLabel({ key: "gluten_free", probability: "0.6999" })).toBe("Probably gluten-free");
    expect(facetLabel({ key: "dairy_free", probability: "0.75" })).toBe("Dairy-free");
    expect(facetLabel({ key: "reheats_well", probability: "0.75" })).toBe("Probably reheats well");
    expect(facetLabel({ key: "reheats_well", probability: "0.8" })).toBe("Reheats well");
  });

  it("renders known tags, optionally filtered, and nothing when empty", () => {
    const facets = [
      { key: "cuisine:thai", probability: "0.9" },
      { key: "keeps_4_days", probability: "0.85" },
      { key: "unknown:thing", probability: "0.99" },
    ];
    const { rerender, container } = render(<FacetChips facets={facets} />);
    expect(screen.getByRole("list", { name: "Recipe tags" })).toHaveTextContent("ThaiKeeps 4 days");
    rerender(<FacetChips facets={facets} keys={["keeps_4_days"]} />);
    expect(screen.getAllByRole("listitem")).toHaveLength(1);
    rerender(<FacetChips facets={[]} />);
    expect(container).toBeEmptyDOMElement();
  });
});
