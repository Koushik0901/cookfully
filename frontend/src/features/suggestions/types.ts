import type { components } from "../../app/api/generated/schema";

export type SuggestionResult = components["schemas"]["SuggestionResultResponse"] & {
  projectedDayTotals: Record<string, PeriodTotal>;
  projectedWeekTotal: PeriodTotal | null;
};
export type SuggestionItem = components["schemas"]["SuggestionItemResponse"];
export type SuggestionAcceptance = components["schemas"]["SuggestionAcceptanceRequest"];
export type JobAccepted = components["schemas"]["JobAcceptedResponse"];
export type MealPlan = components["schemas"]["MealPlanResponse"];
export type RecipePage = components["schemas"]["RecipePageResponse"];
export type PeriodTotal = components["schemas"]["PeriodTotalResponse"];
export type OwnerPreferences = components["schemas"]["OwnerPreferences"];

export type SuggestionMacroValues = {
  caloriesKcal: string;
  proteinG: string;
  carbohydrateG: string;
  fatG: string;
};

export type SuggestionRequest = Omit<components["schemas"]["SuggestionRequest"], "tolerances"> & {
  tolerances: SuggestionMacroValues;
};
