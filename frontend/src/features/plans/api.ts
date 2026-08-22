import { apiRequest } from "../recipes/api";
import type {
  MealPlan,
  MealPlanEntry,
  MealPlanEntryWrite,
  OwnerPreferences,
  RecipePage,
  UserGoal,
  UserGoalWrite,
} from "./types";

export const planningApi = {
  preferences() {
    return apiRequest<OwnerPreferences>("/owner/preferences");
  },
  updatePreferences(value: OwnerPreferences) {
    return apiRequest<OwnerPreferences>("/owner/preferences", {
      method: "PUT",
      body: JSON.stringify(value),
    });
  },
  goal(onDate?: string) {
    const suffix = onDate ? `?onDate=${encodeURIComponent(onDate)}` : "";
    return apiRequest<UserGoal>(`/goals/current${suffix}`);
  },
  updateGoal(value: UserGoalWrite, version?: number) {
    return apiRequest<UserGoal>("/goals/current", {
      method: "PUT",
      version,
      body: JSON.stringify(value),
    });
  },
  plan(weekStart: string) {
    return apiRequest<MealPlan>(`/meal-plans/${weekStart}`);
  },
  async recipes(query = "", signal?: AbortSignal) {
    const items: RecipePage["items"] = [];
    let cursor: string | undefined;
    do {
      // Planned entries keep a recipe snapshot, but the UI also needs the
      // archived recipe's media and metadata so archiving never turns an
      // existing meal card into a blank placeholder.
      const normalizedQuery = query.trim();
      const params = new URLSearchParams({ limit: normalizedQuery ? "8" : "100", includeArchived: "true" });
      if (normalizedQuery) params.set("query", normalizedQuery);
      if (cursor) params.set("cursor", cursor);
      const page = await apiRequest<RecipePage>(`/recipes?${params.toString()}`, { signal });
      items.push(...page.items);
      cursor = page.nextCursor ?? undefined;
      if (normalizedQuery) cursor = undefined;
    } while (cursor);
    return { items, nextCursor: null } satisfies RecipePage;
  },
  addEntry(weekStart: string, value: MealPlanEntryWrite) {
    return apiRequest<MealPlanEntry>(`/meal-plans/${weekStart}/entries`, {
      method: "POST",
      idempotent: true,
      body: JSON.stringify(value),
    });
  },
  updateEntry(entryId: string, version: number, value: MealPlanEntryWrite) {
    return apiRequest<MealPlanEntry>(`/meal-plan-entries/${entryId}`, {
      method: "PATCH",
      idempotent: true,
      version,
      body: JSON.stringify(value),
    });
  },
  swapEntries(entryId: string, version: number, targetEntryId: string, targetVersion: number) {
    return apiRequest<{ source: MealPlanEntry; target: MealPlanEntry }>(`/meal-plan-entries/${entryId}/swap`, {
      method: "POST",
      idempotent: true,
      version,
      body: JSON.stringify({ targetEntryId, targetVersion }),
    });
  },
  removeEntry(entryId: string, version: number) {
    return apiRequest<void>(`/meal-plan-entries/${entryId}`, {
      method: "DELETE",
      idempotent: true,
      version,
    });
  },
};
