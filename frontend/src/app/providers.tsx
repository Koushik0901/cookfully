import { QueryClient, QueryClientProvider, useQuery } from "@tanstack/react-query";
import { type ReactNode, useState } from "react";
import { BrowserRouter } from "react-router-dom";

import { ErrorRecovery, MacroRing, Skeleton } from "../components";
import { GlobalErrorBoundary } from "./GlobalErrorBoundary";
import { LoginForm } from "./LoginForm";

async function verifySession(): Promise<boolean> {
  const response = await fetch("/api/v1/owner/preferences", {
    credentials: "same-origin",
    headers: { accept: "application/json" },
  });
  if (response.status === 401) return false;
  if (!response.ok) throw new Error("Unable to verify your session.");
  return true;
}

export function RequireAuthentication({ children }: { children: ReactNode }) {
  const session = useQuery({ queryKey: ["owner-session"], queryFn: verifySession, retry: 1 });
  if (session.isPending) return <Skeleton label="Checking your session" lines={3} />;
  if (session.isError) {
    return <ErrorRecovery title="Session check failed" onRetry={() => void session.refetch()} />;
  }
  if (!session.data) {
    return (
      <main className="auth-screen">
        <div className="auth-screen__glow" aria-hidden="true" />
        <MacroRing className="auth-screen__ring" />
        <section className="auth-card" aria-label="Sign in">
          <p className="eyebrow">Self-hosted nutrition planning</p>
          <h1>Sign in to your planner</h1>
          <p className="lede">Recipes become honest, correctable macro plans.</p>
          <LoginForm />
          <p className="auth-card__footnote">Single-owner instance · your data stays on your server</p>
        </section>
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
          queries: { staleTime: 30_000, refetchOnWindowFocus: false },
          mutations: { retry: false },
        },
      }),
  );
  return (
    <GlobalErrorBoundary>
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>{children}</BrowserRouter>
      </QueryClientProvider>
    </GlobalErrorBoundary>
  );
}
