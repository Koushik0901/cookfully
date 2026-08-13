import { apiRequest } from "../recipes/api";
import type { AccessToken, AccessTokenCreated, AccessTokenWrite, PasswordChange, SessionList } from "./types";

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
