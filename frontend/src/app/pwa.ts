export type InstallPromptEvent = Event & {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed" }>;
};

const INSTALL_EVENT = "cookfully:install-available";
const UPDATE_EVENT = "cookfully:update-available";
const SERVER_UNAVAILABLE_EVENT = "cookfully:server-unavailable";
const SERVER_RESTORED_EVENT = "cookfully:server-restored";
const SESSION_KNOWN_KEY = "cookfully:session-known";

let deferredInstallPrompt: InstallPromptEvent | null = null;

export function registerProgressiveWebApp(): void {
  if (!import.meta.env.PROD || typeof window === "undefined") return;

  window.addEventListener("beforeinstallprompt", (event) => {
    event.preventDefault();
    deferredInstallPrompt = event as InstallPromptEvent;
    window.dispatchEvent(new Event(INSTALL_EVENT));
  });

  window.addEventListener("appinstalled", () => {
    deferredInstallPrompt = null;
    window.dispatchEvent(new Event(INSTALL_EVENT));
  });

  if (!("serviceWorker" in navigator)) return;
  void navigator.serviceWorker.register("/sw.js", { scope: "/" }).then((registration) => {
    registration.addEventListener("updatefound", () => {
      const worker = registration.installing;
      if (!worker) return;
      worker.addEventListener("statechange", () => {
        if (worker.state === "installed" && navigator.serviceWorker.controller) {
          window.dispatchEvent(new Event(UPDATE_EVENT));
        }
      });
    });
    void registration.update();
  }).catch(() => {
    // The app remains fully usable when service workers are blocked by policy.
  });
}

export function subscribeToPwaEvent(name: typeof INSTALL_EVENT | typeof UPDATE_EVENT, listener: () => void): () => void {
  window.addEventListener(name, listener);
  return () => window.removeEventListener(name, listener);
}

export function canInstallProgressiveWebApp(): boolean {
  return deferredInstallPrompt !== null;
}

export async function promptProgressiveWebAppInstall(): Promise<boolean> {
  if (!deferredInstallPrompt) return false;
  const prompt = deferredInstallPrompt;
  deferredInstallPrompt = null;
  await prompt.prompt();
  const choice = await prompt.userChoice;
  window.dispatchEvent(new Event(INSTALL_EVENT));
  return choice.outcome === "accepted";
}

export function isRunningAsInstalledApp(): boolean {
  if (typeof window === "undefined") return false;
  const standalone = typeof window.matchMedia === "function" && window.matchMedia("(display-mode: standalone)").matches;
  return standalone
    || ("standalone" in navigator && Boolean((navigator as Navigator & { standalone?: boolean }).standalone));
}

export function isIosDevice(): boolean {
  if (typeof navigator === "undefined") return false;
  return /iphone|ipad|ipod/i.test(navigator.userAgent)
    || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
}

export function markSessionKnown(known: boolean): void {
  if (typeof window === "undefined") return;
  try {
    if (known) window.localStorage.setItem(SESSION_KNOWN_KEY, "true");
    else window.localStorage.removeItem(SESSION_KNOWN_KEY);
  } catch {
    // Storage can be blocked by private browsing or an enterprise policy.
  }
}

export function hasKnownSession(): boolean {
  if (typeof window === "undefined") return false;
  try {
    return window.localStorage.getItem(SESSION_KNOWN_KEY) === "true";
  } catch {
    return false;
  }
}

export function notifyServerUnavailable(): void {
  if (typeof window !== "undefined") window.dispatchEvent(new Event(SERVER_UNAVAILABLE_EVENT));
}

export function notifyServerRestored(): void {
  if (typeof window !== "undefined") window.dispatchEvent(new Event(SERVER_RESTORED_EVENT));
}

export const pwaEvents = {
  install: INSTALL_EVENT,
  update: UPDATE_EVENT,
  serverUnavailable: SERVER_UNAVAILABLE_EVENT,
  serverRestored: SERVER_RESTORED_EVENT,
} as const;
