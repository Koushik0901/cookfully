import type { components } from "../../app/api/generated/schema";

export type PantryItem = components["schemas"]["PantryItem"] & {
  purchasedAt?: string | null;
  expirySource?: "auto" | "label" | "manual" | null;
};
export type PantryItemWrite = components["schemas"]["PantryItemWrite"];
export type PantryRecipeMatch = components["schemas"]["PantryRecipeMatch"];
export type PantryDeduction = components["schemas"]["PantryDeduction"];
export type PantryDeductionApply = components["schemas"]["PantryDeductionApply"];
