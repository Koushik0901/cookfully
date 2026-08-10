import { Navigate, Route, Routes } from "react-router-dom";

import { Button, EmptyState } from "../components";
import { GoalSettingsPage } from "../features/goals/GoalSettingsPage";
import { GroceryListPage } from "../features/grocery/GroceryListPage";
import { WeeklyPlannerPage } from "../features/plans/WeeklyPlannerPage";
import { PantryPage } from "../features/pantry/PantryPage";
import { RecipeDetailPage } from "../features/recipes/RecipeDetailPage";
import { RecipeEditorPage } from "../features/recipes/RecipeEditorPage";
import { RecipeLibraryPage } from "../features/recipes/RecipeLibraryPage";
import { AgentAccessPage } from "../features/settings/AgentAccessPage";
import { SuggestionPage } from "../features/suggestions/SuggestionPage";
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
    <>
      <nav className="app-nav" aria-label="Primary navigation"><a className="brand" href="/app/recipes">Vigor &amp; Vine</a><a href="/app/recipes">Recipes</a><a href="/app/plan">Weekly plan</a><a href="/app/suggestions">Suggestions</a><a href="/app/grocery">Grocery</a><a href="/app/pantry">Pantry</a><a href="/app/goals">Goals</a><a href="/app/agent-access">Agent access</a></nav>
      <Routes>
        <Route index element={<Navigate to="recipes" replace />} />
        <Route path="recipes" element={<RecipeLibraryPage />} />
        <Route path="recipes/new" element={<RecipeEditorPage />} />
        <Route path="recipes/:recipeId" element={<RecipeDetailPage />} />
        <Route path="recipes/:recipeId/edit" element={<RecipeEditorPage />} />
        <Route path="plan" element={<WeeklyPlannerPage />} />
        <Route path="goals" element={<GoalSettingsPage />} />
        <Route path="grocery" element={<GroceryListPage />} />
        <Route path="pantry" element={<PantryPage />} />
        <Route path="suggestions" element={<SuggestionPage />} />
        <Route path="agent-access" element={<AgentAccessPage />} />
        <Route path="*" element={<EmptyState title="Planner section coming next" description="Recipe planning is available now." action={<Button asChild><a href="/app/recipes">Open recipes</a></Button>} />} />
      </Routes>
    </>
  );
}

function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<LandingPage />} />
      <Route
        path="/app/*"
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
