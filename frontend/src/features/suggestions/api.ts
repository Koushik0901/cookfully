import { apiRequest } from "../recipes/api";
import type { JobAccepted, MealPlan, OwnerPreferences, RecipePage, SuggestionAcceptance, SuggestionRequest, SuggestionResult } from "./types";

export const suggestionsApi = {
  preferences() {
    return apiRequest<OwnerPreferences>("/owner/preferences");
  },
  async recipes() {
    const items: RecipePage["items"] = [];
    let cursor: string | undefined;
    do {
      const params = new URLSearchParams({ limit: "100" });
      if (cursor) params.set("cursor", cursor);
      const page = await apiRequest<RecipePage>(`/recipes?${params.toString()}`);
      items.push(...page.items);
      cursor = page.nextCursor ?? undefined;
    } while (cursor);
    return { items, nextCursor: null } satisfies RecipePage;
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
