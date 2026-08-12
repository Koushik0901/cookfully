import { Navigate, Route, Routes } from "react-router-dom";

import { Button, EmptyState, MacroPreview, MacroRing } from "../components";
import { GoalSettingsPage } from "../features/goals/GoalSettingsPage";
import { GroceryListPage } from "../features/grocery/GroceryListPage";
import { OwnerFoodsPage } from "../features/foods/OwnerFoodsPage";
import { WeeklyPlannerPage } from "../features/plans/WeeklyPlannerPage";
import { PantryPage } from "../features/pantry/PantryPage";
import { RecipeDetailPage } from "../features/recipes/RecipeDetailPage";
import { RecipeEditorPage } from "../features/recipes/RecipeEditorPage";
import { RecipeLibraryPage } from "../features/recipes/RecipeLibraryPage";
import { CookModePage } from "../features/recipes/CookModePage";
import { AgentAccessPage } from "../features/settings/AgentAccessPage";
import { SuggestionPage } from "../features/suggestions/SuggestionPage";
import { AppProviders, RequireAuthentication } from "./providers";

const WORKFLOW = [
  {
    index: "01",
    title: "Import from anywhere",
    body: "Paste a recipe URL. Ingredients, instructions, and a best-effort per-serving estimate arrive together — even when the source page publishes no nutrition at all.",
  },
  {
    index: "02",
    title: "Measure against your targets",
    body: "Set daily and per-meal calories and macros. Every recipe and every planned day is scored against the numbers you actually care about.",
  },
  {
    index: "03",
    title: "Plan, shop, correct",
    body: "Fill the week, generate the grocery list, and correct any estimate. Every correction is remembered and wins from then on.",
  },
];

function LandingPage() {
  return (
    <main className="landing">
      <header className="landing__topbar">
        <span className="landing__brand">Cookfully</span>
        <span className="landing__pill">Self-hosted</span>
      </header>
      <section className="landing__hero">
        <div className="landing__copy">
          <p className="eyebrow">Self-hosted nutrition planning</p>
          <h1>Recipes become honest, correctable macro plans.</h1>
          <p className="lede">
            Pull a recipe from any URL and get a per-serving nutrition estimate you can trust. Set your
            calorie and macro targets, plan a week, and fix any number — your correction wins from then on.
          </p>
          <div className="actions">
            <Button asChild>
              <a href="/app">Open the planner</a>
            </Button>
          </div>
        </div>
        <div className="landing__visual">
          <MacroPreview />
        </div>
      </section>
      <section className="landing__features" aria-label="What the planner does">
        <ol>
          {WORKFLOW.map((step) => (
            <li key={step.index}>
              <span className="landing__index data-value">{step.index}</span>
              <div className="landing__step">
                <h3>{step.title}</h3>
                <p>{step.body}</p>
              </div>
            </li>
          ))}
        </ol>
      </section>
      <footer className="landing__footer">
        <span>Cookfully</span>
        <span>Your recipes and plans stay on your own server.</span>
      </footer>
    </main>
  );
}

function PlannerShell() {
  return (
    <>
      <nav className="app-nav" aria-label="Primary navigation"><a className="brand" href="/app/recipes"><MacroRing className="app-nav__mark" />Cookfully</a><a href="/app/recipes">Recipes</a><a href="/app/plan">Weekly plan</a><a href="/app/suggestions">Suggestions</a><a href="/app/grocery">Grocery</a><a href="/app/pantry">Pantry</a><a href="/app/foods">Foods</a><a href="/app/goals">Goals</a><a href="/app/agent-access">Agent access</a></nav>
      <Routes>
        <Route index element={<Navigate to="recipes" replace />} />
        <Route path="recipes" element={<RecipeLibraryPage />} />
        <Route path="recipes/new" element={<RecipeEditorPage />} />
        <Route path="recipes/:recipeId" element={<RecipeDetailPage />} />
        <Route path="recipes/:recipeId/cook" element={<CookModePage />} />
        <Route path="recipes/:recipeId/edit" element={<RecipeEditorPage />} />
        <Route path="plan" element={<WeeklyPlannerPage />} />
        <Route path="goals" element={<GoalSettingsPage />} />
        <Route path="grocery" element={<GroceryListPage />} />
        <Route path="pantry" element={<PantryPage />} />
        <Route path="foods" element={<OwnerFoodsPage />} />
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
