import { apiRequest } from "../recipes/api";
import type {
  PantryDeduction,
  PantryDeductionApply,
  PantryItem,
  PantryItemWrite,
  PantryRecipeMatch,
} from "./types";

export const pantryApi = {
  list() {
    return apiRequest<PantryItem[]>("/pantry-items");
  },
  create(value: PantryItemWrite) {
    return apiRequest<PantryItem>("/pantry-items", {
      method: "POST",
      idempotent: true,
      body: JSON.stringify(value),
    });
  },
  update(itemId: string, version: number, value: PantryItemWrite) {
    return apiRequest<PantryItem>(`/pantry-items/${itemId}`, {
      method: "PATCH",
      idempotent: true,
      version,
      body: JSON.stringify(value),
    });
  },
  remove(itemId: string, version: number) {
    return apiRequest<void>(`/pantry-items/${itemId}`, {
      method: "DELETE",
      idempotent: true,
      version,
    });
  },
  search(query = "") {
    const params = new URLSearchParams();
    if (query.trim()) params.set("query", query.trim());
    const suffix = params.size ? `?${params.toString()}` : "";
    return apiRequest<PantryRecipeMatch[]>(`/pantry/recipe-matches${suffix}`);
  },
  applyDeductions(weekStart: string, value: PantryDeductionApply) {
    return apiRequest<PantryDeduction[]>(
      `/meal-plans/${weekStart}/grocery-list/pantry-deductions`,
      { method: "POST", idempotent: true, body: JSON.stringify(value) },
    );
  },
  reverseDeduction(deductionId: string, version: number) {
    return apiRequest<PantryDeduction>(`/pantry-deductions/${deductionId}`, {
      method: "DELETE",
      idempotent: true,
      version,
    });
  },
};
