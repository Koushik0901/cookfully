import { apiRequest } from "../recipes/api";
import type { GroceryItem, GroceryItemCreate, GroceryItemWrite, GroceryList } from "./types";

export const groceryApi = {
  get(weekStart: string) {
    return apiRequest<GroceryList>(`/meal-plans/${weekStart}/grocery-list`);
  },
  regenerate(weekStart: string) {
    return apiRequest<GroceryList>(`/meal-plans/${weekStart}/grocery-list`, {
      method: "POST",
      idempotent: true,
    });
  },
  create(weekStart: string, value: GroceryItemCreate) {
    return apiRequest<GroceryItem>(`/meal-plans/${weekStart}/grocery-list/items`, {
      method: "POST",
      idempotent: true,
      body: JSON.stringify(value),
    });
  },
  update(itemId: string, version: number, value: GroceryItemWrite) {
    return apiRequest<GroceryItem>(`/grocery-items/${itemId}`, {
      method: "PATCH",
      idempotent: true,
      version,
      body: JSON.stringify(value),
    });
  },
  remove(itemId: string, version: number) {
    return apiRequest<void>(`/grocery-items/${itemId}`, {
      method: "DELETE",
      idempotent: true,
      version,
    });
  },
};

