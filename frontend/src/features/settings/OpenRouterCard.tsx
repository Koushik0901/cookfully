import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { KeyRound, Save, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";

import { Button, ErrorRecovery, Field, Skeleton } from "../../components";
import { openRouterSettingsApi } from "./api";

const OPENROUTER_QUERY_KEY = ["openrouter-settings"];

export function OpenRouterCard() {
  const queryClient = useQueryClient();
  const settings = useQuery({ queryKey: OPENROUTER_QUERY_KEY, queryFn: openRouterSettingsApi.get });
  const [apiKey, setApiKey] = useState("");
  const [cleanupModel, setCleanupModel] = useState("");
  const [assistEnabled, setAssistEnabled] = useState(true);
  const [assistModel, setAssistModel] = useState("");
  const [tolerancePercent, setTolerancePercent] = useState("2");
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (!settings.data) return;
    setCleanupModel(settings.data.cleanupModel);
    setAssistEnabled(settings.data.decisionAssistEnabled);
    setAssistModel(settings.data.decisionAssistModel);
    setTolerancePercent(String(Number(settings.data.decisionAssistToleranceDv) * 100));
  }, [settings.data]);

  const toleranceValue = Number(tolerancePercent);
  const toleranceValid = Number.isFinite(toleranceValue) && toleranceValue > 0 && toleranceValue <= 10;

  const save = useMutation({
    mutationFn: (options: { clearApiKey: boolean }) =>
      openRouterSettingsApi.update({
        ...(apiKey.trim() && !options.clearApiKey ? { apiKey: apiKey.trim() } : {}),
        clearApiKey: options.clearApiKey,
        cleanupModel: cleanupModel.trim(),
        decisionAssistEnabled: assistEnabled,
        decisionAssistModel: assistModel.trim(),
        decisionAssistToleranceDv: (toleranceValue / 100).toFixed(4),
        version: settings.data?.version ?? 1,
      }),
    onSuccess: async () => {
      setApiKey("");
      setSaved(true);
      await queryClient.invalidateQueries({ queryKey: OPENROUTER_QUERY_KEY });
      await queryClient.invalidateQueries({ queryKey: ["recipe-import-settings"] });
    },
  });

  if (settings.isPending) return <Skeleton label="Loading OpenRouter settings" lines={4} />;
  if (settings.isError) {
    return <ErrorRecovery title="OpenRouter settings could not be loaded" onRetry={() => void settings.refetch()} />;
  }

  const dirty = () => setSaved(false);
  const keyConfigured = settings.data.keyConfigured;

  return (
    <section className="settings-system-intro" aria-labelledby="openrouter-title">
      <strong id="openrouter-title">OpenRouter</strong>
      <p>
        One key powers the smarter ingredient matching and the optional import-cleanup fallback. It is
        encrypted before it is stored and is never shown again. Enabling these sends ingredient lines,
        recipe titles and candidate food names to OpenRouter; without a key everything stays local.
      </p>
      <div className="form-grid">
        <Field
          label="API key"
          hint={keyConfigured ? `A key ending in ${settings.data.keyHint ?? "····"} is saved. Enter a new one to replace it.` : "No key saved."}
        >
          <input
            className="input"
            type="password"
            autoComplete="off"
            spellCheck={false}
            value={apiKey}
            placeholder={keyConfigured ? "••••••••••••" : "sk-or-…"}
            onChange={(event) => { setApiKey(event.target.value); dirty(); }}
          />
        </Field>
        <Field label="Smarter ingredient matching">
          <label className="settings-checkbox">
            <input
              type="checkbox"
              checked={assistEnabled}
              onChange={(event) => { setAssistEnabled(event.target.checked); dirty(); }}
            />
            <span>Let a decision model pick foods when the choice can’t change the nutrition</span>
          </label>
        </Field>
        <Field label="Matching model" hint="Tolerances are tuned per model; Jev is the tested default.">
          <input
            className="input"
            value={assistModel}
            disabled={!assistEnabled}
            onChange={(event) => { setAssistModel(event.target.value); dirty(); }}
          />
        </Field>
        <Field
          label="Auto-resolve tolerance (% of daily value)"
          hint="A line is resolved automatically only if the remaining doubt is within this in every tracked nutrient."
        >
          <input
            className="input"
            inputMode="decimal"
            value={tolerancePercent}
            disabled={!assistEnabled}
            aria-invalid={!toleranceValid}
            onChange={(event) => { setTolerancePercent(event.target.value); dirty(); }}
          />
        </Field>
        <Field label="Import cleanup model" hint="Used only when the OpenRouter fallback above is switched on.">
          <input
            className="input"
            value={cleanupModel}
            placeholder="provider/model"
            onChange={(event) => { setCleanupModel(event.target.value); dirty(); }}
          />
        </Field>
      </div>
      {save.error instanceof Error ? <p className="error-text" role="alert">{save.error.message}</p> : null}
      {saved ? <p className="success-text" role="status">OpenRouter settings saved.</p> : null}
      <div className="actions">
        {keyConfigured ? (
          <Button type="button" variant="ghost" onClick={() => save.mutate({ clearApiKey: true })} disabled={save.isPending}>
            <Trash2 aria-hidden="true" /> Remove key
          </Button>
        ) : null}
        <Button
          type="button"
          onClick={() => save.mutate({ clearApiKey: false })}
          disabled={save.isPending || !toleranceValid || !assistModel.trim()}
        >
          {apiKey.trim() ? <KeyRound aria-hidden="true" /> : <Save aria-hidden="true" />}
          {save.isPending ? "Saving…" : apiKey.trim() ? "Save key and settings" : "Save settings"}
        </Button>
      </div>
    </section>
  );
}
