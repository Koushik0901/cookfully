import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type CSSProperties, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Archive, Check, Heart, MoreVertical, Pencil, RotateCcw, Trash2 } from "lucide-react";

import { ConfirmDialog, PollingStatusBadge, RecipeMedia } from "../../components";
import { nutritionPresentation } from "../../components/cookfully/nutritionState";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "../../components/ui/dropdown-menu";
import { Checkbox } from "../../components/ui/checkbox";
import { recipesApi } from "./api";
import { servingLabel } from "./formatCooking";
import { RecipeMetadata } from "./RecipeMetadata";
import type { Recipe } from "./types";

const EMPTY_COLLECTIONS: NonNullable<Recipe["collections"]> = [];

export function RecipeCard({
  recipe,
  onArchive,
  onRestore,
  onDelete,
  actionPending = false,
  selectionMode = false,
  selected = false,
  onSelectedChange,
}: {
  recipe: Recipe;
  onArchive: (id: string, version: number) => void;
  onRestore: (id: string, version: number) => void;
  onDelete: (id: string, version: number) => void;
  actionPending?: boolean;
  selectionMode?: boolean;
  selected?: boolean;
  onSelectedChange?: (selected: boolean) => void;
}) {
  const queryClient = useQueryClient();
  const recipeCollections = recipe.collections ?? EMPTY_COLLECTIONS;
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [confirmArchive, setConfirmArchive] = useState(false);
  const [favorite, setFavorite] = useState(Boolean(recipe.favorite));
  const [membership, setMembership] = useState(recipeCollections.map((item) => item.id));
  useEffect(() => {
    setFavorite(Boolean(recipe.favorite));
    setMembership(recipeCollections.map((item) => item.id));
  }, [recipe.favorite, recipeCollections]);
  const nutrition = recipe.nutrition;
  const displayedNutritionState = ["stale", "pending", "failed"].includes(recipe.nutritionState)
    ? recipe.nutritionState
    : nutrition?.status === "manual" ? "manual" : recipe.nutritionState;
  const statePresentation = nutritionPresentation(displayedNutritionState, nutrition?.status);
  const collections = useQuery({ queryKey: ["recipe-collections"], queryFn: recipesApi.collections, retry: 1 });
  const organize = useMutation({
    mutationFn: (value: { favorite: boolean; collectionIds: string[] }) =>
      recipesApi.organize(recipe.id, recipe.version, {
        favorite: value.favorite,
        collectionIds: value.collectionIds,
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
    const previous = membership;
    setMembership(next);
    organize.mutate({ favorite, collectionIds: next }, { onError: () => setMembership(previous) });
  };
  const toggleFavorite = () => {
    const next = !favorite;
    setFavorite(next);
    organize.mutate({ favorite: next, collectionIds: membership }, { onError: () => setFavorite(!next) });
  };
  return (
    <article className={`recipe-card${selectionMode ? " recipe-card--selection-mode" : ""}`}>
      {selectionMode ? <Checkbox className="recipe-card__selection" checked={selected} aria-label={`Select ${recipe.title}`} onCheckedChange={(checked) => onSelectedChange?.(checked === true)} /> : null}
      <Link className="recipe-card__primary" to={`/app/recipes/${recipe.id}`} aria-label={recipe.title} viewTransition>
        <div className="recipe-card__media" style={{ viewTransitionName: `recipe-media-${recipe.id}` } as CSSProperties}>
          <RecipeMedia recipe={recipe} />
        </div>
        <div className="recipe-card__body">
          <div className="recipe-card__heading">
            <h2 style={{ viewTransitionName: `recipe-title-${recipe.id}` } as CSSProperties}>{recipe.title}</h2>
            {recipe.status === "processing" ? <PollingStatusBadge status="running" /> : null}
          </div>
          <p className="recipe-card__yield data-value">
            Makes {servingLabel(recipe.yieldQuantity, recipe.yieldUnit)}
            {" · "}
             <span className={`recipe-card__state recipe-card__state--${statePresentation.key}`} title={statePresentation.description}>{statePresentation.label}</span>
          </p>
          {recipeCollections.length ? <div className="recipe-card__context"><span className="recipe-card__collection">{recipeCollections[0].name}</span>{recipeCollections.length > 1 ? <span className="recipe-card__collection">+{recipeCollections.length - 1}</span> : null}</div> : null}
          <RecipeMetadata recipe={recipe} />
        </div>
      </Link>
      <button type="button" className={`recipe-card__favorite-toggle${favorite ? " is-favorite" : ""}`} aria-label={`${favorite ? "Remove" : "Add"} ${recipe.title} ${favorite ? "from" : "to"} favorites`} aria-pressed={favorite} onClick={toggleFavorite} disabled={organize.isPending}>
        <Heart aria-hidden="true" />
      </button>
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
           <DropdownMenuItem disabled={actionPending} onSelect={() => onRestore(recipe.id, recipe.version)}><RotateCcw aria-hidden="true" />Restore recipe</DropdownMenuItem>
          ) : (
             <DropdownMenuItem disabled={actionPending} onSelect={(event) => { event.preventDefault(); setConfirmArchive(true); }}><Archive aria-hidden="true" />Archive recipe</DropdownMenuItem>
          )}
           <DropdownMenuItem disabled={actionPending} variant="destructive" onSelect={() => setConfirmDelete(true)}><Trash2 aria-hidden="true" />Delete recipe</DropdownMenuItem>
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
      <ConfirmDialog
        open={confirmArchive}
        onOpenChange={setConfirmArchive}
        title={`Archive ${recipe.title}?`}
        description="This hides the recipe from active planning but keeps it safe in Archived recipes for later restoration."
        confirmLabel="Archive recipe"
        onConfirm={() => { setConfirmArchive(false); onArchive(recipe.id, recipe.version); }}
      />
      {organize.error instanceof Error ? <p className="error-text recipe-card__feedback" role="alert">{organize.error.message}</p> : null}
    </article>
  );
}
