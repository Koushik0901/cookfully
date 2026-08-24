import { apiRequest } from "../recipes/api";
import type { GroceryItem, GroceryItemCreate, GroceryItemWrite, GroceryList, GroceryShoppingStop, GroceryShoppingStopWrite } from "./types";

// groceryApi.update now forwards expiresOn (YYYY-MM-DD) for label/manual expiry; backend maps to expiry_source label/manual

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
  complete(weekStart: string, version: number) {
    return apiRequest<GroceryList>(`/meal-plans/${weekStart}/grocery-list/complete`, {
      method: "POST", version,
    });
  },
  reopen(weekStart: string, version: number) {
    return apiRequest<GroceryList>(`/meal-plans/${weekStart}/grocery-list/reopen`, {
      method: "POST", version,
    });
  },
  stops() {
    return apiRequest<GroceryShoppingStop[]>("/grocery-shopping-stops");
  },
  createStop(value: Required<Pick<GroceryShoppingStopWrite, "name">> & GroceryShoppingStopWrite) {
    return apiRequest<GroceryShoppingStop>("/grocery-shopping-stops", { method: "POST", body: JSON.stringify(value) });
  },
  updateStop(stopId: string, version: number, value: GroceryShoppingStopWrite) {
    return apiRequest<GroceryShoppingStop>(`/grocery-shopping-stops/${stopId}`, { method: "PATCH", version, body: JSON.stringify(value) });
  },
  removeStop(stopId: string, version: number) {
    return apiRequest<void>(`/grocery-shopping-stops/${stopId}`, { method: "DELETE", version });
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

