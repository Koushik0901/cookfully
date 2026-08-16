import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { Archive, Check, Heart, MoreVertical, Pencil, RotateCcw, Trash2 } from "lucide-react";

import { ConfirmDialog, PollingStatusBadge } from "../../components";
import { RecipeFallbackArt } from "../../components/cookfully/RecipeFallbackArt";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "../../components/ui/dropdown-menu";
import { recipesApi } from "./api";
import { servingLabel } from "./formatCooking";
import type { Recipe } from "./types";

const STATE_LABELS: Record<string, string> = {
  stale: "Outdated",
  pending: "Estimating…",
  failed: "Unavailable",
  manual: "Manual",
  partial: "Partial estimate",
  estimated: "Estimated",
  source_provided: "Source provided",
};

export function RecipeCard({
  recipe,
  onArchive,
  onRestore,
  onDelete,
}: {
  recipe: Recipe;
  onArchive: (id: string, version: number) => void;
  onRestore: (id: string, version: number) => void;
  onDelete: (id: string, version: number) => void;
}) {
  const queryClient = useQueryClient();
  const [confirmDelete, setConfirmDelete] = useState(false);
  const nutrition = recipe.nutrition;
  const displayedNutritionState = ["stale", "pending", "failed"].includes(recipe.nutritionState)
    ? recipe.nutritionState
    : nutrition?.status === "manual" ? "manual" : recipe.nutritionState;
  const stateLabel = STATE_LABELS[displayedNutritionState] ?? displayedNutritionState.replace("_", " ");
  const collections = useQuery({ queryKey: ["recipe-collections"], queryFn: recipesApi.collections, retry: 1 });
  const membership = (recipe.collections ?? []).map((item) => item.id);
  const organize = useMutation({
    mutationFn: (collectionIds: string[]) =>
      recipesApi.organize(recipe.id, recipe.version, {
        favorite: Boolean(recipe.favorite),
        collectionIds,
        mealRoles: recipe.mealRoles ?? [],
      }),
    onSuccess: (value) => {
      queryClient.setQueryData(["recipe", recipe.id], value);
      void queryClient.invalidateQueries({ queryKey: ["recipes"] });
      void queryClient.invalidateQueries({ queryKey: ["recipe-collections"] });
    },
  });
  const toggleCollection = (collectionId: string) => {
    const next = membership.includes(collectionId)
      ? membership.filter((id) => id !== collectionId)
      : [...membership, collectionId];
    organize.mutate(next);
  };
  const displayNumber = (value: string | null | undefined, maximumFractionDigits: number) =>
    value == null
      ? "—"
      : new Intl.NumberFormat(undefined, { maximumFractionDigits }).format(Number(value));
  return (
    <article className="recipe-card">
      <Link className="recipe-card__media" to={`/app/recipes/${recipe.id}`} aria-label={`Open ${recipe.title}`}>
        {recipe.imageUrl ? <img src={recipe.imageUrl} alt="" loading="lazy" decoding="async" /> : <RecipeFallbackArt title={recipe.title} />}
        {recipe.favorite ? <span className="recipe-card__favorite" aria-label="Favorite recipe"><Heart aria-hidden="true" /></span> : null}
      </Link>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <button type="button" className="recipe-card__menu" aria-label={`More actions for ${recipe.title}`}><MoreVertical aria-hidden="true" /></button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          <DropdownMenuItem asChild><Link to={`/app/recipes/${recipe.id}/edit`}><Pencil aria-hidden="true" />Edit recipe</Link></DropdownMenuItem>
          <DropdownMenuSeparator />
          <p className="cf-menu__label">Collections</p>
          {Array.isArray(collections.data) && collections.data.length ? collections.data.map((collection) => {
            const active = membership.includes(collection.id);
            return (
              <DropdownMenuItem key={collection.id} onSelect={() => toggleCollection(collection.id)}>
                <span className="cf-menu__check">{active ? <Check aria-hidden="true" /> : null}</span>
                {collection.name}
              </DropdownMenuItem>
            );
          }) : <p className="cf-menu__empty">No collections yet. Create one under “Refine recipes”.</p>}
          <DropdownMenuSeparator />
          {recipe.status === "archived" ? (
            <DropdownMenuItem onSelect={() => onRestore(recipe.id, recipe.version)}><RotateCcw aria-hidden="true" />Restore recipe</DropdownMenuItem>
          ) : (
            <DropdownMenuItem onSelect={() => onArchive(recipe.id, recipe.version)}><Archive aria-hidden="true" />Archive recipe</DropdownMenuItem>
          )}
          <DropdownMenuItem variant="destructive" onSelect={() => setConfirmDelete(true)}><Trash2 aria-hidden="true" />Delete recipe</DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
      <ConfirmDialog
        open={confirmDelete}
        onOpenChange={setConfirmDelete}
        title="Permanently delete this recipe?"
        description="Recipe content and media will be erased after the bounded recovery window. Historical plan and grocery records remain detached so their past facts stay accurate."
        confirmLabel="Delete permanently"
        onConfirm={() => { setConfirmDelete(false); onDelete(recipe.id, recipe.version); }}
      />
      <div className="recipe-card__body">
        <div className="recipe-card__heading">
          <h2><Link to={`/app/recipes/${recipe.id}`}>{recipe.title}</Link></h2>
          {recipe.status === "processing" ? <PollingStatusBadge status="running" /> : null}
        </div>
        <p className="recipe-card__yield data-value">
          Makes {servingLabel(recipe.yieldQuantity, recipe.yieldUnit)}
          {" · "}
          <span className={`recipe-card__state recipe-card__state--${displayedNutritionState}`}>{stateLabel}</span>
        </p>
        {nutrition ? (
          <dl className="recipe-card__nutrition" aria-label={`${recipe.title} nutrition`}>
            <div><dt>Calories</dt><dd>{displayNumber(nutrition.caloriesKcal, 0)} kcal</dd></div>
            <div className="recipe-card__protein"><dt>Protein</dt><dd>{displayNumber(nutrition.proteinG, 1)} g</dd></div>
            <div className="recipe-card__carb"><dt>Carbs</dt><dd>{displayNumber(nutrition.carbohydrateG, 1)} g</dd></div>
            <div className="recipe-card__fat"><dt>Fat</dt><dd>{displayNumber(nutrition.fatG, 1)} g</dd></div>
          </dl>
        ) : <p className="muted">Nutrition estimate in progress.</p>}
      </div>
    </article>
  );
}
