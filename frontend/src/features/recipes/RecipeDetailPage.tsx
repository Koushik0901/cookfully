import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";

import { ArrowLeft, ChefHat, ExternalLink, Pencil } from "lucide-react";

import { Button, ConfirmDialog, ErrorRecovery, KitchenCompanion, Skeleton } from "../../components";
import { RecipeFallbackArt } from "../../components/cookfully/RecipeFallbackArt";
import { recipesApi } from "./api";
import { formatCookingText, servingLabel, sourceHost } from "./formatCooking";
import { NutritionPanel } from "./NutritionPanel";
import { RecipeNutritionSummary } from "./RecipeNutritionSummary";
import { RecipeOrganizationPanel } from "./RecipeOrganizationPanel";
import type { Job, RecipeDetail } from "./types";

const terminalStatuses = new Set(["succeeded", "failed", "cancelled", "superseded"]);

export function RecipeDetailPage() {
  const { recipeId } = useParams();
  const location = useLocation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const routeState = location.state as { jobId?: string; recipeSaved?: boolean; importUrl?: string } | null;
  const routeJobId = routeState?.jobId;
  const [savedRecipeId] = useState(() => routeState?.recipeSaved ? recipeId : undefined);
  const [jobId, setJobId] = useState<string | undefined>(routeJobId);
  const [mobilePanel, setMobilePanel] = useState<"ingredients" | "method">("ingredients");
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

  const shouldRecoverJob = Boolean(
    recipeId
    && detail.data
    && ["processing", "partial", "failed", "import_failed"].includes(detail.data.status)
    && !detail.data.activeJob
    && !jobId,
  );
  const recoveredJob = useQuery({
    queryKey: ["job-current", recipeId],
    queryFn: () => recipesApi.currentJob(recipeId!),
    enabled: shouldRecoverJob,
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

  const recalculate = useMutation({
    mutationFn: () => recipesApi.recalculate(recipeId!, false),
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
  useEffect(() => {
    const servings = Number(detail.data?.yieldQuantity ?? 1);
    if (servings > 0) setScale(servings);
  }, [detail.data?.yieldQuantity]);
  const scaleFactor = useMemo(() => {
    const sourceYield = Number(detail.data?.yieldQuantity ?? 1);
    return sourceYield > 0 ? scale / sourceYield : 1;
  }, [scale, detail.data?.yieldQuantity]);

  if (detail.isPending) return <Skeleton label="Loading recipe" lines={8} />;
  if (detail.isError || !detail.data) return <ErrorRecovery title="Recipe could not be loaded" onRetry={() => void detail.refetch()} />;
  const recipe = detail.data;
  const latestJob = job.data ?? recoveredJob.data ?? recipe.activeJob;
  const importFailed = recipe.status === "import_failed" || (recipe.status === "failed" && recipe.title === "Importing recipe");
  if (importFailed) {
    return (
      <main className="page-shell import-recovery-page">
        <section className="import-recovery" role="alert">
          <KitchenCompanion moment="error" size="md" />
          <div>
            <p className="eyebrow">Nothing was added to your library</p>
            <h1>This source could not be imported</h1>
            <p>{latestJob?.failureMessage ?? "Cookfully could not find a usable recipe in this source."}</p>
            {recipe.sourceUrl ? <a href={recipe.sourceUrl} target="_blank" rel="noopener noreferrer">Open the original source <ExternalLink aria-hidden="true" /></a> : null}
            <div className="actions"><Button asChild><Link to="/app/recipes">Back to recipes</Link></Button><Button variant="secondary" asChild><Link to="/app/recipes/new">Write it manually</Link></Button></div>
          </div>
        </section>
      </main>
    );
  }

  const ingredientReviewCount = recipe.ingredients.filter((item) => item.matchStatus === "ambiguous" || item.matchStatus === "unmatched").length;
  const actionError = [recalculate.error, archive.error, restore.error, permanentDelete.error].find((value) => value instanceof Error);
  const ingredientGroups = new Map<string | null, typeof recipe.ingredients>();
  for (const item of recipe.ingredients) {
    const key = item.sectionId ?? null;
    ingredientGroups.set(key, [...(ingredientGroups.get(key) ?? []), item]);
  }
  const instructionGroups = new Map<string | null, typeof recipe.instructions>();
  for (const item of recipe.instructions) {
    const key = item.sectionId ?? null;
    instructionGroups.set(key, [...(instructionGroups.get(key) ?? []), item]);
  }
  const orderedSections = (recipe.sections ?? []).filter((section) => (ingredientGroups.get(section.id)?.length ?? 0) > 0 || (instructionGroups.get(section.id)?.length ?? 0) > 0);

  return (
    <main className="page-shell recipe-detail-page">
      <div className="recipe-detail__topline">
        <Button asChild variant="ghost" size="sm"><Link to="/app/recipes"><ArrowLeft aria-hidden="true" />All recipes</Link></Button>
      </div>

      <section className="recipe-hero" aria-labelledby="recipe-title">
        <div className="recipe-hero__media">
          {recipe.imageUrl ? <img src={recipe.imageUrl} alt={recipe.title} /> : <RecipeFallbackArt title={recipe.title} />}
        </div>
        <div className="recipe-hero__copy">
          <p className="eyebrow">{recipe.status === "archived" ? "Archived recipe" : recipe.mealRoles?.[0] ?? "From your kitchen"}</p>
          <h1 id="recipe-title">{recipe.title}</h1>
          {recipe.description ? <p className="lede">{recipe.description}</p> : null}
          <div className="recipe-hero__facts">
            <span><strong>{servingLabel(recipe.yieldQuantity, recipe.yieldUnit)}</strong>{recipe.sourceUrl ? " · source yield" : ""}</span>
            <span><strong>{recipe.ingredients.length}</strong> ingredients</span>
            <span><strong>{recipe.instructions.length}</strong> steps</span>
            {recipe.sourceUrl && sourceHost(recipe.sourceUrl) ? <a className="recipe-source" href={recipe.sourceUrl} target="_blank" rel="noopener noreferrer">From {sourceHost(recipe.sourceUrl)} <ExternalLink aria-hidden="true" /></a> : null}
          </div>
          <RecipeNutritionSummary nutrition={recipe.nutrition} nutritionState={recipe.nutritionState} job={latestJob} editTo={`/app/recipes/${recipe.id}/edit`} />
          <div className="recipe-hero__actions">
            {recipe.instructions.length > 0 ? <Button asChild size="lg"><Link to={`/app/recipes/${recipe.id}/cook`}><ChefHat aria-hidden="true" />Start cooking</Link></Button> : null}
            <Button asChild variant="secondary"><Link to={`/app/recipes/${recipe.id}/edit`} aria-label="Edit recipe"><Pencil aria-hidden="true" />Edit recipe</Link></Button>
          </div>
          <label className="portion-scale__label">
            <span>Scale to</span>
            <input className="input portion-scale__input" type="number" min={0.25} step={0.5} value={scale} onChange={(event) => { const value = parseFloat(event.target.value); if (value > 0) setScale(value); }} />
            <span>{recipe.yieldUnit}</span>
          </label>
        </div>
      </section>

      {savedRecipeId === recipeId ? <section className="recipe-saved-moment" role="status"><KitchenCompanion moment="success" size="sm" /><div><strong>Recipe saved</strong><p>{recipe.title} is ready in your kitchen.</p></div></section> : null}
      {actionError instanceof Error ? <p className="error-text" role="alert">{actionError.message}</p> : null}

      <RecipeOrganizationPanel recipe={recipe} onSaved={(value) => queryClient.setQueryData(["recipe", recipeId], value)} />

      <nav className="recipe-reading-tabs" aria-label="Recipe sections">
        <button type="button" aria-pressed={mobilePanel === "ingredients"} onClick={() => setMobilePanel("ingredients")}>Ingredients <span>{recipe.ingredients.length}</span></button>
        <button type="button" aria-pressed={mobilePanel === "method"} onClick={() => setMobilePanel("method")}>Method <span>{recipe.instructions.length}</span></button>
      </nav>

      <section className="recipe-reading-grid">
        <section className={`recipe-reading-panel recipe-reading-panel--ingredients${mobilePanel === "ingredients" ? " is-mobile-active" : ""}`} aria-labelledby="ingredients-heading">
          <div className="section-heading"><h2 id="ingredients-heading">Ingredients</h2><span>{recipe.ingredients.length} items</span></div>
          {recipe.ingredients.length ? (
            <ul className="ingredient-list">
              {orderedSections.map((section) => (
                <li key={section.id} className="ingredient-section" aria-label={`${section.title} ingredients`}>
                  <h3>{section.title}</h3>
                  <ul>
                    {(ingredientGroups.get(section.id) ?? []).map((item) => {
                      const scaledMin = item.quantityMin != null ? (Number(item.quantityMin) * scaleFactor).toFixed(2).replace(/\.?0+$/, "") : null;
                      const scaledMax = item.quantityMax != null ? (Number(item.quantityMax) * scaleFactor).toFixed(2).replace(/\.?0+$/, "") : null;
                      const friendlyIngredient = scaleFactor !== 1 && scaledMin
                        ? [scaledMin, scaledMax && scaledMax !== scaledMin ? `–${scaledMax}` : null, item.unit, item.food, item.preparation].filter(Boolean).join(" ")
                        : formatCookingText(item.originalText);
                      return <li key={item.id}><span className="ingredient-text">{friendlyIngredient}</span></li>;
                    })}
                  </ul>
                </li>
              ))}
              {(ingredientGroups.get(null) ?? []).map((item) => {
                const scaledMin = item.quantityMin != null ? (Number(item.quantityMin) * scaleFactor).toFixed(2).replace(/\.?0+$/, "") : null;
                const scaledMax = item.quantityMax != null ? (Number(item.quantityMax) * scaleFactor).toFixed(2).replace(/\.?0+$/, "") : null;
                const friendlyIngredient = scaleFactor !== 1 && scaledMin
                  ? [scaledMin, scaledMax && scaledMax !== scaledMin ? `–${scaledMax}` : null, item.unit, item.food, item.preparation].filter(Boolean).join(" ")
                  : formatCookingText(item.originalText);
                return <li key={item.id}><span className="ingredient-text">{friendlyIngredient}</span></li>;
              })}
            </ul>
          ) : <p className="muted">No ingredients were provided.</p>}
        </section>

        <section className={`recipe-reading-panel recipe-reading-panel--method${mobilePanel === "method" ? " is-mobile-active" : ""}`} aria-labelledby="method-heading">
          <div className="section-heading"><h2 id="method-heading">Method</h2><span>{recipe.instructions.length} steps</span></div>
          {recipe.instructions.length ? (
            <ol className="instruction-list">
              {orderedSections.map((section) => (
                <li key={section.id} className="instruction-section" aria-label={`${section.title} instructions`}>
                  <h3>{section.title}</h3>
                  <ol>
                    {(instructionGroups.get(section.id) ?? []).map((step) => <li key={`${step.position}-${step.text}`}>{step.text}</li>)}
                  </ol>
                </li>
              ))}
              {(instructionGroups.get(null) ?? []).map((step) => <li key={`${step.position}-${step.text}`}>{step.text}</li>)}
            </ol>
          ) : <p className="muted">No instructions were provided.</p>}
        </section>
      </section>

      <details className="recipe-nutrition-drawer" id="nutrition-details">
        <summary><span><strong>Nutrition details and evidence</strong><small>Micronutrients, sources, assumptions, and processing status</small></span></summary>
        {ingredientReviewCount ? (
          <section className="ingredient-evidence--inline" style={{ borderTop: 0 }}>
            <div><strong>{ingredientReviewCount} nutrition match{ingredientReviewCount === 1 ? "" : "es"} could be improved</strong><small style={{ display: "block", color: "var(--color-on-surface-variant)", marginTop: "0.15rem" }}>The recipe is still usable. Review these only if you want a more complete estimate.</small></div>
            <div className="ingredient-evidence__list">{recipe.ingredients.filter((item) => item.matchStatus === "ambiguous" || item.matchStatus === "unmatched").map((item) => <article key={item.id}><strong>{formatCookingText(item.originalText)}</strong><small>{item.matchStatus}</small></article>)}</div>
            <Button variant="secondary" asChild><Link to={`/app/recipes/${recipe.id}/edit#ingredient-matches`}>Review matches in editor</Link></Button>
          </section>
        ) : null}
        <NutritionPanel nutrition={recipe.nutrition} nutritionState={recipe.nutritionState} job={latestJob} onRecalculate={async () => { await recalculate.mutateAsync(); }} />
      </details>

      <details className="danger-zone"><summary><span><strong>More recipe options</strong><small>Archive, restore, or permanently remove this recipe</small></span></summary><div className="danger-zone__body">
        {recipe.status === "archived" ? <><p>Restore this recipe for active planning, or permanently remove its recipe content.</p><div className="actions"><Button onClick={() => restore.mutate()}>Restore recipe</Button><ConfirmDialog trigger={<Button variant="destructive">Permanently delete recipe</Button>} title="Permanently delete this recipe?" description="Recipe content and media will be erased after the bounded recovery window. Historical plan and grocery records remain detached so their past facts stay accurate." confirmLabel="Delete permanently" onConfirm={() => permanentDelete.mutate()} /></div></> : <><p>Archiving hides the recipe from active planning without deleting it.</p><ConfirmDialog trigger={<Button variant="secondary">Archive recipe</Button>} title="Archive this recipe?" description="You can restore it later from the archived recipe view." confirmLabel="Archive" onConfirm={() => archive.mutate()} /></>}
      </div></details>
    </main>
  );
}
