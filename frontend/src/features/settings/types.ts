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
