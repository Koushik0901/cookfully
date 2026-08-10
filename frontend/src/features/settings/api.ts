import { apiRequest } from "../recipes/api";
import type { AccessToken, AccessTokenCreated, AccessTokenWrite } from "./types";

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
