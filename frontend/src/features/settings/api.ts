import { apiRequest } from "../recipes/api";
import type {
  AccessToken,
  AccessTokenCreated,
  AccessTokenWrite,
  DatabaseBackupRequested,
  DatabaseBackupStatus,
  PasswordChange,
  SessionList,
} from "./types";
import type {
  NutritionIntelligenceEstimate,
  NutritionIntelligenceEstimateRequest,
  NutritionIntelligenceSettings,
  NutritionIntelligenceSettingsWrite,
} from "./types";

export const agentAccessApi = {
  list() {
    return apiRequest<AccessToken[]>("/access-tokens");
  },
  create(value: AccessTokenWrite) {
    return apiRequest<AccessTokenCreated>("/access-tokens", {
      method: "POST",
      body: JSON.stringify(value),
    });
  },
  revoke(tokenId: string) {
    return apiRequest<void>(`/access-tokens/${tokenId}`, {
      method: "DELETE",
      idempotent: true,
    });
  },
};

export const accountApi = {
  sessions() {
    return apiRequest<SessionList>("/auth/sessions");
  },
  revokeSession(sessionId: string) {
    return apiRequest<void>(`/auth/sessions/${sessionId}`, {
      method: "DELETE",
    });
  },
  changePassword(value: PasswordChange) {
    return apiRequest<void>("/auth/password", {
      method: "POST",
      body: JSON.stringify(value),
    });
  },
  signOut() {
    return apiRequest<void>("/auth/session", {
      method: "DELETE",
    });
  },
};

export const nutritionIntelligenceApi = {
  get() {
    return apiRequest<NutritionIntelligenceSettings>("/nutrition-intelligence/settings");
  },
  estimate(value: NutritionIntelligenceEstimateRequest) {
    return apiRequest<NutritionIntelligenceEstimate>(
      "/nutrition-intelligence/estimate",
      { method: "POST", body: JSON.stringify(value) },
    );
  },
  update(value: NutritionIntelligenceSettingsWrite) {
    return apiRequest<NutritionIntelligenceSettings>(
      "/nutrition-intelligence/settings",
      { method: "PUT", body: JSON.stringify(value) },
    );
  },
};

export const databaseBackupsApi = {
  status() {
    return apiRequest<DatabaseBackupStatus>("/database-backups");
  },
  request() {
    return apiRequest<DatabaseBackupRequested>("/database-backups/request", {
      method: "POST",
    });
  },
};
