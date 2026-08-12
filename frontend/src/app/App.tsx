import { lazy, Suspense } from "react";
import { Navigate, NavLink, Route, Routes } from "react-router-dom";

import {
  BookOpenText,
  CalendarDays,
  Carrot,
  CircleEllipsis,
  ListChecks,
  PackageOpen,
  ShoppingBasket,
} from "lucide-react";

import { BrandMark, Button, EmptyState, Skeleton } from "../components";
import { AppProviders, RequireAuthentication } from "./providers";

const AgentAccessPage = lazy(() => import("../features/settings/AgentAccessPage").then((module) => ({ default: module.AgentAccessPage })));
const CookModePage = lazy(() => import("../features/recipes/CookModePage").then((module) => ({ default: module.CookModePage })));
const GoalSettingsPage = lazy(() => import("../features/goals/GoalSettingsPage").then((module) => ({ default: module.GoalSettingsPage })));
const GroceryListPage = lazy(() => import("../features/grocery/GroceryListPage").then((module) => ({ default: module.GroceryListPage })));
const OwnerFoodsPage = lazy(() => import("../features/foods/OwnerFoodsPage").then((module) => ({ default: module.OwnerFoodsPage })));
const PantryPage = lazy(() => import("../features/pantry/PantryPage").then((module) => ({ default: module.PantryPage })));
const RecipeDetailPage = lazy(() => import("../features/recipes/RecipeDetailPage").then((module) => ({ default: module.RecipeDetailPage })));
const RecipeEditorPage = lazy(() => import("../features/recipes/RecipeEditorPage").then((module) => ({ default: module.RecipeEditorPage })));
const RecipeLibraryPage = lazy(() => import("../features/recipes/RecipeLibraryPage").then((module) => ({ default: module.RecipeLibraryPage })));
const SuggestionPage = lazy(() => import("../features/suggestions/SuggestionPage").then((module) => ({ default: module.SuggestionPage })));
const WeeklyPlannerPage = lazy(() => import("../features/plans/WeeklyPlannerPage").then((module) => ({ default: module.WeeklyPlannerPage })));

const WORKFLOW = [
  {
    index: "01",
    title: "Bring in a recipe",
    body: "Save a favorite from the web or write your own. Ingredients, method, and a useful nutrition estimate stay together.",
  },
  {
    index: "02",
    title: "Build a realistic week",
    body: "Plan one meal or seven days. Adjust servings as life changes and let your grocery list follow along.",
  },
  {
    index: "03",
    title: "Understand the balance",
    body: "See the nutrition that matters without turning dinner into a spreadsheet. Correct an estimate whenever you know better.",
  },
];

const PRIMARY_NAVIGATION = [
  { to: "/app/recipes", label: "Recipes", Icon: BookOpenText },
  { to: "/app/plan", label: "Plan", Icon: CalendarDays },
  { to: "/app/grocery", label: "Grocery", Icon: ShoppingBasket },
  { to: "/app/pantry", label: "Pantry", Icon: PackageOpen },
] as const;

const SECONDARY_NAVIGATION = [
  { to: "/app/foods", label: "Foods", Icon: Carrot },
  { to: "/app/goals", label: "Goals", Icon: ListChecks },
] as const;

function LandingPage() {
  return (
    <main className="landing">
      <header className="landing__topbar">
        <span className="landing__brand"><BrandMark />Cookfully</span>
        <span className="landing__pill">Self-hosted</span>
      </header>
      <section className="landing__hero">
        <div className="landing__copy">
          <p className="eyebrow">A calmer way to eat well</p>
          <h1>Good food. Clear choices. Your kind of healthy.</h1>
          <p className="lede">
            Keep the recipes you love, plan meals that fit real life, and understand the nutrition without
            doing the math yourself.
          </p>
          <div className="actions">
            <Button asChild>
              <a href="/app">Open Cookfully</a>
            </Button>
          </div>
        </div>
        <figure className="landing__visual">
          <img
            src="/cookfully-hero-balanced-table.png"
            alt="Roasted vegetables, grains, greens, and salmon served for a balanced meal"
          />
          <figcaption>
            <span>Dinner, understood</span>
            <strong>Herbed salmon grain bowl</strong>
            <small><i className="nutrient-dot nutrient-dot--protein" aria-hidden="true" /> 38 g protein · estimated per serving</small>
          </figcaption>
        </figure>
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
    <div className="planner-shell">
      <aside className="planner-nav">
        <NavLink className="planner-nav__brand" to="/app/recipes">
          <BrandMark />
          <span>Cookfully</span>
        </NavLink>
        <nav aria-label="Kitchen">
          <p className="planner-nav__label">Kitchen</p>
          {PRIMARY_NAVIGATION.map(({ to, label, Icon }) => (
            <NavLink key={to} to={to} className={({ isActive }) => isActive ? "planner-nav__link planner-nav__link--active" : "planner-nav__link"}>
              <Icon aria-hidden="true" /><span>{label}</span>
            </NavLink>
          ))}
        </nav>
        <nav aria-label="Your space" className="planner-nav__secondary">
          <p className="planner-nav__label">Your space</p>
          {SECONDARY_NAVIGATION.map(({ to, label, Icon }) => (
            <NavLink key={to} to={to} className={({ isActive }) => isActive ? "planner-nav__link planner-nav__link--active" : "planner-nav__link"}>
              <Icon aria-hidden="true" /><span>{label}</span>
            </NavLink>
          ))}
        </nav>
        <p className="planner-nav__promise">Your food stays on your server.</p>
      </aside>
      <div className="planner-shell__mobile-brand"><BrandMark /><strong>Cookfully</strong></div>
      <nav className="mobile-nav" aria-label="Primary navigation">
        {PRIMARY_NAVIGATION.map(({ to, label, Icon }) => (
          <NavLink key={to} to={to} className={({ isActive }) => isActive ? "mobile-nav__link mobile-nav__link--active" : "mobile-nav__link"}>
            <Icon aria-hidden="true" /><span>{label}</span>
          </NavLink>
        ))}
        <details className="mobile-nav__more">
          <summary><CircleEllipsis aria-hidden="true" /><span>More</span></summary>
          <div className="mobile-nav__menu">
            {SECONDARY_NAVIGATION.map(({ to, label, Icon }) => (
              <NavLink key={to} to={to}><Icon aria-hidden="true" /><span>{label}</span></NavLink>
            ))}
          </div>
        </details>
      </nav>
      <main className="planner-shell__content">
        <Suspense fallback={<div className="page-shell"><Skeleton label="Loading kitchen" lines={6} /></div>}>
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
        </Suspense>
      </main>
    </div>
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
