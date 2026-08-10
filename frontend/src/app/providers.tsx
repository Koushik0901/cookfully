import { QueryClient, QueryClientProvider, useQuery } from "@tanstack/react-query";
import { type ReactNode, useState } from "react";
import { BrowserRouter } from "react-router-dom";

import { ErrorRecovery, Skeleton } from "../components";
import { GlobalErrorBoundary } from "./GlobalErrorBoundary";

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
      <ErrorRecovery
        title="Sign in required"
        description="Sign in with the owner account to open the planner."
        actionLabel="Return home"
        onRetry={() => window.location.assign("/")}
      />
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
