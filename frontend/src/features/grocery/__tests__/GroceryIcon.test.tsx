import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { GroceryIcon, categoryFor } from "../../../components/GroceryIcon";

describe("GroceryIcon", () => {
  it("maps dairy keywords", () => { expect(categoryFor("Whole Milk 1L")).toBe("dairy"); });
  it("maps produce", () => { expect(categoryFor("Brown Rice")).toBe("pantry"); expect(categoryFor("Fresh Spinach")).toBe("produce"); });
  it("fallback other", () => { expect(categoryFor("")).toBe("other"); expect(categoryFor("xyz abc")).toBe("other"); });
  it("renders svg aria-hidden", () => {
    const { container } = render(<GroceryIcon name="milk" />);
    expect(container.querySelector("svg")).toHaveAttribute("aria-hidden", "true");
  });
  it("bakery/meat/frozen/beverage/household", () => {
    expect(categoryFor("Sourdough Bread")).toBe("bakery");
    expect(categoryFor("Chicken Breast")).toBe("meat");
    expect(categoryFor("Frozen Peas")).toBe("frozen");
    expect(categoryFor("Orange Juice")).toBe("beverage");
    expect(categoryFor("Paper Towels")).toBe("household");
  });
});
