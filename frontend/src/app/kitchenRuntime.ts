import { clearOfflineResponses, readOfflineResponse, writeOfflineResponse } from "./offlineCache";
import { hasKnownSession, markSessionKnown, notifyServerRestored, notifyServerUnavailable } from "./pwa";
import { getSessionQueryClient } from "./sessionStore";

const API_ROOT = "/api/v1";

export class KitchenRequestProblem extends Error {
  constructor(readonly status: number, message: string, readonly code?: string) {
    super(message);
    this.name = "KitchenRequestProblem";
  }
}

export type KitchenRequestOptions = RequestInit & { idempotent?: boolean; version?: number };

function cookie(name: string): string | undefined {
  return document.cookie.split(";").map((part) => part.trim()).find((part) => part.startsWith(`${name}=`))?.slice(name.length + 1);
}

function shouldCacheOffline(path: string): boolean {
  return !path.startsWith("/auth/") && !path.startsWith("/access-tokens") && !path.startsWith("/database-backups");
}

function isNetworkFailure(error: unknown): boolean {
  if (error instanceof Error && error.name === "AbortError") return false;
  return error instanceof TypeError || (typeof navigator !== "undefined" && navigator.onLine === false);
}

export async function kitchenRequest<T>(path: string, options: KitchenRequestOptions = {}): Promise<T> {
  const headers = new Headers(options.headers);
  headers.set("accept", "application/json");
  const method = (options.method ?? "GET").toUpperCase();
  if (options.body && !(options.body instanceof FormData)) headers.set("content-type", "application/json");
  if (!new Set(["GET", "HEAD", "OPTIONS"]).has(method)) {
    const csrf = cookie("cookfully_csrf");
    if (csrf) headers.set("x-csrf-token", decodeURIComponent(csrf));
  }
  if (options.idempotent) headers.set("idempotency-key", crypto.randomUUID());
  if (options.version !== undefined) headers.set("if-match", `"${options.version}"`);
  const requestUrl = `${API_ROOT}${path}`;
  try {
    const response = await fetch(requestUrl, { ...options, credentials: "same-origin", headers });
    if (!response.ok) {
      let message = `Request failed (${response.status}).`;
      let code: string | undefined;
      try {
        const problem = (await response.json()) as { detail?: string; title?: string; code?: string };
        message = problem.detail ?? problem.title ?? message;
        code = problem.code;
      } catch { /* keep generic error */ }
      if (response.status === 401) {
        markSessionKnown(false);
        void clearOfflineResponses();
        getSessionQueryClient()?.invalidateQueries({ queryKey: ["owner-session"] });
      }
      throw new KitchenRequestProblem(response.status, message, code);
    }
    if (response.status === 204) return undefined as T;
    const value = await response.json() as T;
    notifyServerRestored();
    if (method === "GET" && shouldCacheOffline(path)) void writeOfflineResponse(requestUrl, value);
    return value;
  } catch (error) {
    if (!(error instanceof KitchenRequestProblem) && isNetworkFailure(error)) {
      notifyServerUnavailable();
      if (method === "GET") {
        const cached = await readOfflineResponse<T>(requestUrl);
        if (cached !== undefined) return cached;
      }
      throw new Error("Cookfully could not reach the server. Reconnect and try again.", { cause: error });
    }
    throw error;
  }
}

export async function verifyKitchenSession(): Promise<boolean> {
  try {
    const response = await fetch(`${API_ROOT}/owner/preferences`, { credentials: "same-origin", headers: { accept: "application/json" } });
    if (response.status === 401) {
      markSessionKnown(false);
      void clearOfflineResponses();
      return false;
    }
    if (!response.ok) throw new Error("Unable to verify your session.");
    markSessionKnown(true);
    notifyServerRestored();
    return true;
  } catch (error) {
    notifyServerUnavailable();
    if (hasKnownSession()) return true;
    throw error;
  }
}
