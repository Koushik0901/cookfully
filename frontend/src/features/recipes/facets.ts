import type { RecipeDetail } from "./types";

export type RecipeFacet = NonNullable<RecipeDetail["facets"]>[number];

const CONFIDENT = 0.8;
// Diet claims were measured on a hand-labeled set and are worded as certain from 0.7 (the server's
// `DIET_CONFIDENT_THRESHOLD`); everything else keeps 0.8.
const DIET_CONFIDENT = 0.7;
const DIET_KEYS = new Set(["vegetarian", "vegan", "gluten_free", "dairy_free"]);

const LABELS: Record<string, string> = {
  vegetarian: "Vegetarian",
  vegan: "Vegan",
  gluten_free: "Gluten-free",
  dairy_free: "Dairy-free",
  "cuisine:italian": "Italian",
  "cuisine:mexican": "Mexican",
  "cuisine:chinese": "Chinese",
  "cuisine:japanese": "Japanese",
  "cuisine:korean": "Korean",
  "cuisine:thai": "Thai",
  "cuisine:indian": "Indian",
  "cuisine:middle_eastern": "Middle Eastern",
  "cuisine:mediterranean": "Mediterranean",
  "cuisine:french": "French",
  "cuisine:american": "American",
  "meal:breakfast": "Breakfast",
  "meal:main": "Main",
  "meal:side": "Side",
  "meal:snack": "Snack",
  "meal:dessert": "Dessert",
  "meal:drink": "Drink",
  "meal:component": "Sauce or component",
  "effort:minimal": "Easy",
  "effort:moderate": "Some effort",
  "effort:involved": "Involved",
  "time:under_15": "Under 15 min hands-on",
  "time:15_30": "15–30 min hands-on",
  "time:30_60": "30–60 min hands-on",
  "time:over_60": "Over an hour hands-on",
  keeps_4_days: "Keeps 4 days",
  freezes_well: "Freezes well",
  reheats_well: "Reheats well",
  needs_oven: "Needs an oven",
  weeknight: "Weeknight-friendly",
};

/** Human label for a facet, with "Probably" when the models were not confident. */
export function facetLabel(facet: RecipeFacet): string {
  const label = LABELS[facet.key] ?? facet.key;
  const cutoff = DIET_KEYS.has(facet.key) ? DIET_CONFIDENT : CONFIDENT;
  return Number(facet.probability) >= cutoff ? label : `Probably ${label.charAt(0).toLowerCase()}${label.slice(1)}`;
}

export function facetKnown(facet: RecipeFacet): boolean {
  return facet.key in LABELS;
}

export const FACET_LABELS = LABELS;
