import type { components } from "../../app/api/generated/schema";

export type GroceryList = components["schemas"]["GroceryList"];
export type GroceryItem = components["schemas"]["GroceryItem"];
export type GroceryItemWrite = components["schemas"]["GroceryItemWrite"];

export type GroceryItemCreate = GroceryItemWrite & { displayName: string };

