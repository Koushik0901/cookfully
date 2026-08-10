import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";

import { Button, ConfirmDialog, ErrorRecovery, Skeleton } from "../../components";
import { recipesApi } from "./api";
import { NutritionPanel } from "./NutritionPanel";
import type { Job, NutritionCorrectionWrite, RecipeDetail } from "./types";

const terminalStatuses = new Set(["succeeded", "failed", "cancelled", "superseded"]);

export function RecipeDetailPage() {
  const { recipeId } = useParams();
  const location = useLocation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const routeJobId = (location.state as { jobId?: string } | null)?.jobId;
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

  if (detail.isPending) return <Skeleton label="Loading recipe" lines={8} />;
  if (detail.isError || !detail.data) return <ErrorRecovery title="Recipe could not be loaded" onRetry={() => void detail.refetch()} />;
  const recipe = detail.data;
  const actionError = [correction.error, reset.error, recalculate.error, archive.error, restore.error, permanentDelete.error].find((value) => value instanceof Error);

  return (
    <main className="page-shell">
      <header className="page-header">
        <div><p className="eyebrow">{recipe.status === "archived" ? "Archived recipe" : "Recipe"}</p><h1>{recipe.title}</h1><p className="lede">{recipe.description || `${recipe.yieldQuantity} ${recipe.yieldUnit}`}</p></div>
        <div className="actions"><Button asChild className="button--secondary"><Link to="/app/recipes">Library</Link></Button><Button asChild><Link to={`/app/recipes/${recipe.id}/edit`}>Edit recipe</Link></Button></div>
      </header>

      {actionError instanceof Error ? <p className="error-text" role="alert">{actionError.message}</p> : null}
      <section className="recipe-detail-grid">
        <div className="recipe-content">
          <section><h2>Ingredients</h2><ul className="ingredient-list">{recipe.ingredients.map((item) => <li key={item.id}><span>{item.originalText}</span><small>{[item.quantityMin, item.quantityMax ? `–${item.quantityMax}` : null, item.unit, item.food, item.preparation].filter(Boolean).join(" ") || "Original text retained; structured parsing unavailable."} · {item.parseStatus}{item.matchStatus ? ` / ${item.matchStatus}` : ""}</small>{item.assumptions?.map((assumption) => <small key={assumption}>{assumption}</small>)}</li>)}</ul></section>
          <section><h2>Instructions</h2>{recipe.instructions.length ? <ol className="instruction-list">{recipe.instructions.map((step, index) => <li key={`${index}-${step}`}>{step}</li>)}</ol> : <p className="muted">No instructions were provided.</p>}</section>
          {recipe.sourceUrl ? <p>Original source: <a href={recipe.sourceUrl} rel="noreferrer">{new URL(recipe.sourceUrl).hostname}</a></p> : null}
        </div>
        <NutritionPanel nutrition={recipe.nutrition} nutritionState={recipe.nutritionState} job={job.data ?? recipe.activeJob} onCorrect={async (value) => { await correction.mutateAsync(value); }} onResetCorrection={async (id) => { await reset.mutateAsync(id); }} onRecalculate={async (resetCorrections = false) => { await recalculate.mutateAsync(resetCorrections); }} />
      </section>

      <section className="danger-zone" aria-labelledby="lifecycle-heading"><h2 id="lifecycle-heading">Recipe lifecycle</h2>
        {recipe.status === "archived" ? <><p>Restore this recipe for active planning, or permanently remove its recipe content.</p><div className="actions"><Button onClick={() => restore.mutate()}>Restore recipe</Button><ConfirmDialog trigger={<Button className="button--danger">Permanently delete recipe</Button>} title="Permanently delete this recipe?" description="Recipe content and media will be erased after the bounded recovery window. Historical plan and grocery records remain detached so their past facts stay accurate." confirmLabel="Delete permanently" onConfirm={() => permanentDelete.mutate()} /></div></> : <><p>Archiving hides the recipe from active planning without deleting it.</p><ConfirmDialog trigger={<Button className="button--secondary">Archive recipe</Button>} title="Archive this recipe?" description="You can restore it later from the archived recipe view." confirmLabel="Archive" onConfirm={() => archive.mutate()} /></>}
      </section>
    </main>
  );
}
