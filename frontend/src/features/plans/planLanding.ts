import { createContext, useContext } from "react";

/**
 * The meal that was just added or copied, so its card can "land" (arrive and
 * hold the mint field briefly) and its day count can tick. Planning-drop motion
 * only; it never affects data or layout.
 */
export type PlanLanding = { entryId: string; localDate: string } | null;

export const PLAN_LANDING_MS = 1600;

export const PlanLandingContext = createContext<PlanLanding>(null);

export function usePlanLanding(): PlanLanding {
  return useContext(PlanLandingContext);
}
