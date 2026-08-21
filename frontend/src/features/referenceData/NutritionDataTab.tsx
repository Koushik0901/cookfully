import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Database, Download, LoaderCircle } from "lucide-react";
import { Button, SectionHeading } from "../../components";
import { referenceDataApi, type InstallUnit } from "./api";
import { ApiProblem } from "../recipes/api";

const ACTIVE_STATUSES = new Set(["queued", "running", "retry_wait"]);

const UNITS: { unit: InstallUnit; title: string; blurb: string; size: string; datasets: InstallUnit[] }[] = [
  {
    unit: "foundation_sr_legacy",
    title: "Foundation + SR Legacy",
    blurb: "About 10,000 whole foods and ingredients — the two databases behind the nutrition engine. Recommended for everyday cooking.",
    size: "~100 MB download",
    datasets: ["foundation_sr_legacy"],
  },
  {
    unit: "branded",
    title: "Branded foods",
    blurb: "Packaged foods you buy by brand — yogurt, bread, sauces, snacks, and other labeled staples — with their serving sizes.",
    size: "~1.5 GB download",
    datasets: ["branded"],
  },
];

export function NutritionDataTab() {
  const queryClient = useQueryClient();
  const status = useQuery({
    queryKey: ["reference-data-status"],
    queryFn: referenceDataApi.status,
    refetchInterval: (query) => {
      const job = query.state.data?.job;
      if (!job || !ACTIVE_STATUSES.has(job.status)) return false;
      return 2_000;
    },
  });
  const install = useMutation({
    mutationFn: (datasets: InstallUnit[]) => referenceDataApi.install(datasets),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["reference-data-status"] });
    },
  });

  const job = status.data?.job;
  const working = job !== undefined && job !== null && ACTIVE_STATUSES.has(job.status);
  const progress =
    job?.progressTotal && job.progressTotal > 0
      ? Math.round(((job.progressCurrent ?? 0) / job.progressTotal) * 100)
      : 0;
  const requested = new Set(status.data?.requestedDatasets ?? []);

  return (
    <section className="settings-section reference-data-section" aria-labelledby="nutrition-data-title">
      <SectionHeading id="nutrition-data-title" title="Nutrition reference data" description="USDA FoodData Central powers ingredient matching. Install it so Cookfully can estimate macros and micronutrients from official reference data." />
      {working && job ? (
        <div className="token-card" role="status">
          <h3>
            <LoaderCircle className="reference-data__spinner" aria-hidden="true" /> Installing USDA data… {progress}%
          </h3>
          <progress aria-label="USDA data install progress" max={100} value={progress}>
            {progress}%
          </progress>
        </div>
      ) : null}
      {job?.status === "failed" ? (
        <div className="token-card" role="alert">
          <h3>Install failed</h3>
          <p>{job.failureMessage ?? "The download could not be completed."}</p>
          <Button
            variant="secondary"
            onClick={() => install.mutate(Array.from(requested) as InstallUnit[])}
            disabled={install.isPending || requested.size === 0}
          >
            <Download aria-hidden="true" /> Retry
          </Button>
        </div>
      ) : null}
      <div className="token-card">
        {UNITS.map(({ unit, title, blurb, size, datasets }) => {
          const installed = requested.has(unit) && job?.status === "succeeded";
          const active = status.data?.releases.some((release) =>
            unit === "foundation_sr_legacy"
              ? release.datasetType === "foundation" || release.datasetType === "sr_legacy"
              : release.datasetType === "branded_food"
          );
          return (
            <div key={unit} className="section-heading">
              <div>
                <h3>
                  <Database aria-hidden="true" /> {title}
                </h3>
                <p>{blurb}</p>
                <p className="muted">{size}</p>
              </div>
              <Button
                variant="secondary"
                className="reference-data__install-button"
                onClick={() => install.mutate(datasets)}
                disabled={Boolean(active) || working || install.isPending}
              >
                {installed ? "Installed" : `Install ${title}`}
              </Button>
            </div>
          );
        })}
      </div>
      {status.data?.releases.length ? (
        <div className="token-card">
          <h3>Active releases</h3>
          <ul>
            {status.data.releases.map((release) => (
              <li key={release.datasetType}>
                {release.datasetType} — {release.releaseId}
              </li>
            ))}
          </ul>
          <p className="muted">
            License: <span>{Array.from(new Set(status.data.releases.map((release) => release.license))).join(", ")}</span>
          </p>
        </div>
      ) : null}
      {install.error instanceof ApiProblem ? (
        <p className="error-text" role="alert">{install.error.message}</p>
      ) : null}
    </section>
  );
}
