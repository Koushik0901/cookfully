import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createBrowserRouter, Link, Navigate, NavLink, Route, Routes, RouterProvider, useLocation } from "react-router-dom";

import {
  BookOpenText,
  CalendarDays,
  Carrot,
  CircleEllipsis,
  Home,
  ListChecks,
  LogOut,
  PackageOpen,
  Search,
  ShoppingBasket,
  SlidersHorizontal,
} from "lucide-react";

import { BrandMark, Button, EmptyState, Skeleton } from "../components";
import { useSignOut } from "../features/settings/useSignOut";
import { CommandPalette } from "./CommandPalette";
import { AppProviders, RequireAuthentication } from "./providers";

const HomePage = lazy(() => import("../features/home/HomePage").then((module) => ({ default: module.HomePage })));
const CookModePage = lazy(() => import("../features/recipes/CookModePage").then((module) => ({ default: module.CookModePage })));
const AgentAccessPage = lazy(() => import("../features/settings/AgentAccessPage").then((module) => ({ default: module.AgentAccessPage })));
const GoalSettingsPage = lazy(() => import("../features/goals/GoalSettingsPage").then((module) => ({ default: module.GoalSettingsPage })));
const GroceryListPage = lazy(() => import("../features/grocery/GroceryListPage").then((module) => ({ default: module.GroceryListPage })));
const OwnerFoodsPage = lazy(() => import("../features/foods/OwnerFoodsPage").then((module) => ({ default: module.OwnerFoodsPage })));
const PantryPage = lazy(() => import("../features/pantry/PantryPage").then((module) => ({ default: module.PantryPage })));
const RecipeDetailPage = lazy(() => import("../features/recipes/RecipeDetailPage").then((module) => ({ default: module.RecipeDetailPage })));
const RecipeEditorPage = lazy(() => import("../features/recipes/RecipeEditorPage").then((module) => ({ default: module.RecipeEditorPage })));
const RecipeLibraryPage = lazy(() => import("../features/recipes/RecipeLibraryPage").then((module) => ({ default: module.RecipeLibraryPage })));
const SettingsPage = lazy(() => import("../features/settings/SettingsPage").then((module) => ({ default: module.SettingsPage })));
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
  { to: "/app", label: "Home", Icon: Home, end: true },
  { to: "/app/recipes", label: "Recipes", Icon: BookOpenText },
  { to: "/app/plan", label: "Plan", Icon: CalendarDays },
  { to: "/app/grocery", label: "Grocery", Icon: ShoppingBasket },
  { to: "/app/pantry", label: "Pantry", Icon: PackageOpen },
] as const;

const SECONDARY_NAVIGATION = [
  { to: "/app/foods", label: "Foods", Icon: Carrot },
  { to: "/app/goals", label: "Goals", Icon: ListChecks },
] as const;

