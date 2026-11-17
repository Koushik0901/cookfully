import { createContext, useContext, useMemo, type ReactNode } from "react";
import { TriangleAlert } from "lucide-react";

import type { MealPlan } from "./types";

const AvoidWarningsContext = createContext<ReadonlyMap<string, readonly string[]>>(new Map());

/** Makes the plan's avoid-list warnings available to every meal card below it. */
export function AvoidWarningsProvider({ plan, children }: { plan: MealPlan | undefined; children: ReactNode }) {
  const warnings = plan?.avoidWarnings;
  const value = useMemo(
    () => new Map((warnings ?? []).map((warning) => [warning.recipeId, warning.items] as const)),
    [warnings],
  );
  return <AvoidWarningsContext.Provider value={value}>{children}</AvoidWarningsContext.Provider>;
}

export function AvoidBadge({ recipeId }: { recipeId: string | null | undefined }) {
  const warnings = useContext(AvoidWarningsContext);
  const items = recipeId ? warnings.get(recipeId) : undefined;
  if (!items?.length) return null;
  return (
    <p className="avoid-badge" role="note">
      <TriangleAlert aria-hidden="true" />
      <span>Contains {items.join(", ")}</span>
    </p>
  );
}
