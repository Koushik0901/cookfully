import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { FoodCategoryIcon, categoryFor } from "../FoodCategoryIcon";

const fixtures = [
  ["spinach", "leafy-greens"],
  ["rice", "grains-rice"],
  ["milk", "dairy-milk"],
  ["apple", "fruit"],
  ["tomato", "vegetables"],
  ["pasta sauce", "pantry-sauce"],
  ["bread", "bread-bakery"],
  ["chicken", "protein-chicken"],
  ["basil", "herbs-spices"],
  ["coffee", "beverages-drinks"],
  ["salmon", "seafood"],
  ["eggs", "eggs"],
  ["granola bar", "snacks"],
] as const;

describe("FoodCategoryIcon", () => {
  it.each(fixtures)("maps %s to %s", (name, category) => {
    expect(categoryFor(name)).toBe(category);
    const { container } = render(<FoodCategoryIcon name={name} />);
    const image = container.querySelector("img");
    expect(image).toHaveAttribute("src", `/media/grocery-icons/${category}-64.png`);
    expect(image).toHaveAttribute("srcset", expect.stringContaining(`${category}.png 256w`));
    expect(image).toHaveAttribute("alt", "");
    expect(image).toHaveAttribute("aria-hidden", "true");
  });

  it("uses the pantry sauce fallback and size class", () => {
    const { container } = render(<FoodCategoryIcon name="unclassified item" size="row" />);
    expect(container.querySelector(".grocery-icon--pantry-sauce.grocery-icon--size-row")).toBeTruthy();
    const img = container.querySelector("img");
    expect(img).toHaveAttribute("src", "/media/grocery-icons/pantry-sauce-64.png");
    expect(img?.getAttribute("srcset")).toContain("pantry-sauce.png 256w");
  });

  it("keeps specific terms ahead of broad terms", () => {
    expect(categoryFor("eggplant")).toBe("vegetables");
    expect(categoryFor("milkshake")).toBe("beverages-drinks");
    expect(categoryFor("frozen vegetables")).toBe("vegetables");
  });

  it("normalizes plural and case", () => {
    expect(categoryFor("SPINACH")).toBe("leafy-greens");
    expect(categoryFor("Tomatoes")).toBe("vegetables");
    expect(categoryFor("Apples")).toBe("fruit");
    expect(categoryFor("EGGS")).toBe("eggs");
    expect(categoryFor("  milk  ")).toBe("dairy-milk");
    expect(categoryFor("CHICKEN")).toBe("protein-chicken");
  });

  it("exposes size and accessibility classes", () => {
    const { container: compact } = render(<FoodCategoryIcon name="apple" size="compact" />);
    expect(compact.querySelector("img.grocery-icon.grocery-icon--fruit.grocery-icon--size-compact")).toBeTruthy();

    const { container: tile } = render(<FoodCategoryIcon name="apple" size="tile" className="extra" />);
    const tileImg = tile.querySelector("img");
    expect(tileImg?.className).toContain("grocery-icon--size-tile");
    expect(tileImg?.className).toContain("extra");
    expect(tileImg).toHaveAttribute("alt", "");
    expect(tileImg).toHaveAttribute("aria-hidden", "true");

    const { container: row } = render(<FoodCategoryIcon name="apple" size="row" />);
    expect(row.querySelector("img.grocery-icon--size-row")).toBeTruthy();
  });

  it("prevents substring misclassification", () => {
    // egg in veggie/eggplant should not map to eggs
    expect(categoryFor("eggplant")).toBe("vegetables");
    expect(categoryFor("veggie mix")).toBe("pantry-sauce");
    // milk in milkshake should not map to dairy-milk
    expect(categoryFor("milkshake")).toBe("beverages-drinks");
  });
});
