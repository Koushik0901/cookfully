import { apiRequest } from "../recipes/api";

export type IntelligenceOperation = "command" | "recipe_extract" | "pantry_extract" | "cook";

export type IntelligenceCall = {
  name: string;
  arguments: Record<string, unknown>;
};

export type IntelligenceInference = {
  status: "ok" | "unsupported" | "unavailable";
  model?: string | null;
  confidence?: number | null;
  reasoning?: string | null;
  functionCalls: IntelligenceCall[];
  errorCode?: string | null;
  draftId?: string | null;
  expiresAt?: string | null;
};

export type IntelligenceJobAccepted = {
  jobId: string;
  resourceId?: string | null;
  status: string;
};

export type IntelligenceDraft = IntelligenceInference & {
  draftId: string;
  operation: IntelligenceOperation;
  status: "queued" | "processing" | "review" | "executed" | "expired" | "failed" | "unsupported";
  failureCode?: string | null;
  failureMessage?: string | null;
};

export const intelligenceApi = {
  infer(operation: IntelligenceOperation, prompt: string, context: Record<string, string> = {}) {
    return apiRequest<IntelligenceInference>("/intelligence/infer", {
      method: "POST",
      body: JSON.stringify({ operation, prompt, context }),
    });
  },
  createDraft(operation: IntelligenceOperation, prompt: string, context: Record<string, string> = {}) {
    return apiRequest<IntelligenceInference>("/intelligence/drafts", {
      method: "POST",
      body: JSON.stringify({ operation, prompt, context }),
    });
  },
  executeDraft(draftId: string) {
    return apiRequest<{ draftId: string; status: "executed"; results: Array<Record<string, unknown>> }>(
      `/intelligence/drafts/${draftId}/execute`,
      { method: "POST", body: JSON.stringify({ confirm: true }) },
    );
  },
  getDraft(draftId: string) {
    return apiRequest<IntelligenceDraft>(`/intelligence/drafts/${draftId}`);
  },
  createExtractionJob(operation: "recipe_extract" | "pantry_extract", prompt: string, context: Record<string, string> = {}) {
    return apiRequest<IntelligenceJobAccepted>("/intelligence/extraction-jobs", {
      method: "POST",
      body: JSON.stringify({ operation, prompt, context }),
    });
  },
};