const MOBILE_NAVIGATION = PRIMARY_NAVIGATION.filter(({ label }) => label !== "Pantry");

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
  const signOut = useSignOut();
  const location = useLocation();
  const [moreOpen, setMoreOpen] = useState(false);
  const moreTriggerRef = useRef<HTMLButtonElement>(null);
  const moreMenuRef = useRef<HTMLDivElement>(null);
  const atHome = location.pathname.replace(/\/$/, "") === "/app";
  const moreIsActive = [
    "/app/pantry",
    ...SECONDARY_NAVIGATION.map(({ to }) => to),
    "/app/settings",
  ].some((path) => location.pathname.startsWith(path));

  const toggleMore = useCallback(() => setMoreOpen((value) => !value), []);
  const closeMore = useCallback(() => setMoreOpen(false), []);

  useEffect(() => {
    if (!moreOpen) return;
    function handleKey(event: KeyboardEvent) {
      if (event.key === "Escape") {
        closeMore();
        moreTriggerRef.current?.focus();
      }
    }
    function handleClick(event: MouseEvent) {
      if (moreMenuRef.current && !moreMenuRef.current.contains(event.target as Node) && !moreTriggerRef.current?.contains(event.target as Node)) {
        closeMore();
      }
    }
    document.addEventListener("keydown", handleKey);
    document.addEventListener("mousedown", handleClick);
    return () => {
      document.removeEventListener("keydown", handleKey);
      document.removeEventListener("mousedown", handleClick);
    };
  }, [moreOpen, closeMore]);

  return (
    <div className="planner-shell">
      <a href="#planner-content" className="skip-link">Skip to content</a>
      <aside className="planner-nav">
        <NavLink className="planner-nav__brand" to="/app" end>
          <span className="planner-nav__brandmark" aria-hidden="true">♨</span>
          <span className="visually-hidden">Cookfully home</span>
        </NavLink>
        <nav aria-label="Kitchen">
          {PRIMARY_NAVIGATION.map(({ to, label, Icon, ...item }) => (
            <NavLink key={to} to={to} end={"end" in item ? item.end : undefined} title={label} className={({ isActive }) => isActive ? "planner-nav__link planner-nav__link--active" : "planner-nav__link"}>
              <Icon aria-hidden="true" /><span>{label}</span>
            </NavLink>
          ))}
        </nav>
        <nav aria-label="Account" className="planner-nav__account">
          <NavLink
            to="/app/settings"
            title="Settings"
            className={({ isActive }) => isActive ? "planner-nav__link planner-nav__link--active" : "planner-nav__link"}
          >
            <SlidersHorizontal aria-hidden="true" /><span>Settings</span>
          </NavLink>
        </nav>
      </aside>
      <div className="planner-shell__mobile-brand">
        <NavLink to="/app" aria-label="Cookfully home"><BrandMark /><strong>Cookfully</strong></NavLink>
        {atHome ? null : <button type="button" aria-label="Open quick search" onClick={() => window.dispatchEvent(new Event("cookfully:open-command"))}><Search aria-hidden="true" /></button>}
      </div>
      <nav className="mobile-nav" aria-label="Primary navigation">
        {MOBILE_NAVIGATION.map(({ to, label, Icon, ...item }) => (
          <NavLink key={to} to={to} end={"end" in item ? item.end : undefined} className={({ isActive }) => isActive ? "mobile-nav__link mobile-nav__link--active" : "mobile-nav__link"}>
            <Icon aria-hidden="true" /><span>{label}</span>
          </NavLink>
        ))}
        <div className={`mobile-nav__more ${moreIsActive ? "mobile-nav__more--active" : ""}`}>
          <button
            ref={moreTriggerRef}
            type="button"
            className="mobile-nav__more-trigger"
            aria-expanded={moreOpen}
            aria-haspopup="menu"
            onClick={toggleMore}
          >
            <CircleEllipsis aria-hidden="true" /><span>More</span>
          </button>
          {moreOpen ? (
            <div ref={moreMenuRef} className="mobile-nav__menu" role="menu" aria-label="More navigation">
              <NavLink to="/app/pantry" role="menuitem" onClick={closeMore}>
                <PackageOpen aria-hidden="true" /><span>Pantry</span>
              </NavLink>
              {SECONDARY_NAVIGATION.map(({ to, label, Icon }) => (
                <NavLink key={to} to={to} role="menuitem" onClick={closeMore}>
                  <Icon aria-hidden="true" /><span>{label}</span>
                </NavLink>
              ))}
              <div className="mobile-nav__menu-divider" role="separator" />
              <NavLink to="/app/settings" role="menuitem" onClick={closeMore}>
                <SlidersHorizontal aria-hidden="true" /><span>Settings</span>
              </NavLink>
              <button type="button" role="menuitem" onClick={() => signOut.mutate()} disabled={signOut.isPending}>
                <LogOut aria-hidden="true" /><span>{signOut.isPending ? "Signing out…" : "Sign out"}</span>
              </button>
              {signOut.isError ? <p className="mobile-nav__error" role="alert">Couldn't sign out. Try again.</p> : null}
            </div>
          ) : null}
        </div>
      </nav>
      <CommandPalette />
      <main id="planner-content" className="planner-shell__content">
        <Suspense fallback={<div className="page-shell"><Skeleton label="Loading kitchen" lines={6} /></div>}>
          <Routes>
            <Route index element={<HomePage />} />
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
             <Route path="agent-access" element={<AgentAccessPage />} />
             <Route path="suggestions" element={<SuggestionPage />} />
            <Route path="settings" element={<SettingsPage />} />
            <Route path="*" element={<div className="page-shell utility-page"><EmptyState title="That kitchen page isn’t here" description="The link may be old, but your recipes and plans are still safe." action={<><Button asChild><Link to="/app">Return home</Link></Button><Button variant="secondary" asChild><Link to="/app/recipes">Open recipes</Link></Button></>} /></div>} />
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
  const router = useMemo(
    () => createBrowserRouter([{ path: "*", element: <AppProviders><AppRoutes /></AppProviders> }]),
    [],
  );
  return <RouterProvider router={router} />;
}
