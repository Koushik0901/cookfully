import { apiRequest } from "../recipes/api";
import type { JobAccepted, Recipe, RecipePage, RecipeProcessingSummary } from "../recipes/types";
import type { InstallUnit, ReferenceDataStatus } from "../referenceData/api";
import { referenceDataApi } from "../referenceData/api";
import { recipesApi } from "../recipes/api";

export type JobRunScope = "all" | "missing";

export interface JobRunResult {
  scope: JobRunScope;
  accepted: number;
  failed: number;
}

const MISSING_NUTRITION_STATES = new Set(["pending", "stale", "partial", "failed"]);

async function listAllRecipes(): Promise<Recipe[]> {
  const recipes: Recipe[] = [];
  let cursor: string | undefined;
  do {
    const page: RecipePage = await recipesApi.list({}, cursor, 100);
    recipes.push(...page.items);
    cursor = page.nextCursor ?? undefined;
  } while (cursor);
  return recipes;
}

export const jobsApi = {
  recipeProcessingSummary() {
    return apiRequest<RecipeProcessingSummary>("/jobs/recipe-processing");
  },

  async runRecipeProcessing(scope: JobRunScope): Promise<JobRunResult> {
    const recipes = await listAllRecipes();
    const targets = scope === "missing"
      ? recipes.filter((recipe) => MISSING_NUTRITION_STATES.has(recipe.nutritionState))
      : recipes;
    const results = await Promise.allSettled(targets.map((recipe) => recipesApi.recalculate(recipe.id)));
    return {
      scope,
      accepted: results.filter((result) => result.status === "fulfilled").length,
      failed: results.filter((result) => result.status === "rejected").length,
    };
  },

  referenceData() {
    return referenceDataApi.status();
  },

  installReferenceData(units: InstallUnit[]) {
    return referenceDataApi.install(units);
  },

  job(jobId: string) {
    return recipesApi.job(jobId);
  },

  exportPortable(includeMedia = true) {
    return apiRequest<JobAccepted>("/exports", {
      method: "POST",
      idempotent: true,
      body: JSON.stringify({ includeMedia }),
    });
  },
};

export type { InstallUnit, ReferenceDataStatus };
