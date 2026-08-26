import * as Dialog from "@radix-ui/react-dialog";
import { useMutation, useQuery } from "@tanstack/react-query";
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

import { RecipeMedia } from "../components";
import { groceryApi } from "../features/grocery/api";
import { intelligenceApi } from "../features/intelligence/api";
import { pantryApi } from "../features/pantry/api";
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

function getWeekStartISO(): string {
  const now = new Date();
  const weekday = now.getUTCDay();
  const diff = weekday === 0 ? -6 : 1 - weekday;
  const monday = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate() + diff));
  return monday.toISOString().slice(0, 10);
}

function humanPreview(call: { name: string; arguments: Record<string, unknown> }): string {
  const args = call.arguments as Record<string, unknown>;
  const name = typeof args.name === "string" ? args.name : (typeof args.query === "string" ? args.query : "");
  const qty = args.quantity != null ? String(args.quantity) : "";
  const unit = typeof args.unit === "string" ? args.unit : "";
  const qtyUnit = [qty, unit].filter(Boolean).join(" ");
  if (call.name === "add_pantry_item" && typeof args.name === "string") {
    return `add ${qtyUnit ? qtyUnit + " " : ""}${args.name} to pantry`.trim();
  }
  if (call.name === "add_grocery_item" && typeof args.name === "string") {
    return `add ${qtyUnit ? qtyUnit + " " : ""}${args.name} to grocery`.trim();
  }
  if (call.name === "add_recipe_to_plan" && typeof args.query === "string") {
    const when = typeof args.localDate === "string" ? ` on ${args.localDate}` : "";
    const slot = typeof args.mealSlot === "string" ? ` (${args.mealSlot})` : "";
    return `add ${args.query} to plan${when}${slot}`.trim();
  }
  if (call.name === "search_recipes" && typeof args.query === "string") {
    return `search recipes for ${args.query}`;
  }
  if (name) return `${call.name}: ${qtyUnit ? qtyUnit + " " : ""}${name}`.trim();
  try {
    return `${call.name} ${JSON.stringify(args)}`;
  } catch {
    return call.name;
  }
}

