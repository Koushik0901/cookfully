import type { components } from "../../app/api/generated/schema";

export type Recipe = components["schemas"]["RecipeResponse"];
export type RecipeDetail = components["schemas"]["RecipeDetailResponse"];
export type RecipePage = components["schemas"]["RecipePageResponse"];
export type RecipeWrite = components["schemas"]["RecipeWriteRequest"];
export type IngredientWrite = components["schemas"]["IngredientWriteRequest"];
export type Job = components["schemas"]["JobResponse"];
export type JobAccepted = components["schemas"]["JobAcceptedResponse"];
export type ResolvedNutrition = components["schemas"]["ResolvedNutritionResponse"];
export type NutritionCorrectionWrite = components["schemas"]["NutritionCorrectionWriteRequest"];
export type NutritionState = components["schemas"]["NutritionSnapshotResponse"]["status"];
export type RecipeCollection = components["schemas"]["RecipeCollectionResponse"];
export type RecipeOrganizationWrite = components["schemas"]["RecipeOrganizationWriteRequest"];
export type ImportPreview = components["schemas"]["ImportPreviewResponse"];
export type ImportConfirmWrite = components["schemas"]["ImportConfirmRequest"];
export type ImportPreviewSection = components["schemas"]["ImportPreviewSection"];
export type ImportPreviewIngredient = components["schemas"]["ImportPreviewIngredient"];
export type DuplicateSummary = components["schemas"]["DuplicateSummary"];

