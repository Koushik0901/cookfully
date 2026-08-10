import type { components } from "../../app/api/generated/schema";

export type AccessToken = components["schemas"]["AccessToken"];
export type AccessTokenCreated = components["schemas"]["AccessTokenCreated"];
export type AccessTokenWrite = components["schemas"]["AccessTokenWrite"];
export type AccessTokenScope = AccessTokenWrite["scopes"][number];
