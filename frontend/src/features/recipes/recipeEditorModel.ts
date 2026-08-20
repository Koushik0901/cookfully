import type { RecipeDetail, RecipeWrite, ThumbnailCropWrite } from "./types";

export interface EditorIngredientRow {
  key: string;
  originalText: string;
  quantityMin: string;
  quantityMax: string;
  unit: string;
  food: string;
  preparation: string;
  optional: boolean;
}

export interface EditorMethodStep {
  key: string;
  text: string;
}

export interface EditorBlock {
  key: string;
  title: string;
  ingredients: EditorIngredientRow[];
  instructions: EditorMethodStep[];
}

let editorSequence = 0;
function key(prefix: string) {
  editorSequence += 1;
  return `${prefix}-${editorSequence}`;
}

export function newIngredient(value: Partial<Omit<EditorIngredientRow, "key">> = {}): EditorIngredientRow {
  return {
    key: key("ingredient"),
    originalText: value.originalText ?? "",
    quantityMin: value.quantityMin ?? "",
    quantityMax: value.quantityMax ?? "",
    unit: value.unit ?? "",
    food: value.food ?? "",
    preparation: value.preparation ?? "",
    optional: value.optional ?? false,
  };
}

export function newMethodStep(text = ""): EditorMethodStep {
  return { key: key("step"), text };
}

export function newEditorBlock(title = ""): EditorBlock {
  return { key: key("block"), title, ingredients: [newIngredient()], instructions: [newMethodStep()] };
}

export function editorBlocksFromRecipe(recipe: RecipeDetail): EditorBlock[] {
  const blockFor = (sectionId: string | null, title: string, blockKey: string): EditorBlock => {
    const ingredients = recipe.ingredients
      .filter((item) => (item.sectionId ?? null) === sectionId)
      .sort((a, b) => a.position - b.position)
      .map((item) => newIngredient({
        originalText: item.originalText,
        quantityMin: item.quantityMin ?? "",
        quantityMax: item.quantityMax ?? "",
        unit: item.unit ?? "",
        food: item.food ?? "",
        preparation: item.preparation ?? "",
        optional: item.optional,
      }));
    const instructions = recipe.instructions
      .filter((item) => (item.sectionId ?? null) === sectionId)
      .sort((a, b) => a.position - b.position)
      .map((item) => newMethodStep(item.text));
    return {
      key: blockKey,
      title,
      ingredients: ingredients.length ? ingredients : [newIngredient()],
      instructions: instructions.length ? instructions : [newMethodStep()],
    };
  };

  return [
    blockFor(null, "", "block-main"),
    ...(recipe.sections ?? []).map((section) => blockFor(section.id, section.title, `section-${section.id}`)),
  ];
}

export function splitPastedRows(value: string): string[] {
  return value
    .replace(/\r\n?/g, "\n")
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
}

export function moveAt<T>(items: T[], from: number, to: number): T[] {
  if (from === to || from < 0 || to < 0 || from >= items.length || to >= items.length) return items;
  const next = [...items];
  const [item] = next.splice(from, 1);
  next.splice(to, 0, item);
  return next;
}

export function previewBlocks(blocks: EditorBlock[]) {
  return blocks.map((block) => ({
    key: block.key,
    title: block.title,
    ingredients: block.ingredients.filter((item) => item.originalText.trim()).map((item) => item.originalText).join("\n"),
    instructions: block.instructions.filter((step) => step.text.trim()).map((step) => step.text).join("\n"),
  }));
}

export function serializeRecipeBlocks(
  blocks: EditorBlock[],
  identity: {
    title: string;
    description: string;
    sourceUrl: string;
    yieldQuantity: string;
    yieldUnit: string;
    prepMinutes?: string;
    cookMinutes?: string;
    thumbnailCrop: ThumbnailCropWrite;
  },
): RecipeWrite {
  const sectionBlocks = blocks.filter((block) => block.title.trim());
  const sectionTitles = sectionBlocks.map((block) => block.title.trim());
  const sectionIndex = (block: EditorBlock) => block.title.trim() ? sectionBlocks.indexOf(block) : null;

  return {
    title: identity.title.trim(),
    description: identity.description.trim() || null,
    sourceUrl: identity.sourceUrl.trim() || null,
    yieldQuantity: identity.yieldQuantity,
    yieldUnit: identity.yieldUnit.trim() || "servings",
    prepMinutes: identity.prepMinutes?.trim() ? Number(identity.prepMinutes) : null,
    cookMinutes: identity.cookMinutes?.trim() ? Number(identity.cookMinutes) : null,
    sections: sectionTitles.map((title) => ({ title })),
    ingredients: blocks.flatMap((block) => block.ingredients
      .filter((item) => item.originalText.trim())
      .map((item) => ({
        originalText: item.originalText,
        quantityMin: item.quantityMin || null,
        quantityMax: item.quantityMax || null,
        unit: item.unit || null,
        food: item.food || null,
        preparation: item.preparation || null,
        optional: item.optional,
        section: sectionIndex(block),
      }))),
    instructions: blocks.flatMap((block) => block.instructions
      .filter((step) => step.text.trim())
      .map((step) => ({ text: step.text, section: sectionIndex(block) }))),
    thumbnailCrop: identity.thumbnailCrop,
  };
}
