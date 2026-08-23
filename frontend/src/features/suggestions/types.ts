import type { components } from "../../app/api/generated/schema";

export type SuggestionResult = components["schemas"]["SuggestionResult"] & {
  projectedDayTotals: Record<string, PeriodTotal>;
  projectedWeekTotal: PeriodTotal | null;
};
export type SuggestionItem = components["schemas"]["SuggestionItem"];
export type SuggestionAcceptance = components["schemas"]["SuggestionAcceptance"];
export type JobAccepted = components["schemas"]["JobAccepted"];
export type MealPlan = components["schemas"]["MealPlan"];
export type RecipePage = components["schemas"]["RecipePage"];
export type PeriodTotal = components["schemas"]["PeriodTotal"];
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
