import { QueryClient, QueryClientProvider, useQuery } from "@tanstack/react-query";
import { type ReactNode, useState } from "react";

import { BrandMark, ErrorRecovery, Skeleton } from "../components";
import { verifyKitchenSession } from "./kitchenRuntime";
import { ForegroundRefresh, NetworkStatusBanner, PwaUpdateBanner } from "./MobileRuntime";
import { GlobalErrorBoundary } from "./GlobalErrorBoundary";
import { LoginForm } from "./LoginForm";
import { setSessionQueryClient } from "./sessionStore";


export function RequireAuthentication({ children }: { children: ReactNode }) {
  const session = useQuery({ queryKey: ["owner-session"], queryFn: verifyKitchenSession, retry: 1 });
  if (session.isPending) return <main className="utility-screen"><section className="utility-screen__card"><div className="utility-screen__brand"><BrandMark /><strong>Cookfully</strong></div><p className="eyebrow">Opening your kitchen</p><Skeleton label="Checking your session" lines={3} /></section></main>;
  if (session.isError) {
    return <main className="utility-screen"><section className="utility-screen__card"><div className="utility-screen__brand"><BrandMark /><strong>Cookfully</strong></div><p className="eyebrow">Your kitchen is still safe</p><ErrorRecovery title="Session check failed" description="Cookfully could not confirm this browser session. Try the connection again." onRetry={() => void session.refetch()} /></section></main>;
  }
  if (!session.data) {
    return (
      <main className="auth-screen">
        <div className="auth-layout">
          <figure className="auth-visual">
            <picture>
              <source type="image/avif" srcSet="/cookfully-hero-balanced-table-960.avif 960w, /cookfully-hero-balanced-table-1440.avif 1440w" sizes="(max-width: 900px) 0px, 50vw" />
              <source type="image/webp" srcSet="/cookfully-hero-balanced-table-960.webp 960w, /cookfully-hero-balanced-table-1440.webp 1440w" sizes="(max-width: 900px) 0px, 50vw" />
              <img src="/cookfully-hero-balanced-table-960.webp" width="1536" height="1024" alt="A balanced salmon grain bowl with roasted vegetables" />
            </picture>
            <figcaption>
              <span>Cook with clarity</span>
              <strong>Good food, organized around your life.</strong>
            </figcaption>
          </figure>
          <section className="auth-card" aria-label="Sign in">
            <a className="auth-card__brand" href="/"><BrandMark />Cookfully</a>
            <div>
              <p className="eyebrow">Your kitchen, in one place</p>
              <h1>Welcome back</h1>
              <p className="lede">Pick up your recipes, weekly plan, and grocery list.</p>
            </div>
            <LoginForm />
            <p className="auth-card__footnote">Private by design · your data stays on your server</p>
          </section>
        </div>
      </main>
    );
  }
  return children;
}

export function AppProviders({ children }: { children: ReactNode }) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 30_000,
            gcTime: 5 * 60_000,
            retry: 1,
            networkMode: "offlineFirst",
            refetchOnWindowFocus: false,
            refetchOnReconnect: true,
          },
          mutations: { retry: false },
        },
      }),
  );
  setSessionQueryClient(queryClient);
  return (
      <GlobalErrorBoundary>
      <QueryClientProvider client={queryClient}>
        <NetworkStatusBanner />
        <PwaUpdateBanner />
        <ForegroundRefresh />
        {children}
      </QueryClientProvider>
      </GlobalErrorBoundary>
  );
}
