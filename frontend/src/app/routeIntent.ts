import type { QueryClient } from "@tanstack/react-query";

import { groceryApi } from "../features/grocery/api";
import { pantryApi } from "../features/pantry/api";
import { planningApi } from "../features/plans/api";
import { todayInTimezone, weekStartFor } from "../features/plans/dates";
import type { OwnerPreferences } from "../features/plans/types";
import { recipesApi } from "../features/recipes/api";

type CodePreloader = () => Promise<unknown>;

let codePreloaders: Record<string, CodePreloader> = {};

export function configureRouteCodePreloaders(preloaders: Record<string, CodePreloader>) {
  codePreloaders = preloaders;
}

/**
 * Start small, cancelable work from an explicit navigation signal.  This uses
 * the existing React Query cache (and its GC window), not a permanent in-memory
 * route cache or an eager startup download.
 */
export function prefetchRouteIntent(queryClient: QueryClient, path: string) {
  const route = path.split("?")[0] ?? path;
  const preloader = codePreloaders[route];
  if (preloader) void preloader();

  if (route === "/app/recipes") {
    void queryClient.prefetchQuery({
      queryKey: ["recipes", { query: "", includeArchived: true }],
      queryFn: ({ signal }) => recipesApi.list({ query: "", includeArchived: true }, undefined, 30, signal),
      staleTime: 60_000,
    });
  } else if (route === "/app/pantry") {
    void queryClient.prefetchQuery({
      queryKey: ["pantry-items"],
      queryFn: pantryApi.list,
      staleTime: 45_000,
    });
  } else if (route === "/app/plan" || route === "/app/grocery") {
    void queryClient.prefetchQuery({
      queryKey: ["owner-preferences"],
      queryFn: planningApi.preferences,
      staleTime: 5 * 60_000,
    }).then(() => {
      const preferences = queryClient.getQueryData<OwnerPreferences>(["owner-preferences"]);
      if (!preferences) return;
      const today = todayInTimezone(preferences.timezone);
      const weekStart = weekStartFor(today, preferences.weekStartsOn);
      if (route === "/app/plan") {
        void queryClient.prefetchQuery({
          queryKey: ["meal-plan", weekStart],
          queryFn: () => planningApi.plan(weekStart),
          staleTime: 20_000,
        });
      } else {
        void queryClient.prefetchQuery({
          queryKey: ["grocery-list", weekStart],
          queryFn: () => groceryApi.get(weekStart),
          staleTime: 15_000,
        });
      }
    });
  }
}

export function prefetchRecipeIntent(queryClient: QueryClient, recipeId: string) {
  void codePreloaders["__recipe-detail"]?.();
  void queryClient.prefetchQuery({
    queryKey: ["recipe", recipeId],
    queryFn: () => recipesApi.get(recipeId),
    staleTime: 60_000,
  });
}
