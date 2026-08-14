import { apiRequest } from "../recipes/api";
import type {
  FoodSearchResponse,
  OwnerFood,
  OwnerFoodUpdate,
  OwnerFoodWrite,
} from "./types";

export const foodsApi = {
  search(query: string) {
    const params = new URLSearchParams({ q: query });
    return apiRequest<FoodSearchResponse>(`/foods/search?${params.toString()}`);
  },

  listUserFoods(query?: string) {
    const params = new URLSearchParams();
    if (query?.trim()) params.set("q", query.trim());
    const suffix = params.size ? `?${params.toString()}` : "";
    return apiRequest<OwnerFood[]>(`/foods/user${suffix}`);
  },

  createUserFood(value: OwnerFoodWrite) {
    return apiRequest<OwnerFood>("/foods/user", {
      method: "POST",
      body: JSON.stringify(value),
    });
  },

  updateUserFood(foodId: string, value: OwnerFoodUpdate) {
    return apiRequest<OwnerFood>(`/foods/user/${foodId}`, {
      method: "PUT",
      version: value.expectedVersion,
      body: JSON.stringify(value),
    });
  },

  deleteUserFood(foodId: string, expectedVersion: number) {
    return apiRequest<void>(`/foods/user/${foodId}?expectedVersion=${expectedVersion}`, {
      method: "DELETE",
    });
  },

  ingredientCandidates(recipeId: string, ingredientId: string) {
    return apiRequest<FoodSearchResponse>(
      `/recipes/${recipeId}/ingredients/${ingredientId}/candidates`
    );
  },

  async selectIngredientFood(recipeId: string, ingredientId: string, foodReferenceId: string) {
    await apiRequest(`/recipes/${recipeId}/nutrition/corrections`, {
      method: "POST",
      idempotent: true,
      body: JSON.stringify({
        ingredientId,
        field: "food_reference",
        referenceIdValue: foodReferenceId,
        reason: "Selected in recipe editor",
      }),
    });
    return apiRequest(`/recipes/${recipeId}/nutrition/recalculate`, {
      method: "POST",
      idempotent: true,
      body: JSON.stringify({ resetCorrections: false }),
    });
  },
};
