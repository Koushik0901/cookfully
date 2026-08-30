import type {
  ImportConfirmWrite,
  ImportMergeWrite,
  ImportPreview,
  Job,
  JobAccepted,
  NutritionCorrectionWrite,
  Recipe,
  BulkArchiveResponse,
  RecipeDetail,
  RecipePage,
  RecipeWrite,
  RecipeCollection,
  RecipeOrganizationWrite,
  ThumbnailCropWrite,
  ResolvedNutrition,
} from "./types";
import { KitchenRequestProblem, kitchenRequest, type KitchenRequestOptions } from "../../app/kitchenRuntime";

export class ApiProblem extends KitchenRequestProblem {}

export async function apiRequest<T>(path: string, options: KitchenRequestOptions = {}): Promise<T> {
  try {
    return await kitchenRequest<T>(path, options);
  } catch (error) {
    if (error instanceof KitchenRequestProblem) throw new ApiProblem(error.status, error.message, error.code);
    throw error;
  }
}

export const recipesApi = {
  list(filters: { query?: string; nutritionState?: string; includeArchived?: boolean; favorite?: boolean; collectionId?: string; mealRole?: string } = {}, cursor?: string, limit = 30, signal?: AbortSignal) {
    const params = new URLSearchParams();
    if (filters.query) params.set("query", filters.query);
    if (filters.nutritionState) params.set("nutritionState", filters.nutritionState);
    if (filters.includeArchived) params.set("includeArchived", "true");
    if (filters.favorite) params.set("favorite", "true");
    if (filters.collectionId) params.set("collectionId", filters.collectionId);
    if (filters.mealRole) params.set("mealRole", filters.mealRole);
    params.set("limit", String(limit));
    if (cursor) params.set("cursor", cursor);
    const suffix = params.size ? `?${params.toString()}` : "";
    return apiRequest<RecipePage>(`/recipes${suffix}`, { signal });
  },
  get(recipeId: string) {
    return apiRequest<RecipeDetail>(`/recipes/${recipeId}`);
  },
  create(value: RecipeWrite) {
    return apiRequest<Recipe>("/recipes", { method: "POST", body: JSON.stringify(value) });
  },
  update(recipeId: string, version: number, value: RecipeWrite) {
    return apiRequest<RecipeDetail>(`/recipes/${recipeId}`, {
      method: "PATCH",
      version,
      body: JSON.stringify(value),
    });
  },
  collections() { return apiRequest<RecipeCollection[]>("/recipes/collections"); },
  createCollection(name: string) { return apiRequest<RecipeCollection>("/recipes/collections", { method: "POST", body: JSON.stringify({ name }) }); },
  updateCollection(collectionId: string, version: number, value: { name?: string; position?: number }) { return apiRequest<RecipeCollection>(`/recipes/collections/${collectionId}`, { method: "PATCH", version, body: JSON.stringify(value) }); },
  removeCollection(collectionId: string, version: number) { return apiRequest<void>(`/recipes/collections/${collectionId}`, { method: "DELETE", version }); },
  organize(recipeId: string, version: number, value: RecipeOrganizationWrite) {
    return apiRequest<RecipeDetail>(`/recipes/${recipeId}/organization`, { method: "PUT", version, body: JSON.stringify(value) });
  },
  uploadPhoto(recipeId: string, version: number, photo: File, thumbnailCrop?: ThumbnailCropWrite) {
    const body = new FormData();
    body.set("photo", photo);
    if (thumbnailCrop) body.set("thumbnailCrop", JSON.stringify(thumbnailCrop));
    return apiRequest<RecipeDetail>(`/recipes/${recipeId}/photo`, {
      method: "PUT",
      version,
      body,
    });
  },
  removePhoto(recipeId: string, version: number) {
    return apiRequest<RecipeDetail>(`/recipes/${recipeId}/photo`, {
      method: "DELETE",
      version,
    });
  },
  sourceImages(recipeId: string) {
    return apiRequest<{ url: string }[]>(`/recipes/${recipeId}/source-images`);
  },
  useSourcePhoto(recipeId: string, version: number, url: string, thumbnailCrop?: ThumbnailCropWrite) {
    return apiRequest<RecipeDetail>(`/recipes/${recipeId}/photo/source`, {
      method: "PUT",
      version,
      body: JSON.stringify({ url, thumbnailCrop }),
    });
  },
  archive(recipeId: string, version: number) {
    return apiRequest<void>(`/recipes/${recipeId}`, { method: "DELETE", version });
  },
  stagePhoto(photo: File) {
    const body = new FormData();
    body.set("photo", photo);
    return apiRequest<{ id: string; expiresAt: string }>("/recipes/photo-stages", {
      method: "POST",
      body,
    });
  },
  bulkArchive(items: Array<{ id: string; version: number }>) {
    return apiRequest<BulkArchiveResponse>("/recipes/bulk/archive", {
      method: "POST",
      body: JSON.stringify({ recipes: items }),
    });
  },
  restore(recipeId: string, version: number) {
    return apiRequest<RecipeDetail>(`/recipes/${recipeId}/restore`, {
      method: "POST",
      version,
      idempotent: true,
    });
  },
  permanentDelete(recipeId: string, version: number) {
    return apiRequest<void>(`/recipes/${recipeId}/permanent`, {
      method: "DELETE",
      version,
      idempotent: true,
      body: JSON.stringify({ confirmation: "permanently-delete" }),
    });
  },
  import(url: string) {
    return apiRequest<JobAccepted>("/recipes/import", {
      method: "POST",
      idempotent: true,
      body: JSON.stringify({ url }),
    });
  },
  preview(url: string) {
    return apiRequest<ImportPreview>("/recipes/import/preview", {
      method: "POST",
      body: JSON.stringify({ url }),
    });
  },
  previewPdf(file: File) {
    const body = new FormData();
    body.set("file", file);
    return apiRequest<ImportPreview>("/recipes/import/preview/pdf", {
      method: "POST",
      body,
    });
  },
  confirmImport(write: ImportConfirmWrite) {
    return apiRequest<JobAccepted>("/recipes/import/confirm", {
      method: "POST",
      idempotent: true,
      body: JSON.stringify(write),
    });
  },
  mergeImport(write: ImportMergeWrite) {
    return apiRequest<JobAccepted>("/recipes/import/merge", {
      method: "POST",
      idempotent: true,
      body: JSON.stringify(write),
    });
  },
  attachPhoto(recipeId: string, version: number, imageSource: string, thumbnailCrop?: ThumbnailCropWrite) {
    return apiRequest<RecipeDetail>(`/recipes/${recipeId}/photo/attach`, {
      method: "PUT",
      version,
      body: JSON.stringify({ imageSource, thumbnailCrop }),
    });
  },
  recalculate(recipeId: string, resetCorrections = false) {
    return apiRequest<JobAccepted>(`/recipes/${recipeId}/nutrition/recalculate`, {
      method: "POST",
      idempotent: true,
      body: JSON.stringify({ resetCorrections }),
    });
  },
  correct(recipeId: string, value: NutritionCorrectionWrite) {
    return apiRequest<ResolvedNutrition>(`/recipes/${recipeId}/nutrition/corrections`, {
      method: "POST",
      idempotent: true,
      body: JSON.stringify(value),
    });
  },
  resetCorrection(recipeId: string, correctionId: string) {
    return apiRequest<ResolvedNutrition>(
      `/recipes/${recipeId}/nutrition/corrections/${correctionId}`,
      { method: "DELETE", idempotent: true },
    );
  },
  job(jobId: string) {
    return apiRequest<Job>(`/jobs/${jobId}`);
  },
  currentJob(recipeId: string) {
    const params = new URLSearchParams({ aggregateType: "recipe", aggregateId: recipeId });
    return apiRequest<Job>(`/jobs/current?${params.toString()}`);
  },
};
