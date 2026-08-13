import type { components } from "../../app/api/generated/schema";

export type GroceryList = components["schemas"]["GroceryList"];
export type GroceryItem = components["schemas"]["GroceryItem"];
export type GroceryItemWrite = components["schemas"]["GroceryItemWrite"];
export type GroceryShoppingStop = components["schemas"]["GroceryShoppingStop"];
export type GroceryShoppingStopWrite = components["schemas"]["GroceryShoppingStopWrite"];

export type GroceryItemCreate = GroceryItemWrite & { displayName: string };

