import { Navigate, Route, Routes } from "react-router-dom";

import { Button, EmptyState } from "../components";
import { AppProviders, RequireAuthentication } from "./providers";

function LandingPage() {
  return (
    <main className="app-shell">
      <p className="eyebrow">Self-hosted nutrition planning</p>
      <h1>Vigor &amp; Vine</h1>
      <p className="lede">Recipes become honest, correctable macro plans.</p>
      <div className="actions">
        <Button asChild>
          <a href="/app">Open planner</a>
        </Button>
      </div>
    </main>
  );
}

function PlannerShell() {
  return (
    <main className="app-shell">
      <EmptyState
        title="Your planner is ready"
        description="Add a recipe to begin building an evidence-backed weekly plan."
        action={<Button>Add recipe</Button>}
      />
    </main>
  );
}

function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<LandingPage />} />
      <Route
        path="/app"
        element={
          <RequireAuthentication>
            <PlannerShell />
          </RequireAuthentication>
        }
      />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

export function App() {
  return (
    <AppProviders>
      <AppRoutes />
    </AppProviders>
  );
}