export function CommandPalette() {
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const inferred = useMutation({ mutationFn: (q: string) => intelligenceApi.infer("command", q) });
  const pantryCreate = useMutation({
    mutationFn: (args: Record<string, unknown>) =>
      pantryApi.create({
        displayName: String(args.name),
        quantity: args.quantity != null ? String(args.quantity) : "1",
        unit: args.unit != null ? String(args.unit) : "count",
      }),
  });
  const groceryCreate = useMutation({
    mutationFn: (payload: { weekStart: string; args: Record<string, unknown> }) =>
      groceryApi.create(payload.weekStart, {
        displayName: String(payload.args.name),
        quantity: payload.args.quantity != null ? String(payload.args.quantity) : null,
        unit: payload.args.unit != null ? String(payload.args.unit) : null,
      } as never),
  });
  const mealPlanCreate = useMutation({
    mutationFn: async (args: Record<string, unknown>) => {
      const weekStart = typeof args.localDate === "string" ? getWeekStartFromLocalDate(String(args.localDate)) : getWeekStartISO();
      const queryText = String(args.query ?? "");
      // Resolve recipe via search - list compat, surface ambiguous
      const page = await planningApi.recipes(queryText);
      if (!page.items.length) throw new Error("No recipe match");
      const lower = queryText.toLocaleLowerCase();
      const exact = page.items.find((r) => r.title.toLocaleLowerCase() === lower);
      if (page.items.length > 1 && !exact) {
        // ambiguous: multiple matches without exact title — surface as error, do not auto-pick
        const includes = page.items.filter((r) => r.title.toLocaleLowerCase().includes(lower));
        if (includes.length !== 1) throw new Error("Ambiguous recipe match — pick one manually");
        // if exactly one includes-match among many, use it
        const match = includes[0];
        return planningApi.addEntry(weekStart, {
          localDate: String(args.localDate),
          mealSlot: String(args.mealSlot),
          recipeId: match.id,
          servings: args.servings != null ? String(args.servings) : "1",
        } as never);
      }
      const match = exact ?? page.items.find((r) => r.title.toLocaleLowerCase().includes(lower)) ?? page.items[0];
      if (!match) throw new Error("No recipe match");
      return planningApi.addEntry(weekStart, {
        localDate: String(args.localDate),
        mealSlot: String(args.mealSlot),
        recipeId: match.id,
        servings: args.servings != null ? String(args.servings) : "1",
      } as never);
    },
  });
  const inputRef = useRef<HTMLInputElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const normalized = query.trim().toLocaleLowerCase();
  const recipes = useQuery({
    queryKey: ["planning-recipes", "command", normalized],
    queryFn: ({ signal }) => planningApi.recipes(normalized, signal),
    enabled: open && normalized.length >= 2,
    retry: 1,
    staleTime: 60_000,
  });

  // C4: stale preview reset on query change and on close
  useEffect(() => {
    inferred.reset();
    pantryCreate.reset();
    groceryCreate.reset();
    mealPlanCreate.reset();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [normalized]);

  useEffect(() => {
    function openPalette() {
      setOpen(true);
    }
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

  const closeAndNavigate = useCallback(
    (to: string) => {
      setOpen(false);
      setQuery("");
      navigate(to);
    },
    [navigate],
  );

  function focusMenu(direction: 1 | -1, event: KeyboardEvent<HTMLElement>) {
    const items = Array.from(menuRef.current?.querySelectorAll<HTMLButtonElement>("button[data-command-item]") ?? []);
    if (!items.length) return;
    const current = items.indexOf(document.activeElement as HTMLButtonElement);
    const next = current < 0 ? (direction === 1 ? 0 : items.length - 1) : (current + direction + items.length) % items.length;
    event.preventDefault();
    items[next]?.focus();
  }

  function handleAdd() {
    const call = inferred.data?.functionCalls[0];
    if (!call) return;
    const args = call.arguments as Record<string, unknown>;
    if (call.name === "add_pantry_item" && typeof args.name === "string") {
      pantryCreate.mutate(args);
    } else if (call.name === "add_grocery_item" && typeof args.name === "string") {
      groceryCreate.mutate({ weekStart: getWeekStartISO(), args });
    } else if (call.name === "add_recipe_to_plan" && typeof args.query === "string" && typeof args.localDate === "string" && typeof args.mealSlot === "string") {
      mealPlanCreate.mutate(args);
    } else if (typeof args.name === "string") {
      // fallback: treat as pantry
      pantryCreate.mutate(args);
    }
  }

  const isAddPending = pantryCreate.isPending || groceryCreate.isPending || mealPlanCreate.isPending;
  const isAddSuccess = pantryCreate.isSuccess || groceryCreate.isSuccess || mealPlanCreate.isSuccess;
  const isAddError = pantryCreate.isError || groceryCreate.isError || mealPlanCreate.isError;

  return (
    <Dialog.Root
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (!next) {
          setQuery("");
          inferred.reset();
          pantryCreate.reset();
          groceryCreate.reset();
          mealPlanCreate.reset();
        }
      }}
    >
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
            <Dialog.Close className="command-close" aria-label="Close quick search">
              <X aria-hidden="true" />
            </Dialog.Close>
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
                      <Icon aria-hidden="true" />
                      <span>
                        <strong>{label}</strong>
                        <small>{hint}</small>
                      </span>
                      <kbd>↵</kbd>
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
                    <span className="command-recipe-media"><RecipeMedia recipe={recipe} loading="lazy" sizes="64px" /></span>
                    <span>
                      <strong>{recipe.title}</strong>
                      <small>{recipe.favorite ? "Favorite recipe" : "Open recipe"}</small>
                      <RecipeMetadata recipe={recipe} compact />
                    </span>
                    <kbd>↵</kbd>
                  </button>
                ))}
              </section>
            ) : null}
            {!visibleCommands.length && !visibleRecipes.length && !recipes.isPending ? (
              <div className="command-empty">
                <Sparkles aria-hidden="true" />
                <strong>No direct match yet</strong>
                <p>Ask Cookfully to interpret a grocery, pantry, recipe, or cooking action.</p>
                {!inferred.data ? (
                  <button
                    data-command-item
                    type="button"
                    role="menuitem"
                    aria-label="Interpret with Cookfully"
                    onClick={() => inferred.mutate(query.trim())}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        inferred.mutate(query.trim());
                      }
                    }}
                    disabled={inferred.isPending}
                  >
                    <Sparkles aria-hidden="true" />
                    <span>
                      <strong>{inferred.isPending ? "Understanding…" : "Interpret with Cookfully"}</strong>
                      <small>Review the proposed action before anything changes</small>
                    </span>
                    <kbd>↵</kbd>
                  </button>
                ) : inferred.data.status === "ok" && (inferred.data.confidence ?? 0) >= 0.80 && inferred.data.functionCalls[0] ? (
                  <div className="command-note" role="status" aria-live="polite">
                    <span>We think you mean: {humanPreview(inferred.data.functionCalls[0] as never)} — </span>
                    <button type="button" aria-label="Add" onClick={handleAdd} disabled={isAddPending}>
                      {isAddPending ? "Adding…" : "Add"}
                    </button>
                    {isAddSuccess ? <span> Added.</span> : null}
                    {isAddError ? <span role="alert"> Couldn’t add. Try manually.</span> : null}
                  </div>
                ) : (
                  <div className="command-note" role="status" aria-live="polite">
                    <span>Not sure — Add manually? </span>
                    <a href="/app/pantry?add=1">Open pantry</a>
                  </div>
                )}
              </div>
            ) : null}
            {recipes.isError ? <p className="command-note" role="status" aria-live="polite">Recipe search is unavailable. Navigation and actions still work.</p> : null}
          </div>
          <footer className="command-footer">
            <span>
              <kbd>↑</kbd>
              <kbd>↓</kbd> move
            </span>
            <span>
              <kbd>Esc</kbd> close
            </span>
          </footer>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

function getWeekStartFromLocalDate(localDate: string): string {
  const d = new Date(localDate + "T00:00:00.000Z");
  if (Number.isNaN(d.getTime())) return getWeekStartISO();
  const weekday = d.getUTCDay();
  const diff = weekday === 0 ? -6 : 1 - weekday;
  const monday = new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate() + diff));
  return monday.toISOString().slice(0, 10);
}
