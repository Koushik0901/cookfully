import type { QueryClient } from "@tanstack/react-query";

/**
 * A food choice can change nutrition, pantry confidence, planning summaries,
 * and grocery deductions. Keep the refresh contract in one place so a match
 * made from any screen converges everywhere else.
 */
export function invalidateFoodChoiceQueries(queryClient: QueryClient) {
  return Promise.all([
    queryClient.invalidateQueries({ queryKey: ["owner-foods"] }),
    queryClient.invalidateQueries({ queryKey: ["pantry-items"] }),
    queryClient.invalidateQueries({ queryKey: ["pantry-recipe-matches"] }),
    queryClient.invalidateQueries({ queryKey: ["planning-recipes"] }),
    queryClient.invalidateQueries({ queryKey: ["recipes"] }),
    queryClient.invalidateQueries({ queryKey: ["recipe"] }),
    queryClient.invalidateQueries({ queryKey: ["grocery-list"] }),
    queryClient.invalidateQueries({ queryKey: ["meal-plan"] }),
  ]);
}
