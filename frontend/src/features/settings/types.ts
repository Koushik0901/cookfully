import type { components } from "../../app/api/generated/schema";

export type AccessToken = components["schemas"]["AccessToken"];
export type AccessTokenCreated = components["schemas"]["AccessTokenCreated"];
export type AccessTokenWrite = components["schemas"]["AccessTokenWrite"];
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
  runtimeStatus: "ready" | "configured" | "downloading" | "failed";
  downloadJobId: string | null;
  downloadJobStatus: string | null;
  downloadProgressCurrent: number | null;
  downloadProgressTotal: number | null;
  downloadFailureMessage: string | null;
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

export type DatabaseBackup = {
  filename: string;
  createdAt: string;
  bytes: number;
  sha256: string;
  reason: "schedule" | "manual" | "host-copy";
};

export type DatabaseBackupStatus = {
  storageMode: "host_bind_mount";
  schedule: string;
  retentionCount: number;
  backups: DatabaseBackup[];
  latest: DatabaseBackup | null;
  lastSuccessAt: string | null;
  lastFailure: { occurredAt: string; message: string } | null;
  pendingManualRequest: boolean;
  serviceHeartbeatAt: string | null;
};

export type DatabaseBackupRequested = { requestId: string; status: "queued" };
