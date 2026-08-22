import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Archive, Database, ListTodo, RefreshCw } from "lucide-react";

import { SectionHeading } from "../../components";
import { ApiProblem } from "../recipes/api";
import type { Job } from "../recipes/types";
import { JobQueueCard } from "./JobQueueCard";
import { jobsApi, type InstallUnit, type JobRunScope } from "./jobsApi";
import { nutritionIntelligenceApi } from "./api";

const ACTIVE_JOB_STATUSES = new Set<Job["status"]>(["queued", "running", "retry_wait"]);

function isActive(job: Job | null | undefined): boolean {
  return Boolean(job && ACTIVE_JOB_STATUSES.has(job.status));
}

function errorMessage(error: unknown): string | undefined {
  if (error instanceof ApiProblem || error instanceof Error) return error.message;
  return error ? "That job could not be started. Try again." : undefined;
}

export function JobsTab() {
  const queryClient = useQueryClient();
  const [message, setMessage] = useState<string>("");
  const [exportJobId, setExportJobId] = useState<string | null>(null);
  const [referenceAction, setReferenceAction] = useState<"all" | "missing" | null>(null);
  const [recipeRunActive, setRecipeRunActive] = useState(false);
  const [embeddingAction, setEmbeddingAction] = useState<JobRunScope | null>(null);

  const recipes = useQuery({
    queryKey: ["jobs-recipe-processing"],
    queryFn: jobsApi.recipeProcessingSummary,
    refetchInterval: (query) => {
      const pollAfterSeconds = query.state.data?.pollAfterSeconds;
      return recipeRunActive || pollAfterSeconds ? (pollAfterSeconds ?? 2) * 1_000 : false;
    },
  });

  const references = useQuery({
    queryKey: ["reference-data-status"],
    queryFn: jobsApi.referenceData,
    refetchInterval: (query) => (isActive(query.state.data?.job) ? 2_000 : false),
  });

  const embeddings = useQuery({
    queryKey: ["jobs-food-embeddings"],
    queryFn: jobsApi.foodEmbeddingSummary,
    refetchInterval: (query) =>
      query.state.data?.pollAfterSeconds ? query.state.data.pollAfterSeconds * 1_000 : false,
  });

  const nutritionIntelligence = useQuery({
    queryKey: ["nutrition-intelligence-settings"],
    queryFn: nutritionIntelligenceApi.get,
    refetchInterval: (query) => query.state.data?.runtimeStatus === "downloading" ? 2_000 : false,
  });

  const exportJob = useQuery({
    queryKey: ["jobs-export", exportJobId],
    queryFn: () => jobsApi.job(exportJobId!),
    enabled: Boolean(exportJobId),
    refetchInterval: (query) => (isActive(query.state.data) ? 2_000 : false),
  });

  const runRecipes = useMutation({
    mutationFn: (scope: JobRunScope) => jobsApi.runRecipeProcessing(scope),
    onMutate: async () => {
      setRecipeRunActive(true);
      await queryClient.invalidateQueries({ queryKey: ["jobs-recipe-processing"] });
    },
    onSuccess: (result) => {
      setMessage(result.failed ? `Queued ${result.accepted} recipes; ${result.failed} could not be queued.` : `Queued ${result.accepted} ${result.accepted === 1 ? "recipe" : "recipes"} for processing.`);
    },
    onSettled: () => {
      setRecipeRunActive(false);
      void queryClient.invalidateQueries({ queryKey: ["jobs-recipe-processing"] });
    },
  });

  const installReferences = useMutation({
    mutationFn: (units: InstallUnit[]) => jobsApi.installReferenceData(units),
    onSuccess: () => {
      setMessage("Reference data install queued. Cookfully will update the nutrition engine in the background.");
      void queryClient.invalidateQueries({ queryKey: ["reference-data-status"] });
    },
    onSettled: () => setReferenceAction(null),
  });

  const runEmbeddings = useMutation({
    mutationFn: (scope: JobRunScope) => jobsApi.runFoodEmbeddings(scope),
    onSuccess: (_, scope) => {
      setMessage(scope === "all" ? "All food embeddings queued for rebuilding." : "Missing food embeddings queued for repair.");
      void queryClient.invalidateQueries({ queryKey: ["jobs-food-embeddings"] });
    },
    onSettled: () => setEmbeddingAction(null),
  });

  const runExport = useMutation({
    mutationFn: () => jobsApi.exportPortable(true),
    onSuccess: (result) => {
      setExportJobId(result.jobId);
      setMessage("Export queued. You can keep cooking while the archive is prepared.");
      void queryClient.invalidateQueries({ queryKey: ["jobs-export", result.jobId] });
    },
  });

  const missingReferenceUnits = useMemo<InstallUnit[]>(() => {
    const releases = references.data?.releases ?? [];
    const foundationReady = releases.some((release) => release.datasetType === "foundation");
    const srLegacyReady = releases.some((release) => release.datasetType === "sr_legacy");
    const brandedReady = releases.some((release) => release.datasetType === "branded_food");
    const units: InstallUnit[] = [];
    if (!foundationReady || !srLegacyReady) units.push("foundation_sr_legacy");
    if (!brandedReady) units.push("branded");
    return units;
  }, [references.data?.releases]);

  const referenceJob = references.data?.job;
  const referenceWorking = isActive(referenceJob);
  const exportStatus = exportJob.data;
  const exportWorking = isActive(exportStatus);
  const recipeData = recipes.data;
  const embeddingData = embeddings.data;
  const modelData = nutritionIntelligence.data;
  const modelDownloading = modelData?.runtimeStatus === "downloading";
  const modelActive = modelData?.downloadJobStatus === "running" ? 1 : 0;
  const modelWaiting = modelData && ["queued", "retry_wait"].includes(modelData.downloadJobStatus ?? "") ? 1 : 0;

  return (
    <section className="settings-section jobs-section" aria-labelledby="jobs-title">
      <SectionHeading
        id="jobs-title"
        eyebrow="Background work"
        title="Jobs"
        description="Run the work that keeps your recipes, nutrition references, and exports current. Jobs run quietly in the background, so you can leave this page as soon as they start."
        action={<span className="jobs-section__badge"><ListTodo aria-hidden="true" /> {recipeData?.active ?? 0} active</span>}
      />

      <div className="jobs-section__intro" role="note">
        <div>
          <strong>One place to restart the kitchen system</strong>
          <p>Use “Run missing only” when you are repairing gaps. “Run all” intentionally refreshes every eligible item.</p>
        </div>
        {message ? <span className="jobs-section__message" role="status">{message}</span> : null}
      </div>

      <div className="job-queue-list">
        <article className="job-queue-card">
          <div className="job-queue-card__main">
            <div className="job-queue-card__heading">
              <span className="job-queue-card__icon"><Database aria-hidden="true" /></span>
              <div>
                <h3>Embedding model</h3>
                <p>Download and verify the selected semantic model before food matching is rebuilt.</p>
              </div>
              {modelDownloading ? <span className="settings-status settings-status--working">Working</span> : null}
            </div>
            <div className="job-queue-card__counts" aria-label="Embedding model queue counts">
              <div><strong>{modelActive}</strong><span>Active</span></div>
              <div><strong>{modelWaiting}</strong><span>Waiting</span></div>
            </div>
            <p className="job-queue-card__hint">
              {modelData ? `${modelData.modelName} · ${modelData.runtimeStatus === "ready" ? "ready for indexing" : modelData.runtimeStatus}.` : "Checking model status…"}
            </p>
            {modelData?.runtimeStatus === "failed" ? <p className="error-text" role="alert">{modelData.downloadFailureMessage ?? "Model download failed."} Save the model settings again to retry.</p> : null}
          </div>
          <div className="job-queue-card__actions">
            <span className="muted">Managed from Nutrition intelligence settings</span>
          </div>
        </article>

        <JobQueueCard
          icon={Database}
          title="Food embedding index"
          description="Precompute semantic vectors for every USDA and custom food so matching stays fast."
          active={embeddingData?.active ?? 0}
          waiting={embeddingData?.waiting ?? 0}
          missing={embeddingData?.missing ?? 0}
          supportsMissing
          allLabel="Rebuild all"
          onRunAll={() => { setMessage(""); setEmbeddingAction("all"); runEmbeddings.mutate("all"); }}
          onRunMissing={() => { setMessage(""); setEmbeddingAction("missing"); runEmbeddings.mutate("missing"); }}
          running={Boolean(embeddingData?.active || embeddingData?.waiting)}
          allPending={runEmbeddings.isPending && embeddingAction === "all"}
          missingPending={runEmbeddings.isPending && embeddingAction === "missing"}
          error={errorMessage(runEmbeddings.error) ?? errorMessage(embeddings.error)}
        >
          <p className="job-queue-card__hint">{embeddingData ? `${embeddingData.indexed.toLocaleString()} of ${embeddingData.total.toLocaleString()} foods indexed with ${embeddingData.modelName}.` : "Checking the semantic index…"}</p>
        </JobQueueCard>

        <JobQueueCard
          icon={RefreshCw}
          title="Recipe processing"
          description="Parse ingredients, match nutrition, and recalculate recipe totals."
          active={recipeData?.active ?? 0}
          waiting={recipeData?.waiting ?? 0}
          missing={recipeData?.missing ?? 0}
          running={recipeRunActive || Boolean(recipeData?.active || recipeData?.waiting)}
          supportsMissing
          allLabel="Run all"
          onRunAll={() => { setMessage(""); runRecipes.mutate("all"); }}
          onRunMissing={() => { setMessage(""); runRecipes.mutate("missing"); }}
          allPending={runRecipes.isPending && runRecipes.variables === "all"}
          missingPending={runRecipes.isPending && runRecipes.variables === "missing"}
          error={errorMessage(runRecipes.error)}
        >
          <p className="job-queue-card__hint">Existing nutrition corrections stay intact when a recipe is re-run.</p>
        </JobQueueCard>

        <JobQueueCard
          icon={Database}
          title="Nutrition reference data"
          description="Install the USDA reference releases used for ingredient matching and estimates."
          active={referenceJob?.status === "running" ? 1 : 0}
          waiting={referenceJob && ["queued", "retry_wait"].includes(referenceJob.status) ? 1 : 0}
          missing={missingReferenceUnits.length}
          supportsMissing
          allLabel="Refresh references"
          onRunAll={() => { setMessage(""); setReferenceAction("all"); installReferences.mutate(["foundation_sr_legacy", "branded"]); }}
          onRunMissing={() => { setMessage(""); setReferenceAction("missing"); installReferences.mutate(missingReferenceUnits); }}
          running={referenceWorking}
          allPending={installReferences.isPending && referenceAction === "all"}
          missingPending={installReferences.isPending && referenceAction === "missing"}
          error={errorMessage(installReferences.error) ?? errorMessage(references.error)}
        >
          <p className="job-queue-card__hint">{missingReferenceUnits.length ? `${missingReferenceUnits.length} release ${missingReferenceUnits.length === 1 ? "unit is" : "units are"} not active yet.` : "All configured release units are active."}</p>
        </JobQueueCard>

        <JobQueueCard
          icon={Archive}
          title="Portable export"
          description="Prepare a complete backup archive of recipes, settings, and media."
          active={exportStatus?.status === "running" ? 1 : 0}
          waiting={exportStatus && ["queued", "retry_wait"].includes(exportStatus.status) ? 1 : 0}
          running={exportWorking}
          allLabel="Run export"
          onRunAll={() => { setMessage(""); runExport.mutate(); }}
          allPending={runExport.isPending}
          error={errorMessage(runExport.error) ?? errorMessage(exportJob.error)}
        >
          <p className="job-queue-card__hint">Media is included so the archive can restore the full cooking library.</p>
        </JobQueueCard>
      </div>
    </section>
  );
}
