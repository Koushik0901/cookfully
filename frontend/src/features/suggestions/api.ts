import { apiRequest } from "../recipes/api";
import type { JobAccepted, MealPlan, OwnerPreferences, RecipePage, SuggestionAcceptance, SuggestionRequest, SuggestionResult } from "./types";

export const suggestionsApi = {
  preferences() {
    return apiRequest<OwnerPreferences>("/owner/preferences");
  },
  recipes() {
    return apiRequest<RecipePage>("/recipes?limit=100");
  },
  create(value: SuggestionRequest) {
    return apiRequest<JobAccepted>("/suggestions", {
      method: "POST",
      idempotent: true,
      body: JSON.stringify(value),
    });
  },
  get(suggestionId: string) {
    return apiRequest<SuggestionResult>(`/suggestions/${suggestionId}`);
  },
  accept(suggestionId: string, value: SuggestionAcceptance) {
    return apiRequest<MealPlan>(`/suggestions/${suggestionId}/accept`, {
      method: "POST",
      idempotent: true,
      body: JSON.stringify(value),
    });
  },
};
