import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { ApiProblem } from "../recipes/api";
import { planningApi } from "./api";
import { addDays } from "./dates";
import type { MealPlanEntry, MealPlanEntryWrite } from "./types";

export function useMealPlanMutations(weekStart: string) {
  const queryClient = useQueryClient();
  const [message, setMessage] = useState("");
  const refresh = () => queryClient.invalidateQueries({ queryKey: ["meal-plan", weekStart] });
  const update = useMutation({
    mutationFn: ({ entry, value }: { entry: MealPlanEntry; value: MealPlanEntryWrite; action?: "refresh" }) => planningApi.updateEntry(entry.id, entry.version, value),
    onSuccess: (_value, variables) => { setMessage(variables.action === "refresh" ? "Nutrition snapshot refreshed" : "Plan entry updated"); void refresh(); },
  });
  const copy = useMutation({
    mutationFn: (entry: MealPlanEntry) => {
      if (!entry.recipeId) throw new Error("This historical entry no longer has a recipe to copy.");
      return planningApi.addEntry(weekStart, { localDate: addDays(entry.localDate, 1), mealSlot: entry.mealSlot, recipeId: entry.recipeId, servings: entry.servings, refreshNutrition: false });
    },
    onSuccess: () => { setMessage("Entry copied to the next day"); void refresh(); },
  });
  const remove = useMutation({
    mutationFn: (entry: MealPlanEntry) => planningApi.removeEntry(entry.id, entry.version),
    onSuccess: () => { setMessage("Plan entry removed"); void refresh(); },
  });
  const error = update.error ?? copy.error ?? remove.error;
  const conflict = error instanceof ApiProblem && error.status === 409;
  return { update, copy, remove, message, error, conflict, reload: refresh };
}
