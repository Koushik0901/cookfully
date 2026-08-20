import * as Dialog from "@radix-ui/react-dialog";
import { useQuery } from "@tanstack/react-query";
import {
  BookOpenText,
  CalendarDays,
  Carrot,
  ChefHat,
  Home,
  Import,
  ListChecks,
  PackageOpen,
  Plus,
  Search,
  Settings,
  ShoppingBasket,
  Sparkles,
  X,
} from "lucide-react";
import { type KeyboardEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import { RecipeFallbackArt } from "../components/cookfully/RecipeFallbackArt";
import { planningApi } from "../features/plans/api";
import { RecipeMetadata } from "../features/recipes/RecipeMetadata";

const COMMANDS = [
  { id: "home", label: "Home", hint: "Tonight and your kitchen", to: "/app", Icon: Home, group: "Go to" },
  { id: "recipes", label: "Recipes", hint: "Browse your recipe shelf", to: "/app/recipes", Icon: BookOpenText, group: "Go to" },
  { id: "plan", label: "Plan", hint: "Shape this week", to: "/app/plan", Icon: CalendarDays, group: "Go to" },
  { id: "grocery", label: "Grocery", hint: "Shop from your plan", to: "/app/grocery", Icon: ShoppingBasket, group: "Go to" },
  { id: "pantry", label: "Pantry", hint: "Use what is on hand", to: "/app/pantry", Icon: PackageOpen, group: "Go to" },
  { id: "foods", label: "Foods", hint: "Your nutrition references", to: "/app/foods", Icon: Carrot, group: "Go to" },
  { id: "goals", label: "Nutrition guide", hint: "Adjust planning targets", to: "/app/goals", Icon: ListChecks, group: "Go to" },
  { id: "settings", label: "Settings", hint: "Account and system access", to: "/app/settings", Icon: Settings, group: "Go to" },
  { id: "new-recipe", label: "Write a recipe", hint: "Start with ingredients and method", to: "/app/recipes/new", Icon: Plus, group: "Quick actions" },
  { id: "import-recipe", label: "Import a recipe", hint: "Bring in a public page or cookbook", to: "/app/recipes?import=1", Icon: Import, group: "Quick actions" },
  { id: "plan-tonight", label: "Plan tonight", hint: "Choose dinner without leaving the planner", to: "/app/plan?slot=dinner", Icon: ChefHat, group: "Quick actions" },
  { id: "add-grocery", label: "Add a grocery item", hint: "Open the manual item row", to: "/app/grocery?add=1", Icon: ShoppingBasket, group: "Quick actions" },
] as const;

export function CommandPalette() {
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const recipes = useQuery({
    queryKey: ["planning-recipes"],
    queryFn: planningApi.recipes,
    enabled: open,
    retry: 1,
    staleTime: 30_000,
  });

  useEffect(() => {
    function openPalette() { setOpen(true); }
    function shortcut(event: globalThis.KeyboardEvent) {
      if ((event.metaKey || event.ctrlKey) && event.key.toLocaleLowerCase() === "k") {
        event.preventDefault();
        setOpen((current) => !current);
      }
    }
    window.addEventListener("cookfully:open-command", openPalette);
    window.addEventListener("keydown", shortcut);
    return () => {
      window.removeEventListener("cookfully:open-command", openPalette);
      window.removeEventListener("keydown", shortcut);
    };
  }, []);

  const normalized = query.trim().toLocaleLowerCase();
  const visibleCommands = useMemo(
    () => COMMANDS.filter((item) => !normalized || `${item.label} ${item.hint}`.toLocaleLowerCase().includes(normalized)),
    [normalized],
  );
  const visibleRecipes = useMemo(
    () => (recipes.data?.items ?? [])
      .filter((recipe) => recipe.status !== "archived" && (!normalized || recipe.title.toLocaleLowerCase().includes(normalized)))
      .slice(0, normalized ? 8 : 4),
    [normalized, recipes.data?.items],
  );

  const closeAndNavigate = useCallback((to: string) => {
    setOpen(false);
    setQuery("");
    navigate(to);
  }, [navigate]);

  function focusMenu(direction: 1 | -1, event: KeyboardEvent<HTMLElement>) {
    const items = Array.from(menuRef.current?.querySelectorAll<HTMLButtonElement>("button[data-command-item]") ?? []);
    if (!items.length) return;
    const current = items.indexOf(document.activeElement as HTMLButtonElement);
    const next = current < 0 ? (direction === 1 ? 0 : items.length - 1) : (current + direction + items.length) % items.length;
    event.preventDefault();
    items[next]?.focus();
  }

  return (
    <Dialog.Root open={open} onOpenChange={(next) => { setOpen(next); if (!next) setQuery(""); }}>
      <Dialog.Portal>
        <Dialog.Overlay className="command-overlay" />
        <Dialog.Content className="command-palette" onOpenAutoFocus={(event) => { event.preventDefault(); inputRef.current?.focus(); }}>
          <Dialog.Title className="visually-hidden">Search Cookfully</Dialog.Title>
          <Dialog.Description className="visually-hidden">Search recipes, open a kitchen destination, or start a common action.</Dialog.Description>
          <div className="command-search">
            <Search aria-hidden="true" />
            <input
              ref={inputRef}
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "ArrowDown") focusMenu(1, event);
                if (event.key === "ArrowUp") focusMenu(-1, event);
              }}
              placeholder="Search recipes or jump somewhere…"
              aria-label="Search Cookfully"
            />
            <Dialog.Close className="command-close" aria-label="Close quick search"><X aria-hidden="true" /></Dialog.Close>
          </div>
          <div
            ref={menuRef}
            className="command-results"
            role="menu"
            aria-label="Quick search results"
            onKeyDown={(event) => {
              if (event.key === "ArrowDown") focusMenu(1, event);
              if (event.key === "ArrowUp") focusMenu(-1, event);
            }}
          >
            {(["Quick actions", "Go to"] as const).map((group) => {
              const items = visibleCommands.filter((item) => item.group === group);
              if (!items.length) return null;
              return (
                <section className="command-group" key={group} aria-label={group}>
                  <h2>{group}</h2>
                  {items.map(({ id, label, hint, to, Icon }) => (
                    <button data-command-item type="button" role="menuitem" key={id} onClick={() => closeAndNavigate(to)}>
                      <Icon aria-hidden="true" /><span><strong>{label}</strong><small>{hint}</small></span><kbd>↵</kbd>
                    </button>
                  ))}
                </section>
              );
            })}
            {visibleRecipes.length ? (
              <section className="command-group command-group--recipes" aria-label="Recipes">
                <h2>Recipes</h2>
                {visibleRecipes.map((recipe) => (
                  <button data-command-item type="button" role="menuitem" key={recipe.id} onClick={() => closeAndNavigate(`/app/recipes/${recipe.id}`)}>
                    <span className="command-recipe-media">{recipe.imageUrl ? <img src={recipe.imageUrl} alt="" /> : <RecipeFallbackArt title={recipe.title} />}</span>
                    <span><strong>{recipe.title}</strong><small>{recipe.favorite ? "Favorite recipe" : "Open recipe"}</small><RecipeMetadata recipe={recipe} compact /></span>
                    <kbd>↵</kbd>
                  </button>
                ))}
              </section>
            ) : null}
            {!visibleCommands.length && !visibleRecipes.length && !recipes.isPending ? (
              <div className="command-empty"><Sparkles aria-hidden="true" /><strong>No match yet</strong><p>Try a dish name, destination, or action such as “plan tonight.”</p></div>
            ) : null}
            {recipes.isError ? <p className="command-note" role="status">Recipe search is unavailable. Navigation and actions still work.</p> : null}
          </div>
          <footer className="command-footer"><span><kbd>↑</kbd><kbd>↓</kbd> move</span><span><kbd>Esc</kbd> close</span></footer>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
