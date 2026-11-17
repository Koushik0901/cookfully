import type { RecipeDetail } from "./types";

type Ingredient = RecipeDetail["ingredients"][number];

export type ModelPick = {
  foodReferenceId: string;
  description: string;
  probability: number;
};

type RefereeEvidence = {
  kind?: unknown;
  impactDv?: unknown;
  pick?: { foodReferenceId?: unknown; description?: unknown; probability?: unknown } | null;
};

function refereeEvidence(item: Ingredient): RefereeEvidence | null {
  const entries = (item.candidateEvidence ?? []) as RefereeEvidence[];
  return entries.find((entry) => entry && entry.kind === "match_referee") ?? null;
}

/** The decision models' suggested food for a line in review, when they agreed on one. */
export function modelPick(item: Ingredient): ModelPick | null {
  const pick = refereeEvidence(item)?.pick;
  if (!pick || typeof pick.foodReferenceId !== "string" || typeof pick.description !== "string") return null;
  const probability = Number(pick.probability);
  if (!Number.isFinite(probability)) return null;
  return { foodReferenceId: pick.foodReferenceId, description: pick.description, probability };
}

/** Largest nutrient error at stake on the line, as a share of daily value; null when unknown. */
export function reviewImpact(item: Ingredient): number | null {
  const raw = refereeEvidence(item)?.impactDv;
  if (raw === null || raw === undefined) return null;
  const value = Number(raw);
  return Number.isFinite(value) ? value : null;
}

export function needsReview(item: Ingredient): boolean {
  return item.matchStatus === "ambiguous" || item.matchStatus === "unmatched" || item.resolutionKind === "provisional";
}

/** Lines that need review, the ones with the most nutrition at stake first; others keep recipe order. */
export function reviewOrder(ingredients: readonly Ingredient[]): Ingredient[] {
  return ingredients
    .map((item, index) => ({ item, index, impact: reviewImpact(item) }))
    .filter(({ item }) => needsReview(item))
    .sort((a, b) => {
      if (a.impact !== null && b.impact !== null && a.impact !== b.impact) return b.impact - a.impact;
      if (a.impact !== null && b.impact === null) return -1;
      if (a.impact === null && b.impact !== null) return 1;
      return a.index - b.index;
    })
    .map(({ item }) => item);
}

export function reviewSummary(item: Ingredient): string {
  if (item.resolutionKind === "provisional") return `Estimated from ${item.candidateEvidence?.length ?? 0} possible foods`;
  if (item.matchStatus === "ambiguous") return "Several possible foods";
  return "No food selected yet";
}

export function formatProbability(probability: number): string {
  return `${Math.round(probability * 100)}%`;
}
