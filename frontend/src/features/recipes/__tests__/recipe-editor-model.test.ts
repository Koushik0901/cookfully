import { describe, expect, it } from "vitest";

import {
  moveAt,
  newEditorBlock,
  newIngredient,
  newMethodStep,
  serializeRecipeBlocks,
  splitPastedRows,
} from "../recipeEditorModel";

const identity = {
  title: "  Pantry pasta  ",
  description: "",
  sourceUrl: "",
  yieldQuantity: "2.500",
  yieldUnit: "servings",
  thumbnailCrop: { x: "0", y: "0", width: "1", height: "1" },
};

describe("structured recipe editor model", () => {
  it("splits a pasted list into scannable non-empty rows", () => {
    expect(splitPastedRows("1 chicken breast\r\n\r\n  2 cups rice  \nSalt to taste")).toEqual([
      "1 chicken breast",
      "2 cups rice",
      "Salt to taste",
    ]);
  });

  it("reorders rows without mutating their values", () => {
    const first = newIngredient({ originalText: "1 preserved lemon" });
    const second = newIngredient({ originalText: "2 cups chickpeas" });

    const original = [first, second];
    const moved = moveAt(original, 1, 0);

    expect(moved.map((item) => item.originalText)).toEqual(["2 cups chickpeas", "1 preserved lemon"]);
    expect(moved).not.toBe(original);
    expect(original.map((item) => item.originalText)).toEqual(["1 preserved lemon", "2 cups chickpeas"]);
  });

  it("serializes exact entered text and keeps same-named components distinct", () => {
    const main = {
      ...newEditorBlock(),
      ingredients: [newIngredient({ originalText: "  1 1/4 cups rolled oats  ", quantityMin: "1.250000", unit: "cup" })],
      instructions: [newMethodStep("Toast gently; do not brown.")],
    };
    const firstSauce = {
      ...newEditorBlock("Sauce"),
      ingredients: [newIngredient({ originalText: "1 tbsp tahini" })],
      instructions: [newMethodStep("Whisk until glossy.")],
    };
    const secondSauce = {
      ...newEditorBlock("Sauce"),
      ingredients: [newIngredient({ originalText: "1 tsp chilli oil", optional: true })],
      instructions: [newMethodStep("Spoon over at the table.")],
    };

    const value = serializeRecipeBlocks([main, firstSauce, secondSauce], identity);

    expect(value.title).toBe("Pantry pasta");
    expect(value.yieldQuantity).toBe("2.500");
    expect(value.sections).toEqual([{ title: "Sauce" }, { title: "Sauce" }]);
    expect(value.ingredients).toEqual([
      expect.objectContaining({ originalText: "  1 1/4 cups rolled oats  ", quantityMin: "1.250000", section: null }),
      expect.objectContaining({ originalText: "1 tbsp tahini", section: 0 }),
      expect.objectContaining({ originalText: "1 tsp chilli oil", optional: true, section: 1 }),
    ]);
    expect(value.instructions).toEqual([
      { text: "Toast gently; do not brown.", section: null },
      { text: "Whisk until glossy.", section: 0 },
      { text: "Spoon over at the table.", section: 1 },
    ]);
  });
});
