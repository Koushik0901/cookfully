import { Download, RefreshCw, Wifi, WifiOff } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";

import { Button } from "../components";
import {
  canInstallProgressiveWebApp,
  isIosDevice,
  isRunningAsInstalledApp,
  promptProgressiveWebAppInstall,
  pwaEvents,
  subscribeToPwaEvent,
} from "./pwa";

export function NetworkStatusBanner() {
  const [online, setOnline] = useState(() => typeof navigator === "undefined" || navigator.onLine);
  const [restored, setRestored] = useState(false);
  const [serverUnavailable, setServerUnavailable] = useState(false);
  const wasOffline = useRef(!online);
  const serverUnavailableRef = useRef(false);

  useEffect(() => {
    const handleOffline = () => {
      wasOffline.current = true;
      setOnline(false);
      setRestored(false);
    };
    const handleOnline = () => {
      setOnline(true);
      if (wasOffline.current) {
        setRestored(true);
        window.setTimeout(() => setRestored(false), 2800);
      }
      wasOffline.current = false;
    };
    window.addEventListener("offline", handleOffline);
    window.addEventListener("online", handleOnline);
    const handleServerUnavailable = () => {
      serverUnavailableRef.current = true;
      setServerUnavailable(true);
    };
    const handleServerRestored = () => {
      if (!serverUnavailableRef.current) return;
      serverUnavailableRef.current = false;
      setServerUnavailable(false);
      setRestored(true);
      window.setTimeout(() => setRestored(false), 2800);
    };
    window.addEventListener(pwaEvents.serverUnavailable, handleServerUnavailable);
    window.addEventListener(pwaEvents.serverRestored, handleServerRestored);
    return () => {
      window.removeEventListener("offline", handleOffline);
      window.removeEventListener("online", handleOnline);
      window.removeEventListener(pwaEvents.serverUnavailable, handleServerUnavailable);
      window.removeEventListener(pwaEvents.serverRestored, handleServerRestored);
    };
  }, []);

  if (online && !serverUnavailable && !restored) return null;
  if (restored) {
    return <aside className="runtime-banner runtime-banner--online" role="status" aria-live="polite"><Wifi aria-hidden="true" /><span>Connection restored. Refreshing kitchen data.</span></aside>;
  }
  if (online && serverUnavailable) {
    return <aside className="runtime-banner runtime-banner--offline" role="alert" aria-live="assertive"><WifiOff aria-hidden="true" /><span>The Cookfully server is unavailable. Cached kitchen data stays available; changes need a connection.</span></aside>;
  }
  return <aside className="runtime-banner runtime-banner--offline" role="alert" aria-live="assertive"><WifiOff aria-hidden="true" /><span>You’re offline. Cached kitchen data stays available; changes will need a connection.</span></aside>;
}

export function ForegroundRefresh() {
  const queryClient = useQueryClient();
  useEffect(() => {
    const refresh = () => {
      if (document.visibilityState === "visible") {
        void queryClient.invalidateQueries({ refetchType: "active" });
      }
    };
    document.addEventListener("visibilitychange", refresh);
    window.addEventListener("pageshow", refresh);
    return () => {
      document.removeEventListener("visibilitychange", refresh);
      window.removeEventListener("pageshow", refresh);
    };
  }, [queryClient]);
  return null;
}

export function PwaUpdateBanner() {
  const [available, setAvailable] = useState(false);
  useEffect(() => subscribeToPwaEvent(pwaEvents.update, () => setAvailable(true)), []);
  if (!available) return null;
  return <aside className="runtime-banner runtime-banner--update" role="status" aria-live="polite"><RefreshCw aria-hidden="true" /><span>A newer Cookfully is ready.</span><Button size="sm" onClick={() => window.location.reload()}>Refresh</Button></aside>;
}

export function PwaInstallCard() {
  const [installAvailable, setInstallAvailable] = useState(canInstallProgressiveWebApp);
  const [installed, setInstalled] = useState(isRunningAsInstalledApp);
  const ios = isIosDevice();

  useEffect(() => {
    const update = () => {
      setInstallAvailable(canInstallProgressiveWebApp());
      setInstalled(isRunningAsInstalledApp());
    };
    const unsubscribe = subscribeToPwaEvent(pwaEvents.install, update);
    window.addEventListener("pageshow", update);
    return () => {
      unsubscribe();
      window.removeEventListener("pageshow", update);
    };
  }, []);

  async function install() {
    const accepted = await promptProgressiveWebAppInstall();
    if (accepted) setInstalled(true);
    setInstallAvailable(canInstallProgressiveWebApp());
  }

  return (
    <section className="settings-system-intro pwa-install-card" aria-labelledby="pwa-install-title">
      <div className="pwa-install-card__heading"><Download aria-hidden="true" /><div><p className="eyebrow">This device</p><h2 id="pwa-install-title">Cookfully on your phone</h2></div></div>
      {installed ? <p className="success-text" role="status">Cookfully is installed. Open it from your home screen for a focused cooking view.</p> : installAvailable ? <><p>Add the kitchen to your home screen for faster access and a standalone cooking view.</p><Button type="button" onClick={() => void install()}><Download aria-hidden="true" />Install Cookfully</Button></> : ios ? <p>In Safari, tap Share, then <strong>Add to Home Screen</strong>. Cookfully will open like an app and keep your kitchen on this device.</p> : <p>Use your browser menu and choose <strong>Install app</strong> or <strong>Add to home screen</strong>. The option appears after this site is opened over HTTPS.</p>}
    </section>
  );
}
