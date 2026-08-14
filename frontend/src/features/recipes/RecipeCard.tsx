import { Link } from "react-router-dom";
import { Heart } from "lucide-react";

import { Button, PollingStatusBadge } from "../../components";
import { RecipeFallbackArt } from "../../components/cookfully/RecipeFallbackArt";
import { servingLabel } from "./formatCooking";
import type { Recipe } from "./types";

export function RecipeCard({
  recipe,
  onArchive,
  onRestore,
  featured = false,
}: {
  recipe: Recipe;
  onArchive: (id: string, version: number) => void;
  onRestore: (id: string, version: number) => void;
  featured?: boolean;
}) {
  const nutrition = recipe.nutrition;
  const displayedNutritionState = ["stale", "pending", "failed"].includes(recipe.nutritionState)
    ? recipe.nutritionState
    : nutrition?.status === "manual" ? "manual" : recipe.nutritionState;
  const displayNumber = (value: string | null, maximumFractionDigits: number) =>
    value == null
      ? "—"
      : new Intl.NumberFormat(undefined, { maximumFractionDigits }).format(Number(value));
  return (
    <article className={`recipe-card${featured ? " recipe-card--featured" : ""}`}>
      <Link className="recipe-card__media" to={`/app/recipes/${recipe.id}`} aria-label={`Open ${recipe.title}`}>
        {recipe.imageUrl ? <img src={recipe.imageUrl} alt="" loading="lazy" decoding="async" /> : <RecipeFallbackArt title={recipe.title} />}
        {recipe.favorite ? <span className="recipe-card__favorite" aria-label="Favorite recipe"><Heart aria-hidden="true" /></span> : null}
        <span className="recipe-card__state">{displayedNutritionState.replace("_", " ")}</span>
      </Link>
      <div className="recipe-card__body">
        <div className="recipe-card__heading">
          <h2><Link to={`/app/recipes/${recipe.id}`}>{recipe.title}</Link></h2>
          {recipe.status === "processing" ? <PollingStatusBadge status="running" /> : null}
        </div>
        <p className="recipe-card__yield data-value">Makes {servingLabel(recipe.yieldQuantity, recipe.yieldUnit)}</p>
        {nutrition ? (
          <dl className="recipe-card__nutrition" aria-label={`${recipe.title} nutrition`}>
            <div><dt>Calories</dt><dd>{displayNumber(nutrition.caloriesKcal, 0)} kcal</dd></div>
            <div className="recipe-card__protein"><dt>Protein</dt><dd>{displayNumber(nutrition.proteinG, 1)} g</dd></div>
          </dl>
        ) : <p className="muted">Nutrition {recipe.nutritionState.replace("_", " ")}.</p>}
        <div className="actions">
          {recipe.status === "archived" ? (
            <Button onClick={() => onRestore(recipe.id, recipe.version)} aria-label={`Restore ${recipe.title}`}>Restore</Button>
          ) : (
            <Button variant="secondary" onClick={() => onArchive(recipe.id, recipe.version)} aria-label={`Archive ${recipe.title}`}>Archive</Button>
          )}
        </div>
      </div>
    </article>
  );
}
