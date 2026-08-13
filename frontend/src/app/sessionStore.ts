import type { QueryClient } from "@tanstack/react-query";

let client: QueryClient | null = null;

export function setSessionQueryClient(value: QueryClient) {
  client = value;
}

export function getSessionQueryClient(): QueryClient | null {
  return client;
}
