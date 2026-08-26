import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type CSSProperties, useEffect, useMemo, useState } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";

import { ArrowLeft, ChefHat, ExternalLink, Pencil } from "lucide-react";

import { Button, ConfirmDialog, ErrorRecovery, KitchenCompanion, PageState, RecipeMedia, SectionHeading, Skeleton } from "../../components";
import { nutritionPresentation } from "../../components/cookfully/nutritionState";
import { recipesApi } from "./api";
import { formatCookingText, servingLabel, sourceHost } from "./formatCooking";
import { NutritionPanel } from "./NutritionPanel";
import { RecipeNutritionSummary } from "./RecipeNutritionSummary";
import { recipeTimeLabel } from "./recipeMetadataUtils";
import { RecipeOrganizationPanel } from "./RecipeOrganizationPanel";
import { RecipeProcessingBanner } from "./RecipeProcessingBanner";
import type { Job, RecipeDetail } from "./types";

const terminalStatuses = new Set(["succeeded", "failed", "cancelled", "superseded"]);
const originLabel = { manual: "Written in Cookfully", web_import: "Imported from the web", cookbook_import: "Imported from a cookbook" } as const;

export function RecipeDetailPage() {
  const { recipeId } = useParams();
  const location = useLocation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const routeState = location.state as { jobId?: string; recipeSaved?: boolean; importUrl?: string; coverStatus?: "attached" | "not_selected" | "failed" } | null;
  const routeJobId = routeState?.jobId;
  const coverStatus = routeState?.coverStatus;
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
    navigate(location.pathname, { replace: true, state: routeJobId || coverStatus ? { jobId: routeJobId, coverStatus } : null });
  }, [coverStatus, location.pathname, navigate, routeJobId, savedRecipeId]);

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
    onMutate: async () => {
      await queryClient.cancelQueries({ queryKey: ["recipe", recipeId] });
      const previous = queryClient.getQueryData<RecipeDetail>(["recipe", recipeId]);
      if (previous) queryClient.setQueryData<RecipeDetail>(["recipe", recipeId], { ...previous, status: "archived", archivedFromStatus: previous.status === "ready" || previous.status === "partial" || previous.status === "draft" || previous.status === "failed" ? previous.status : null });
      return { previous };
    },
    onError: (_error, _variables, context) => { if (context?.previous) queryClient.setQueryData(["recipe", recipeId], context.previous); },
    onSuccess: async () => { await detail.refetch(); void queryClient.invalidateQueries({ queryKey: ["recipes"] }); },
  });
  const restore = useMutation({
    mutationFn: () => recipesApi.restore(recipeId!, detail.data!.version),
    onMutate: async () => {
      await queryClient.cancelQueries({ queryKey: ["recipe", recipeId] });
      const previous = queryClient.getQueryData<RecipeDetail>(["recipe", recipeId]);
      if (previous?.archivedFromStatus) queryClient.setQueryData<RecipeDetail>(["recipe", recipeId], { ...previous, status: previous.archivedFromStatus, archivedFromStatus: null });
      return { previous };
    },
    onError: (_error, _variables, context) => { if (context?.previous) queryClient.setQueryData(["recipe", recipeId], context.previous); },
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

  if (detail.isPending) return <PageState><Skeleton label="Loading recipe" lines={8} /></PageState>;
  if (detail.isError || !detail.data) return <PageState><ErrorRecovery title="Recipe could not be loaded" onRetry={() => void detail.refetch()} /></PageState>;
  const recipe = detail.data;
  const nutritionStatePresentation = nutritionPresentation(recipe.nutritionState, recipe.nutrition?.status);
  const latestJob = recipe.activeJob && recipe.activeJob.id !== jobId
    ? recipe.activeJob
    : job.data ?? recoveredJob.data ?? recipe.activeJob;
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

  const recipeCollections = recipe.collections ?? [];
  const ingredientReviewCount = recipe.ingredients.filter((item) => item.matchStatus === "ambiguous" || item.matchStatus === "unmatched" || item.resolutionKind === "provisional").length;
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
        <div className="recipe-hero__media" style={{ viewTransitionName: `recipe-media-${recipe.id}` } as CSSProperties}>
          <RecipeMedia recipe={recipe} alt={recipe.title} loading="eager" />
        </div>
        <div className="recipe-hero__copy">
          <p className="eyebrow">{recipe.status === "archived" ? "Archived recipe" : recipe.mealRoles?.[0] ?? "From your kitchen"}</p>
          <h1 id="recipe-title" style={{ viewTransitionName: `recipe-title-${recipe.id}` } as CSSProperties}>{recipe.title}</h1>
          {recipe.description ? <p className="lede">{recipe.description}</p> : null}
           <div className="recipe-hero__facts">
            <span><strong>{servingLabel(recipe.yieldQuantity, recipe.yieldUnit)}</strong>{recipe.sourceUrl ? " · source yield" : ""}</span>
            <span><strong>{recipeTimeLabel(recipe)}</strong> estimated time</span>
            <span><strong>{recipe.ingredients.length}</strong> ingredients</span>
            <span><strong>{recipe.instructions.length}</strong> steps</span>
            {recipe.sourceUrl && sourceHost(recipe.sourceUrl) ? <a className="recipe-source" href={recipe.sourceUrl} target="_blank" rel="noopener noreferrer">From {sourceHost(recipe.sourceUrl)} <ExternalLink aria-hidden="true" /></a> : null}
           </div>
           <p className="recipe-provenance"><strong>{originLabel[recipe.originKind] ?? "Recipe"}</strong>{recipe.sourceUrl ? <> · <a href={recipe.sourceUrl} target="_blank" rel="noopener noreferrer">View original source</a></> : <> · No external source</>}</p>
           {recipeCollections.length ? <div className="recipe-detail__collections" aria-label="Recipe collections">{recipeCollections.map((collection) => <span key={collection.id}>{collection.name}</span>)}</div> : null}
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

       {savedRecipeId === recipeId ? <section className="recipe-saved-moment" role="status"><KitchenCompanion moment="success" size="sm" /><div><strong>{coverStatus === "failed" ? "Recipe saved, cover needs another try" : "Recipe saved"}</strong><p>{coverStatus === "attached" ? "Recipe and cover are ready in your kitchen." : coverStatus === "failed" ? "The recipe is safe. You can choose a different cover in Edit recipe." : "It is ready in your kitchen."}</p></div></section> : null}
      <RecipeProcessingBanner job={latestJob} nutritionState={recipe.nutritionState} />
       {actionError instanceof Error ? <p className="error-text" role="alert">{actionError.message}</p> : null}

      <RecipeOrganizationPanel recipe={recipe} onSaved={(value) => queryClient.setQueryData(["recipe", recipeId], value)} />

      <nav className="recipe-reading-tabs" aria-label="Recipe sections">
        <button type="button" aria-pressed={mobilePanel === "ingredients"} onClick={() => setMobilePanel("ingredients")}>Ingredients <span>{recipe.ingredients.length}</span></button>
        <button type="button" aria-pressed={mobilePanel === "method"} onClick={() => setMobilePanel("method")}>Method <span>{recipe.instructions.length}</span></button>
      </nav>

      <section className="recipe-reading-grid">
        <section className={`recipe-reading-panel recipe-reading-panel--ingredients${mobilePanel === "ingredients" ? " is-mobile-active" : ""}`} aria-labelledby="ingredients-heading">
          <SectionHeading id="ingredients-heading" title="Ingredients" meta={`${recipe.ingredients.length} items`} />
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
          <SectionHeading id="method-heading" title="Method" meta={`${recipe.instructions.length} steps`} />
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
        <div className="recipe-nutrition-evidence-summary">
          <div><span>Estimate</span><strong>{nutritionStatePresentation.label}</strong><small>{nutritionStatePresentation.description}</small></div>
          <div><span>Ingredient coverage</span><strong>{recipe.nutrition ? `${Math.round(Number(recipe.nutrition.coverageRatio) * 100)}%` : "Not ready"}</strong><small>{recipe.nutrition ? "Quantified ingredients with supporting evidence" : "Coverage will appear when the estimate is ready"}</small></div>
        </div>
        {ingredientReviewCount ? (
          <section className="ingredient-evidence--inline" style={{ borderTop: 0 }}>
            <div><strong>{ingredientReviewCount} food match{ingredientReviewCount === 1 ? "" : "es"} {ingredientReviewCount === 1 ? "needs" : "need"} review</strong><small style={{ display: "block", color: "var(--color-on-surface-variant)", marginTop: "0.15rem" }}>The recipe is still usable. Review these when you want a more specific estimate.</small></div>
             <div className="ingredient-evidence__list">{recipe.ingredients.filter((item) => item.matchStatus === "ambiguous" || item.matchStatus === "unmatched" || item.resolutionKind === "provisional").map((item) => <article key={item.id}><strong>{formatCookingText(item.originalText)}</strong><small>{item.resolutionKind === "provisional" ? `Estimated from ${item.candidateEvidence?.length ?? 0} possible foods` : item.matchStatus === "ambiguous" ? "Several possible foods" : "No food selected yet"}</small></article>)}</div>
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
