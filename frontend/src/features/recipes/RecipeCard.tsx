import { Link } from "react-router-dom";

import { Button, PollingStatusBadge } from "../../components";
import type { Recipe } from "./types";

export function RecipeCard({
  recipe,
  onArchive,
  onRestore,
}: {
  recipe: Recipe;
  onArchive: (id: string, version: number) => void;
  onRestore: (id: string, version: number) => void;
}) {
  const nutrition = recipe.nutrition;
  return (
    <article className="recipe-card">
      <Link className="recipe-card__media" to={`/app/recipes/${recipe.id}`} aria-label={`Open ${recipe.title}`}>
        {recipe.imageUrl ? <img src={recipe.imageUrl} alt="" /> : <span aria-hidden="true">V&amp;V</span>}
        <span className="recipe-card__state">{recipe.nutritionState.replace("_", " ")}</span>
      </Link>
      <div className="recipe-card__body">
        <div className="recipe-card__heading">
          <h2><Link to={`/app/recipes/${recipe.id}`}>{recipe.title}</Link></h2>
          {recipe.status === "processing" ? <PollingStatusBadge status="running" /> : null}
        </div>
        <p className="recipe-card__yield data-value">{recipe.yieldQuantity} {recipe.yieldUnit}</p>
        {nutrition ? (
          <dl className="macro-row" aria-label={`${recipe.title} nutrition`}>
            <div className="macro macro--calories"><dt>Calories</dt><dd>{nutrition.caloriesKcal ?? "—"} kcal</dd></div>
            <div className="macro macro--protein"><dt>Protein</dt><dd>{nutrition.proteinG ?? "—"} g protein</dd></div>
            <div className="macro macro--carbs"><dt>Carbs</dt><dd>{nutrition.carbohydrateG ?? "—"} g</dd></div>
            <div className="macro macro--fat"><dt>Fat</dt><dd>{nutrition.fatG ?? "—"} g</dd></div>
          </dl>
        ) : <p className="muted">Nutrition {recipe.nutritionState.replace("_", " ")}.</p>}
        <div className="actions">
          {recipe.status === "archived" ? (
            <Button onClick={() => onRestore(recipe.id, recipe.version)} aria-label={`Restore ${recipe.title}`}>Restore</Button>
          ) : (
            <Button className="button--secondary" onClick={() => onArchive(recipe.id, recipe.version)} aria-label={`Archive ${recipe.title}`}>Archive</Button>
          )}
        </div>
      </div>
    </article>
  );
}

