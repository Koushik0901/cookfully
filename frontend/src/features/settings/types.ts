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
