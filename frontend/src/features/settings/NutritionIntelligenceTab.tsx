import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Cpu, Database, Gauge, HardDrive, RotateCcw, Save } from "lucide-react";
import { useDeferredValue, useEffect, useState } from "react";

import { Button, ErrorRecovery, Field, SectionHeading, Select, Skeleton } from "../../components";
import { nutritionIntelligenceApi } from "./api";

const DEFAULT_MODEL = "BAAI/bge-small-en-v1.5";

function formatBytes(value: number) {
  if (value < 1024 ** 2) return `${Math.round(value / 1024)} KB`;
  if (value < 1024 ** 3) return `${(value / 1024 ** 2).toFixed(0)} MB`;
  return `${(value / 1024 ** 3).toFixed(1)} GB`;
}

export function NutritionIntelligenceTab() {
  const queryClient = useQueryClient();
  const settings = useQuery({
    queryKey: ["nutrition-intelligence-settings"],
    queryFn: nutritionIntelligenceApi.get,
  });
  const [backend, setBackend] = useState<"hashing" | "fastembed">("hashing");
  const [modelName, setModelName] = useState(DEFAULT_MODEL);
  const [concurrency, setConcurrency] = useState(1);
  const [saved, setSaved] = useState(false);
  const deferredModelName = useDeferredValue(modelName);

  useEffect(() => {
    if (!settings.data) return;
    setBackend(settings.data.backend);
    setModelName(settings.data.modelName || DEFAULT_MODEL);
    setConcurrency(settings.data.concurrency);
  }, [settings.data]);

  const estimate = useQuery({
    queryKey: ["nutrition-intelligence-estimate", backend, deferredModelName, concurrency],
    queryFn: () =>
      nutritionIntelligenceApi.estimate({
        backend,
        modelName: deferredModelName,
        concurrency,
      }),
    enabled: settings.isSuccess && (backend === "hashing" || deferredModelName.includes("/")),
  });

  const save = useMutation({
    mutationFn: () =>
      nutritionIntelligenceApi.update({
        backend,
        modelName: modelName || DEFAULT_MODEL,
        concurrency,
        version: settings.data?.version ?? 1,
        estimateHash: estimate.data?.estimateHash ?? "",
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["nutrition-intelligence-settings"] });
      setSaved(true);
    },
  });

  if (settings.isPending) return <Skeleton label="Loading nutrition intelligence settings" lines={8} />;
  if (settings.isError) {
    return <ErrorRecovery title="Nutrition intelligence settings could not be loaded" onRetry={() => void settings.refetch()} />;
  }

  const estimateValue = estimate.data;
  const saveBlocked = !estimateValue || estimateValue.status === "blocked" || save.isPending;

  return (
    <section className="settings-section nutrition-intelligence-section" aria-labelledby="nutrition-intelligence-title">
      <SectionHeading id="nutrition-intelligence-title" title="Nutrition intelligence" description="Tune semantic ingredient matching for this Cookfully installation. Deterministic safety gates stay active in every mode." action={<span className={`settings-status settings-status--${settings.data.runtimeStatus}`}>
          {settings.data.runtimeStatus === "ready" ? "Ready" : "Configured"}
        </span>} />

      <div className="settings-system-intro">
        <strong>Plan the load before you save.</strong>
        <p>
          Estimates use the active food count, the selected model&apos;s Hugging Face metadata, and this host&apos;s reported CPU, memory, and disk capacity. They are deliberately conservative, not a benchmark promise.
        </p>
      </div>

      <div className="form-grid">
        <Field label="Matching backend">
          <Select value={backend} onChange={(event) => { setBackend(event.target.value as "hashing" | "fastembed"); setSaved(false); }}>
            <option value="hashing">Deterministic + hashing fallback</option>
            <option value="fastembed">FastEmbed Hugging Face model</option>
          </Select>
        </Field>
        <Field
          label="Hugging Face model name"
          hint="Use an organization/model identifier. The model is downloaded only after you save and a nutrition job needs it."
        >
          <input
            className="input"
            value={modelName}
            disabled={backend === "hashing"}
            placeholder={DEFAULT_MODEL}
            onChange={(event) => { setModelName(event.target.value); setSaved(false); }}
          />
        </Field>
      </div>

      <Field label={`Nutrition matching concurrency: ${concurrency}`}>
        <div>
          <input
            className="settings-range"
            type="range"
            min={1}
            max={4}
            step={1}
            value={concurrency}
            onChange={(event) => { setConcurrency(Number(event.target.value)); setSaved(false); }}
            aria-label={`Nutrition matching concurrency: ${concurrency}`}
            aria-valuetext={`${concurrency} concurrent nutrition matching jobs`}
          />
          <div className="settings-range-labels"><span>1, gentler</span><span>4, faster</span></div>
        </div>
      </Field>

      {estimate.isPending ? <p className="muted" role="status">Checking the selected model and system capacity…</p> : null}
      {estimate.isError ? <p className="error-text" role="alert">{estimate.error instanceof Error ? estimate.error.message : "The model estimate could not be loaded."}</p> : null}
      {estimateValue ? (
        <div className={`resource-estimate resource-estimate--${estimateValue.status}`} aria-live="polite">
          <div className="resource-estimate__heading">
            <div>
              <p className="eyebrow">Pre-save estimate</p>
              <h3>{estimateValue.status === "safe" ? "Comfortable headroom" : estimateValue.status === "warning" ? "Usable, with trade-offs" : "Too demanding for this host"}</h3>
            </div>
            <span className="resource-estimate__status">{estimateValue.status}</span>
          </div>
          <div className="resource-estimate__grid">
            <div><Cpu aria-hidden="true" /><span><strong>{estimateValue.requiredCpuCores} / {estimateValue.availableCpuCores}</strong><small>CPU cores</small></span></div>
            <div><Database aria-hidden="true" /><span><strong>{formatBytes(estimateValue.totalMemoryBytes)}</strong><small>estimated RAM</small></span></div>
            <div><HardDrive aria-hidden="true" /><span><strong>{formatBytes(estimateValue.downloadBytes)}</strong><small>model download</small></span></div>
            <div><Gauge aria-hidden="true" /><span><strong>{formatBytes(Math.max(0, estimateValue.memoryHeadroomBytes))}</strong><small>RAM headroom</small></span></div>
          </div>
          {estimateValue.modelRevision ? <p className="muted">Revision {estimateValue.modelRevision.slice(0, 12)} · {estimateValue.activeFoodCount.toLocaleString()} active foods</p> : null}
          {estimateValue.warnings.length ? <ul className="resource-estimate__warnings">{estimateValue.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul> : null}
        </div>
      ) : null}

      {save.error instanceof Error ? <p className="error-text" role="alert">{save.error.message}</p> : null}
      {saved ? <p className="success-text" role="status">Nutrition intelligence settings saved. Existing manual matches are unchanged.</p> : null}
      <div className="actions">
        <Button type="button" variant="ghost" onClick={() => { setBackend("hashing"); setModelName(DEFAULT_MODEL); setConcurrency(1); setSaved(false); }} disabled={save.isPending}>
          <RotateCcw aria-hidden="true" /> Reset draft
        </Button>
        <Button type="button" onClick={() => save.mutate()} disabled={saveBlocked}>
          <Save aria-hidden="true" /> {save.isPending ? "Saving…" : "Save settings"}
        </Button>
      </div>
    </section>
  );
}
