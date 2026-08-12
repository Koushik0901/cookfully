export interface OwnerFood {
  id: string;
  displayName: string;
  normalizedName: string;
  brand: string | null;
  caloriesKcal: string;
  proteinG: string;
  carbohydrateG: string;
  fatG: string;
  basisGrams: string;
  typicalServingG: string | null;
  typicalServingUnit: string | null;
  version: number;
}

export interface OwnerFoodWrite {
  displayName: string;
  brand?: string | null;
  caloriesKcal: number;
  proteinG: number;
  carbohydrateG: number;
  fatG: number;
  basisGrams?: number;
  typicalServingG?: number | null;
  typicalServingUnit?: string | null;
}

export interface OwnerFoodUpdate extends OwnerFoodWrite {
  expectedVersion: number;
}

export interface FoodCandidate {
  source: "usda" | "owner";
  id: string;
  description: string;
  brandOwner: string | null;
  servingSizeG: string | null;
  servingUnit: string | null;
}

export interface FoodSearchResponse {
  query: string;
  candidates: FoodCandidate[];
}
