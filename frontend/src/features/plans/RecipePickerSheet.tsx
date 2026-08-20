import * as Dialog from "@radix-ui/react-dialog";
import { CookingPot, Search, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { RecipeFallbackArt } from "../../components/cookfully/RecipeFallbackArt";
import { RecipeMetadata } from "../recipes/RecipeMetadata";
import { formatCookingNumber } from "../recipes/formatCooking";
import type { RecipePage } from "./types";

type Recipe = RecipePage["items"][number];

export function RecipePickerSheet({
  open,
  onOpenChange,
  recipes,
  mealSlot,
  dateLabel,
  pendingRecipeId,
  error,
  loading = false,
  unavailableRecipeCount = 0,
  libraryError,
  onRetry,
  onChoose,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  recipes: Recipe[];
  mealSlot: string;
  dateLabel: string;
  pendingRecipeId?: string;
  error?: string;
  loading?: boolean;
  unavailableRecipeCount?: number;
  libraryError?: string;
  onRetry?: () => void;
  onChoose: (recipeId: string) => void;
}) {
  const [query, setQuery] = useState("");
  useEffect(() => {
    if (!open) setQuery("");
  }, [open]);

  const visibleRecipes = useMemo(() => {
    const normalized = query.trim().toLocaleLowerCase();
    return normalized ? recipes.filter((recipe) => recipe.title.toLocaleLowerCase().includes(normalized)) : recipes;
  }, [query, recipes]);

  const slotLabel = mealSlot[0]?.toUpperCase() + mealSlot.slice(1);

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="recipe-picker-overlay" />
        <Dialog.Content className="recipe-picker-sheet">
          <div className="recipe-picker__header">
            <div>
              <p className="eyebrow">{slotLabel} · {dateLabel}</p>
              <Dialog.Title>Add a recipe</Dialog.Title>
              <Dialog.Description>Choose something you already love. Cookfully will add one serving, ready for you to adjust.</Dialog.Description>
            </div>
            <Dialog.Close className="recipe-picker__close" aria-label="Close recipe picker"><X aria-hidden="true" /></Dialog.Close>
          </div>

          <label className="recipe-picker__search">
            <span className="visually-hidden">Search recipes</span>
            <Search aria-hidden="true" />
            <input autoFocus className="input" type="search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search your recipes" />
          </label>

          {error ? <p className="error-text" role="alert">{error}</p> : null}

          <div className="recipe-picker__results" aria-live="polite">
            {loading ? (
              <div className="recipe-picker__loading" role="status" aria-label="Loading recipes">{Array.from({ length: 4 }, (_, index) => <span key={index}><i /><b /><small /></span>)}</div>
            ) : libraryError ? (
              <div className="recipe-picker__empty" role="alert">
                <CookingPot aria-hidden="true" />
                <strong>Recipes could not be loaded</strong>
                <p>{libraryError}</p>
                {onRetry ? <button className="text-link" type="button" onClick={onRetry}>Try again</button> : null}
              </div>
            ) : visibleRecipes.length ? visibleRecipes.map((recipe) => {
              const pending = pendingRecipeId === recipe.id;
              const yieldUnit = Number(recipe.yieldQuantity) === 1 && recipe.yieldUnit.toLocaleLowerCase() === "servings" ? "serving" : recipe.yieldUnit;
              return (
                <button className="recipe-pick" type="button" key={recipe.id} disabled={Boolean(pendingRecipeId)} onClick={() => onChoose(recipe.id)} aria-label={`Add ${recipe.title} to ${slotLabel}`}>
                  <span className={`recipe-pick__media ${recipe.imageUrl ? "" : "recipe-pick__media--fallback"}`}>
                    {recipe.imageUrl ? <img src={recipe.imageUrl} alt="" loading="lazy" decoding="async" /> : <RecipeFallbackArt title={recipe.title} />}
                  </span>
                  <span className="recipe-pick__copy">
                    <strong>{recipe.title}</strong>
                    <small>Makes {formatCookingNumber(recipe.yieldQuantity)} {yieldUnit}</small>
                    <RecipeMetadata recipe={recipe} compact />
                  </span>
                  <span className="recipe-pick__action">{pending ? "Adding…" : "Add"}</span>
                </button>
              );
            }) : (
              <div className="recipe-picker__empty">
                <CookingPot aria-hidden="true" />
                <strong>{query ? "No recipes match that search" : unavailableRecipeCount ? "No recipes are ready to plan" : "Your recipe shelf is empty"}</strong>
                <p>{query ? "Try a shorter dish name or clear the search." : unavailableRecipeCount ? "Finish or refresh the nutrition estimate on a recipe, then it can join the plan." : "Save a recipe first, then come back to place it in your week."}</p>
              </div>
            )}
          </div>

          <div className="recipe-picker__footer">
            <span>Can’t find the dish you need?</span>
            <Dialog.Close asChild><Link to="/app/recipes/new">Create a recipe</Link></Dialog.Close>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
