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

function systemFacts(operation: IntelligenceOperation): string {
  const today = new Date().toISOString().slice(0, 10);
  const device = operation === "cook" ? "phone" : "server";
  const locale = typeof navigator !== "undefined" && navigator.language ? navigator.language : "en-US";
  return `date:${today}; locale:${locale}; device:${device}`;
}

export const intelligenceApi = {
  infer(operation: IntelligenceOperation, prompt: string, context: Record<string, string> = {}, system?: string) {
    const effectiveSystem = system ?? systemFacts(operation);
    return apiRequest<IntelligenceInference>("/intelligence/infer", {
      method: "POST",
      body: JSON.stringify({ operation, prompt, context, system: effectiveSystem }),
    });
  },
  createDraft(operation: IntelligenceOperation, prompt: string, context: Record<string, string> = {}, system?: string) {
    const effectiveSystem = system ?? systemFacts(operation);
    return apiRequest<IntelligenceInference>("/intelligence/drafts", {
      method: "POST",
      body: JSON.stringify({ operation, prompt, context, system: effectiveSystem }),
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
  createExtractionJob(
    operation: "recipe_extract" | "pantry_extract",
    prompt: string,
    context: Record<string, string> = {},
    system?: string,
  ) {
    const effectiveSystem = system ?? systemFacts(operation);
    return apiRequest<IntelligenceJobAccepted>("/intelligence/extraction-jobs", {
      method: "POST",
      body: JSON.stringify({ operation, prompt, context, system: effectiveSystem }),
    });
  },
};
