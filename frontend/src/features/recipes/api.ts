import type {
  Job,
  JobAccepted,
  NutritionCorrectionWrite,
  Recipe,
  RecipeDetail,
  RecipePage,
  RecipeWrite,
  ResolvedNutrition,
} from "./types";

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
  if (options.body) headers.set("content-type", "application/json");
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
    throw new ApiProblem(response.status, message, code);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export const recipesApi = {
  list(filters: { query?: string; nutritionState?: string; includeArchived?: boolean } = {}) {
    const params = new URLSearchParams();
    if (filters.query) params.set("query", filters.query);
    if (filters.nutritionState) params.set("nutritionState", filters.nutritionState);
    if (filters.includeArchived) params.set("includeArchived", "true");
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
