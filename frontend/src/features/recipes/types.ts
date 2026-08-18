import type { components } from "../../app/api/generated/schema";

export type Recipe = components["schemas"]["RecipeResponse"];
export type RecipeDetail = components["schemas"]["RecipeDetailResponse"];
export type RecipePage = components["schemas"]["RecipePageResponse"];
export type BulkArchiveResponse = components["schemas"]["RecipeBulkArchiveResponse"];
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
export type ImportConfirmComponent = components["schemas"]["ImportConfirmComponent"];
export type ImportConfirmIngredient = components["schemas"]["ImportConfirmIngredient"];
export type ImportMergeWrite = components["schemas"]["ImportMergeRequest"];
export type ImportPreviewSection = components["schemas"]["ImportPreviewSection"];
export type ImportPreviewIngredient = components["schemas"]["ImportPreviewIngredient"];
export type DuplicateSummary = components["schemas"]["DuplicateSummary"];
export type RecipePhotoAttachWrite = components["schemas"]["RecipePhotoAttachRequest"];
export type ThumbnailCrop = components["schemas"]["ThumbnailCropRequest-Output"];
export type ThumbnailCropWrite = components["schemas"]["ThumbnailCropRequest-Input"];

