import { apiRequest } from "../recipes/api";
import type { GroceryList } from "../grocery/types";
import type { PantryItem, PantryRecipeMatch } from "../pantry/types";
import type { MealPlan, OwnerPreferences, RecipePage } from "../plans/types";

export interface HomeBootstrap {
  preferences: OwnerPreferences;
  recipes: RecipePage;
  pantry: PantryItem[];
  plan: MealPlan | null;
  grocery: GroceryList | null;
  pantryMatches: PantryRecipeMatch[];
}

export const homeApi = {
  get() {
    return apiRequest<HomeBootstrap>("/owner/home");
  },
};
