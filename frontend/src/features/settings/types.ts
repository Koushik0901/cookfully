import type { components } from "../../app/api/generated/schema";

export type AccessToken = components["schemas"]["AccessTokenResponse"];
export type AccessTokenCreated = components["schemas"]["AccessTokenCreatedResponse"];
export type AccessTokenWrite = components["schemas"]["AccessTokenWriteRequest"];
export type AccessTokenScope = AccessTokenWrite["scopes"][number];

export type Session = {
  id: string;
  clientLabel: string | null;
  createdAt: string;
  lastSeenAt: string;
  isCurrent: boolean;
};

export type SessionList = { sessions: Session[] };

export type PasswordChange = { currentPassword: string; newPassword: string };

export type NutritionBackend = "hashing" | "fastembed";
export type NutritionIntelligenceSettings = {
  backend: NutritionBackend;
  modelName: string;
  modelRevision: string | null;
  concurrency: number;
  version: number;
  runtimeStatus: "ready" | "configured" | "fallback";
};
export type NutritionIntelligenceEstimateRequest = {
  backend: NutritionBackend;
  modelName: string;
  concurrency: number;
};
export type NutritionIntelligenceSettingsWrite = NutritionIntelligenceEstimateRequest & {
  version: number;
  estimateHash: string;
};
export type NutritionIntelligenceEstimate = {
  backend: NutritionBackend;
  modelName: string;
  modelRevision: string | null;
  concurrency: number;
  activeFoodCount: number;
  downloadBytes: number;
  diskBytes: number;
  modelMemoryBytes: number;
  perJobMemoryBytes: number;
  totalMemoryBytes: number;
  requiredCpuCores: number;
  availableCpuCores: number;
  availableMemoryBytes: number;
  availableDiskBytes: number;
  memoryHeadroomBytes: number;
  status: "safe" | "warning" | "blocked";
  warnings: string[];
  estimateHash: string;
};
