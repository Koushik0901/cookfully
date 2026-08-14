import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";

import { Button, ConfirmDialog, ErrorRecovery, KitchenCompanion, Skeleton } from "../../components";
import { ArrowLeft, ChefHat, Pencil } from "lucide-react";
import { RecipeFallbackArt } from "../../components/cookfully/RecipeFallbackArt";
import { FoodPicker } from "../foods/FoodPicker";
import { recipesApi } from "./api";
import { formatCookingText, servingLabel } from "./formatCooking";
import { NutritionPanel } from "./NutritionPanel";
import { RecipeOrganizationPanel } from "./RecipeOrganizationPanel";
import type { Job, NutritionCorrectionWrite, RecipeDetail } from "./types";

const terminalStatuses = new Set(["succeeded", "failed", "cancelled", "superseded"]);

export function RecipeDetailPage() {
  const { recipeId } = useParams();
  const location = useLocation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const routeState = location.state as { jobId?: string; recipeSaved?: boolean } | null;
  const routeJobId = routeState?.jobId;
  const [savedRecipeId] = useState(() => routeState?.recipeSaved ? recipeId : undefined);
  const [jobId, setJobId] = useState<string | undefined>(routeJobId);
  const detail = useQuery({
    queryKey: ["recipe", recipeId],
    queryFn: () => recipesApi.get(recipeId!),
    enabled: Boolean(recipeId),
    retry: 1,
    staleTime: 0,
  });

  useEffect(() => {
    if (detail.data?.activeJob?.id) setJobId(detail.data.activeJob.id);
  }, [detail.data?.activeJob?.id]);

  useEffect(() => {
    if (!savedRecipeId) return;
    navigate(location.pathname, { replace: true, state: routeJobId ? { jobId: routeJobId } : null });
  }, [location.pathname, navigate, routeJobId, savedRecipeId]);

  const recoveredJob = useQuery({
    queryKey: ["job-current", recipeId],
    queryFn: () => recipesApi.currentJob(recipeId!),
    enabled: Boolean(recipeId && detail.data?.status === "processing" && !detail.data?.activeJob && !jobId),
    retry: false,
  });
  useEffect(() => {
    if (recoveredJob.data?.id) setJobId(recoveredJob.data.id);
  }, [recoveredJob.data?.id]);

  const detailJob = detail.data?.activeJob;
  const initialJob = detailJob?.id === jobId ? detailJob : undefined;
  const job = useQuery({
    queryKey: ["recipe-job", jobId],
    queryFn: () => recipesApi.job(jobId!),
    enabled: Boolean(jobId),
    initialData: initialJob,
    refetchOnMount: false,
    refetchIntervalInBackground: true,
    refetchInterval: (query) => {
      const value = query.state.data as Job | undefined;
      if (!value || terminalStatuses.has(value.status)) return false;
      return document.visibilityState === "visible" ? 2_000 : 15_000;
    },
  });

  useEffect(() => {
    if (!job.data || !terminalStatuses.has(job.data.status)) return;
    void detail.refetch();
  }, [job.data?.status]); // eslint-disable-line react-hooks/exhaustive-deps

  function updateNutrition(nutrition: RecipeDetail["nutrition"]) {
    queryClient.setQueryData<RecipeDetail>(["recipe", recipeId], (current) => current ? {
      ...current,
      nutrition,
    } : current);
  }

  const correction = useMutation({
    mutationFn: (value: NutritionCorrectionWrite) => recipesApi.correct(recipeId!, value),
    onSuccess: updateNutrition,
  });
  const reset = useMutation({
    mutationFn: (correctionId: string) => recipesApi.resetCorrection(recipeId!, correctionId),
    onSuccess: updateNutrition,
  });
  const recalculate = useMutation({
    mutationFn: (resetCorrections: boolean) => recipesApi.recalculate(recipeId!, resetCorrections),
    onSuccess: (accepted) => {
      setJobId(accepted.jobId);
      queryClient.setQueryData<RecipeDetail>(["recipe", recipeId], (current) => current ? { ...current, status: "processing", nutritionState: "pending" } : current);
    },
  });
  const archive = useMutation({
    mutationFn: () => recipesApi.archive(recipeId!, detail.data!.version),
    onSuccess: async () => { await detail.refetch(); void queryClient.invalidateQueries({ queryKey: ["recipes"] }); },
  });
  const restore = useMutation({
    mutationFn: () => recipesApi.restore(recipeId!, detail.data!.version),
    onSuccess: (value) => { queryClient.setQueryData(["recipe", recipeId], value); void queryClient.invalidateQueries({ queryKey: ["recipes"] }); },
  });
  const permanentDelete = useMutation({
    mutationFn: () => recipesApi.permanentDelete(recipeId!, detail.data!.version),
    onSuccess: () => { void queryClient.invalidateQueries({ queryKey: ["recipes"] }); navigate("/app/recipes"); },
  });

  const [scale, setScale] = useState(1);
  const scaleFactor = useMemo(() => {
    const y = Number(detail.data?.yieldQuantity ?? 1);
    return y > 0 ? scale / y : 1;
  }, [scale, detail.data?.yieldQuantity]);

  if (detail.isPending) return <Skeleton label="Loading recipe" lines={8} />;
  if (detail.isError || !detail.data) return <ErrorRecovery title="Recipe could not be loaded" onRetry={() => void detail.refetch()} />;
  const recipe = detail.data;
  const ingredientReviewCount = recipe.ingredients.filter((item) => item.matchStatus !== "matched" && item.matchStatus !== "manual").length;
  const actionError = [correction.error, reset.error, recalculate.error, archive.error, restore.error, permanentDelete.error].find((value) => value instanceof Error);

  return (
    <main className="page-shell recipe-detail-page">
      <section className="recipe-hero" aria-labelledby="recipe-title">
        <div className="recipe-hero__media">
          {recipe.imageUrl ? <img src={recipe.imageUrl} alt={recipe.title} /> : <RecipeFallbackArt title={recipe.title} />}
        </div>
        <div className="recipe-hero__copy">
          <Button asChild variant="ghost" size="sm" className="recipe-hero__back"><Link to="/app/recipes"><ArrowLeft aria-hidden="true" />Recipe library</Link></Button>
          <p className="eyebrow">{recipe.status === "archived" ? "Archived recipe" : recipe.mealRoles?.[0] ?? "From your kitchen"}</p>
          <h1 id="recipe-title">{recipe.title}</h1>
          {recipe.description ? <p className="lede">{recipe.description}</p> : null}
          <div className="recipe-hero__facts">
            <span>Makes <strong>{servingLabel(recipe.yieldQuantity, recipe.yieldUnit)}</strong></span>
            <span><strong>{recipe.ingredients.length}</strong> ingredients</span>
            <span><strong>{recipe.instructions.length}</strong> steps</span>
          </div>
          <div className="recipe-hero__actions">
            {recipe.instructions.length > 0 ? <Button asChild size="lg"><Link to={`/app/recipes/${recipe.id}/cook`}><ChefHat aria-hidden="true" />Start cooking</Link></Button> : null}
            <Button asChild variant="secondary"><Link to={`/app/recipes/${recipe.id}/edit`} aria-label="Edit recipe"><Pencil aria-hidden="true" />Edit</Link></Button>
          </div>
          {Number(recipe.yieldQuantity) > 0 ? (
            <div className="portion-scale">
              <label className="portion-scale__label">
                <span>Scale ingredients to</span>
                <input
                  className="input portion-scale__input"
                  type="number"
                  min={0.25}
                  step={0.5}
                  value={scale}
                  onChange={(event) => {
                    const value = parseFloat(event.target.value);
                    if (value > 0) setScale(value);
                  }}
                />
                <span>servings</span>
              </label>
            </div>
          ) : null}
        </div>
      </section>

      {savedRecipeId === recipeId ? (
        <section className="recipe-saved-moment" role="status">
          <KitchenCompanion moment="success" size="sm" />
          <div><strong>Recipe saved</strong><p>{recipe.title} is ready in your kitchen.</p></div>
        </section>
      ) : null}

      {actionError instanceof Error ? <p className="error-text" role="alert">{actionError.message}</p> : null}
      <RecipeOrganizationPanel recipe={recipe} onSaved={(value) => queryClient.setQueryData(["recipe", recipeId], value)} />
      <section className="recipe-detail-grid">
        <div className="recipe-content">
           <section className="ingredient-section"><div className="section-heading"><h2>Ingredients</h2><span>{recipe.ingredients.length} item{recipe.ingredients.length === 1 ? "" : "s"}</span></div><ul className="ingredient-list">{recipe.ingredients.map((item) => {
           const foodName = item.food || item.originalText || "";
           const scaledMin = item.quantityMin != null ? (Number(item.quantityMin) * scaleFactor).toFixed(2).replace(/\.?0+$/, "") : null;
           const scaledMax = item.quantityMax != null ? (Number(item.quantityMax) * scaleFactor).toFixed(2).replace(/\.?0+$/, "") : null;
           const friendlyIngredient = scaleFactor !== 1 && scaledMin
             ? [scaledMin, scaledMax && scaledMax !== scaledMin ? `\u2013${scaledMax}` : null, item.unit, item.food, item.preparation].filter(Boolean).join(" ")
             : formatCookingText(item.originalText);
           const needsReview = item.matchStatus !== "matched" && item.matchStatus !== "manual";
           return (
             <li key={item.id}>
               <span className="ingredient-text">{friendlyIngredient}</span>
               {needsReview ? <span className="ingredient-review-badge">Needs review</span> : null}
               {needsReview && foodName.trim() && recipeId ? (
                 <FoodPicker
                   recipeId={recipeId}
                   ingredientId={item.id}
                   ingredientName={foodName}
                   trigger={<button className="text-link ingredient-match-btn">Review food match</button>}
                   onSelected={() => detail.refetch()}
                 />
               ) : null}
             </li>
           );
           })}</ul>
           <details className="ingredient-evidence"><summary><span><strong>Ingredient matching and assumptions</strong><small>{ingredientReviewCount ? `${ingredientReviewCount} ingredient${ingredientReviewCount === 1 ? "" : "s"} need review` : "All ingredients are ready for nutrition planning"}</small></span></summary><div className="ingredient-evidence__list">{recipe.ingredients.map((item) => {
             const scaledMin = item.quantityMin != null ? (Number(item.quantityMin) * scaleFactor).toFixed(2).replace(/\.?0+$/, "") : null;
             const scaledMax = item.quantityMax != null ? (Number(item.quantityMax) * scaleFactor).toFixed(2).replace(/\.?0+$/, "") : null;
             const scaledDetail = [scaledMin, scaledMax && scaledMax !== scaledMin ? `\u2013${scaledMax}` : null, item.unit, item.preparation].filter(Boolean).join(" ") || "Quantity not parsed";
             return <article key={item.id}><strong>{formatCookingText(item.originalText)}</strong><small>{scaledDetail} · {item.parseStatus}{item.matchStatus ? ` / ${item.matchStatus.replace("_", " ")}` : ""}</small>{item.assumptions?.length ? <div className="ingredient-assumptions">{item.assumptions.map((assumption) => <span className="assumption-chip" key={assumption}>{formatCookingText(assumption)}</span>)}</div> : null}</article>;
           })}</div></details>
          </section>
          <section><h2>Instructions</h2>{recipe.instructions.length ? <ol className="instruction-list">{recipe.instructions.map((step, index) => <li key={`${index}-${step}`}>{step}</li>)}</ol> : <p className="muted">No instructions were provided.</p>}</section>
          {recipe.sourceUrl ? <p>Original source: <a href={recipe.sourceUrl} rel="noreferrer">{new URL(recipe.sourceUrl).hostname}</a></p> : null}
        </div>
        <NutritionPanel nutrition={recipe.nutrition} nutritionState={recipe.nutritionState} job={job.data ?? recipe.activeJob} servingsScale={scale} onCorrect={async (value) => { await correction.mutateAsync(value); }} onResetCorrection={async (id) => { await reset.mutateAsync(id); }} onRecalculate={async (resetCorrections = false) => { await recalculate.mutateAsync(resetCorrections); }} />
      </section>

      <details className="danger-zone" open><summary><span><strong>Recipe management</strong><small>Archive, restore, or permanently remove this recipe</small></span></summary><div className="danger-zone__body" aria-labelledby="lifecycle-heading"><h2 id="lifecycle-heading">Recipe management</h2>
        {recipe.status === "archived" ? <><p>Restore this recipe for active planning, or permanently remove its recipe content.</p><div className="actions"><Button onClick={() => restore.mutate()}>Restore recipe</Button><ConfirmDialog trigger={<Button variant="destructive">Permanently delete recipe</Button>} title="Permanently delete this recipe?" description="Recipe content and media will be erased after the bounded recovery window. Historical plan and grocery records remain detached so their past facts stay accurate." confirmLabel="Delete permanently" onConfirm={() => permanentDelete.mutate()} /></div></> : <><p>Archiving hides the recipe from active planning without deleting it.</p><ConfirmDialog trigger={<Button variant="secondary">Archive recipe</Button>} title="Archive this recipe?" description="You can restore it later from the archived recipe view." confirmLabel="Archive" onConfirm={() => archive.mutate()} /></>}
      </div></details>
    </main>
  );
}
