import { apiRequest } from "../recipes/api";
import type {
  FoodSearchResponse,
  OwnerFood,
  OwnerFoodUpdate,
  OwnerFoodWrite,
} from "./types";
import type { JobAccepted } from "../recipes/types";

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

  ingredientCandidates(recipeId: string, ingredientId: string, query = "") {
    const params = new URLSearchParams();
    if (query.trim()) params.set("q", query.trim());
    const suffix = params.size ? `?${params.toString()}` : "";
    return apiRequest<FoodSearchResponse>(
      `/recipes/${recipeId}/ingredients/${ingredientId}/candidates${suffix}`
    );
  },

  async selectIngredientFood(
    recipeId: string,
    ingredientId: string,
    foodReferenceId: string,
    rememberMatch = true,
  ): Promise<JobAccepted> {
    await apiRequest(`/recipes/${recipeId}/nutrition/corrections`, {
      method: "POST",
      idempotent: true,
      body: JSON.stringify({
        ingredientId,
        field: "food_reference",
        referenceIdValue: foodReferenceId,
        reason: "Selected in recipe editor",
        rememberMatch,
      }),
    });
    return apiRequest(`/recipes/${recipeId}/nutrition/recalculate`, {
      method: "POST",
      idempotent: true,
      body: JSON.stringify({ resetCorrections: false }),
    });
  },

  async selectOwnerFood(
    recipeId: string,
    ingredientId: string,
    ownerFoodId: string,
    rememberMatch = true,
  ): Promise<JobAccepted> {
    await apiRequest(`/recipes/${recipeId}/ingredients/${ingredientId}/owner-food/${ownerFoodId}`, {
      method: "POST",
      idempotent: true,
      body: JSON.stringify({ rememberMatch }),
    });
    return apiRequest(`/recipes/${recipeId}/nutrition/recalculate`, {
      method: "POST",
      idempotent: true,
      body: JSON.stringify({ resetCorrections: false }),
    });
  },
};
