import type { components } from "../../app/api/generated/schema";

export type GroceryList = components["schemas"]["GroceryListResponse"];
export type GroceryItem = components["schemas"]["GroceryItemResponse"];
export type GroceryItemWrite = components["schemas"]["GroceryItemWriteRequest"];
export type GroceryShoppingStop = components["schemas"]["GroceryShoppingStopResponse"];
export type GroceryShoppingStopWrite = components["schemas"]["GroceryShoppingStopWriteRequest"];

export type GroceryItemCreate = GroceryItemWrite & { displayName: string };

