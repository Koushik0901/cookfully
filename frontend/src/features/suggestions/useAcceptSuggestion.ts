import { useMutation, useQueryClient } from "@tanstack/react-query";

import { ApiProblem } from "../recipes/api";
import { suggestionsApi } from "./api";
import type { MealPlan, PeriodTotal, SuggestionResult } from "./types";

function acceptedTotal(result: SuggestionResult, plan: MealPlan): PeriodTotal | undefined {
  if (result.request.scope === "week") return plan.weekTotal;
  const localDate = result.request.localDate;
  return localDate ? plan.dayTotals[localDate] : undefined;
}

export function useAcceptSuggestion(result: SuggestionResult | undefined, selectedItemIds: string[]) {
  const queryClient = useQueryClient();
  const mutation = useMutation({
    mutationFn: () => {
      if (!result) throw new Error("Generate a suggestion before accepting it.");
      if (!selectedItemIds.length) throw new Error("Select at least one suggested item.");
      return suggestionsApi.accept(result.id, {
        selectedItemIds,
        expectedPlanVersion: result.planVersion,
      });
    },
    onSuccess: (plan) => {
      queryClient.setQueryData(["meal-plan", plan.weekStart], plan);
      void queryClient.invalidateQueries({ queryKey: ["meal-plan", plan.weekStart] });
      void queryClient.invalidateQueries({ queryKey: ["grocery-list", plan.weekStart] });
      void queryClient.invalidateQueries({ queryKey: ["suggestion", result?.id] });
    },
  });
  const conflict = mutation.error instanceof ApiProblem && mutation.error.status === 409;
  return {
    ...mutation,
    conflict,
    acceptedTotal: result && mutation.data ? acceptedTotal(result, mutation.data) : undefined,
  };
}
