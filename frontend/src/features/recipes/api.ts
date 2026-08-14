import type {
  Job,
  JobAccepted,
  NutritionCorrectionWrite,
  Recipe,
  RecipeDetail,
  RecipePage,
  RecipeWrite,
  RecipeCollection,
  RecipeOrganizationWrite,
  ResolvedNutrition,
} from "./types";
import { getSessionQueryClient } from "../../app/sessionStore";

const API_ROOT = "/api/v1";

export class ApiProblem extends Error {
  readonly code?: string;
  readonly status: number;

  constructor(status: number, message: string, code?: string) {
    super(message);
    this.name = "ApiProblem";
    this.status = status;
    this.code = code;
  }
}

function cookie(name: string): string | undefined {
  return document.cookie
    .split(";")
    .map((part) => part.trim())
    .find((part) => part.startsWith(`${name}=`))
    ?.slice(name.length + 1);
}

function idempotencyKey(): string {
  return crypto.randomUUID();
}

type RequestOptions = RequestInit & { idempotent?: boolean; version?: number };

export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const headers = new Headers(options.headers);
  headers.set("accept", "application/json");
  const method = (options.method ?? "GET").toUpperCase();
  if (options.body && !(options.body instanceof FormData)) headers.set("content-type", "application/json");
  if (!new Set(["GET", "HEAD", "OPTIONS"]).has(method)) {
    const csrf = cookie("cookfully_csrf");
    if (csrf) headers.set("x-csrf-token", decodeURIComponent(csrf));
  }
  if (options.idempotent) headers.set("idempotency-key", idempotencyKey());
  if (options.version !== undefined) headers.set("if-match", `"${options.version}"`);

  const response = await fetch(`${API_ROOT}${path}`, {
    ...options,
    credentials: "same-origin",
    headers,
  });
  if (!response.ok) {
    let message = `Request failed (${response.status}).`;
    let code: string | undefined;
    try {
      const problem = (await response.json()) as { detail?: string; title?: string; code?: string };
      message = problem.detail ?? problem.title ?? message;
      code = problem.code;
    } catch {
      // Non-JSON failures retain the bounded generic message.
    }
    if (response.status === 401) {
      getSessionQueryClient()?.invalidateQueries({ queryKey: ["owner-session"] });
    }
    throw new ApiProblem(response.status, message, code);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export const recipesApi = {
  list(filters: { query?: string; nutritionState?: string; includeArchived?: boolean; favorite?: boolean; collectionId?: string; mealRole?: string } = {}) {
    const params = new URLSearchParams();
    if (filters.query) params.set("query", filters.query);
    if (filters.nutritionState) params.set("nutritionState", filters.nutritionState);
    if (filters.includeArchived) params.set("includeArchived", "true");
    if (filters.favorite) params.set("favorite", "true");
    if (filters.collectionId) params.set("collectionId", filters.collectionId);
    if (filters.mealRole) params.set("mealRole", filters.mealRole);
    const suffix = params.size ? `?${params.toString()}` : "";
    return apiRequest<RecipePage>(`/recipes${suffix}`);
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
  uploadPhoto(recipeId: string, version: number, photo: File) {
    const body = new FormData();
    body.set("photo", photo);
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
  useSourcePhoto(recipeId: string, version: number, url: string) {
    return apiRequest<RecipeDetail>(`/recipes/${recipeId}/photo/source`, {
      method: "PUT",
      version,
      body: JSON.stringify({ url }),
    });
  },
  archive(recipeId: string, version: number) {
    return apiRequest<void>(`/recipes/${recipeId}`, { method: "DELETE", version });
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
