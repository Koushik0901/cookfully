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
  recipes() {
    return apiRequest<RecipePage>("/recipes?limit=100");
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
  removeEntry(entryId: string, version: number) {
    return apiRequest<void>(`/meal-plan-entries/${entryId}`, {
      method: "DELETE",
      idempotent: true,
      version,
    });
  },
};
