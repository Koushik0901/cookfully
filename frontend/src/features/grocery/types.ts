import type { components } from "../../app/api/generated/schema";

export type GroceryList = components["schemas"]["GroceryList"];
export type GroceryItem = components["schemas"]["GroceryItem"] & {
  purchasedAt?: string | null;
  expiresOn?: string | null;
  expirySource?: "auto" | "label" | "manual" | null;
  needsExpiryDate?: boolean;
};
export type GroceryItemWrite = components["schemas"]["GroceryItemWrite"] & {
  expiresOn?: string | null;
};
export type GroceryShoppingStop = components["schemas"]["GroceryShoppingStop"];
export type GroceryShoppingStopWrite = components["schemas"]["GroceryShoppingStopWrite"];

export type GroceryItemCreate = GroceryItemWrite & { displayName: string };
