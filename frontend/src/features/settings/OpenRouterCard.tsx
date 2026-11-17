import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { KeyRound, Save, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";

import { Button, ErrorRecovery, Field, Skeleton } from "../../components";
import { openRouterSettingsApi } from "./api";
import { FoodLabelsPanel } from "./FoodLabelsPanel";
import type { DecisionFeature, DecisionPurpose } from "./types";

const OPENROUTER_QUERY_KEY = ["openrouter-settings"];
const MAX_MODELS = 3;
const MODEL_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._:/-]{0,119}$/;

const DECISION_FEATURE_COPY: Record<DecisionPurpose, { label: string; description: string }> = {
  match_referee: {
    label: "Ingredient matching",
    description: "Second opinion on food matches. Resolves or flags a line only when it matters for nutrition.",
  },
  food_labels: {
    label: "Food labels",
    description: "Labels USDA foods once (raw or cooked, branded, allergens) to sharpen matching.",
  },
  import_line_gate: {
    label: "Import line filter",
    description: "Moves headings and notes out of imported ingredient lists.",
  },
  import_screen: {
    label: "Import safety check",
    description: "Spots pages that try to instruct an AI, and pages that need no cleanup.",
  },
  cleanup_verifier: {
    label: "Cleanup check",
    description: "Rejects an import cleanup that adds ingredients the source does not have.",
  },
  hidden_ingredients: {
    label: "Hidden ingredients",
    description: "Warns when an ingredient may contain something on your avoid list.",
  },
  recipe_facets: {
    label: "Recipe tags",
    description: "Diet, cuisine, effort and storage tags for search and planning.",
  },
  substitutions: {
    label: "Substitutions",
    description: "Checks whether a swap works in a particular recipe.",
  },
  grocery_tidy: {
    label: "Grocery tidy",
    description: "Merges duplicate grocery items, sorts them by aisle and marks likely staples.",
  },
  shelf_life: {
    label: "Shelf life",
    description: "Estimates how long pantry items without a known lifespan keep.",
  },
};

type FeatureDraft = { purpose: DecisionPurpose; enabled: boolean; models: string };

function parseModels(value: string): string[] {
  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function featureError(draft: FeatureDraft): string | null {
  const models = parseModels(draft.models);
  if (draft.enabled && models.length === 0) return "Add at least one model or switch this off.";
  if (models.length > MAX_MODELS) return `Use at most ${MAX_MODELS} models.`;
  if (new Set(models).size !== models.length) return "A model is listed twice.";
  if (models.some((model) => !MODEL_PATTERN.test(model))) return "Use model ids like provider/model.";
  return null;
}

function formatUsd(value: string): string {
  const number = Number(value);
  if (!Number.isFinite(number)) return `$${value}`;
  return number > 0 && number < 0.01 ? `$${number.toFixed(4)}` : `$${number.toFixed(2)}`;
}

export function OpenRouterCard() {
  const queryClient = useQueryClient();
  const settings = useQuery({ queryKey: OPENROUTER_QUERY_KEY, queryFn: openRouterSettingsApi.get });
  const [apiKey, setApiKey] = useState("");
  const [cleanupModel, setCleanupModel] = useState("");
  const [tolerancePercent, setTolerancePercent] = useState("2");
  const [capUsd, setCapUsd] = useState("2");
  const [features, setFeatures] = useState<FeatureDraft[]>([]);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (!settings.data) return;
    setCleanupModel(settings.data.cleanupModel);
    setTolerancePercent(String(Number(settings.data.decisionAssistToleranceDv) * 100));
    setCapUsd(String(Number(settings.data.monthlyCapUsd)));
    setFeatures(
      settings.data.decisionFeatures.map((feature: DecisionFeature) => ({
        purpose: feature.purpose,
        enabled: feature.enabled,
        models: feature.models.join(", "),
      })),
    );
  }, [settings.data]);

  const toleranceValue = Number(tolerancePercent);
  const toleranceValid = Number.isFinite(toleranceValue) && toleranceValue > 0 && toleranceValue <= 10;
  const capValue = Number(capUsd);
  const capValid = capUsd.trim() !== "" && Number.isFinite(capValue) && capValue >= 0 && capValue <= 100;
  const featuresValid = features.every((draft) => featureError(draft) === null);

  const save = useMutation({
    mutationFn: (options: { clearApiKey: boolean }) =>
      openRouterSettingsApi.update({
        ...(apiKey.trim() && !options.clearApiKey ? { apiKey: apiKey.trim() } : {}),
        clearApiKey: options.clearApiKey,
        cleanupModel: cleanupModel.trim(),
        decisionAssistToleranceDv: (toleranceValue / 100).toFixed(4),
        monthlyCapUsd: capValue.toFixed(2),
        decisionFeatures: features.map((draft) => ({
          purpose: draft.purpose,
          enabled: draft.enabled,
          models: parseModels(draft.models),
        })),
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
  const updateFeature = (purpose: DecisionPurpose, change: Partial<FeatureDraft>) => {
    setFeatures((current) => current.map((draft) => (draft.purpose === purpose ? { ...draft, ...change } : draft)));
    dirty();
  };
  const matchingEnabled = features.find((draft) => draft.purpose === "match_referee")?.enabled ?? true;

  return (
    <section className="settings-system-intro" aria-labelledby="openrouter-title">
      <strong id="openrouter-title">OpenRouter</strong>
      <p>
        One key powers the decision-model features below and the optional import-cleanup fallback. It is
        encrypted before it is stored and is never shown again. These features send ingredient lines, recipe
        text and food names to OpenRouter; without a key everything stays local.
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
        <Field
          label="Monthly spend cap (USD)"
          hint={`${formatUsd(settings.data.spentThisMonthUsd)} spent this month. Decision features pause when the cap is reached.`}
        >
          <input
            className="input"
            inputMode="decimal"
            value={capUsd}
            aria-invalid={!capValid}
            onChange={(event) => { setCapUsd(event.target.value); dirty(); }}
          />
        </Field>
        <Field
          label="Auto-resolve tolerance (% of daily value)"
          hint="Ingredient matching resolves a line on its own only if the remaining doubt is within this in every tracked nutrient."
        >
          <input
            className="input"
            inputMode="decimal"
            value={tolerancePercent}
            disabled={!matchingEnabled}
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
      <fieldset className="decision-features">
        <legend>Decision features</legend>
        <p className="muted">
          Each feature asks one or more models (comma separated) and combines their answers. Thresholds are tuned
          for the defaults, Jev and Clef.
        </p>
        <ul>
          {features.map((draft) => {
            const copy = DECISION_FEATURE_COPY[draft.purpose];
            const error = featureError(draft);
            const modelsId = `decision-models-${draft.purpose}`;
            const errorId = `${modelsId}-error`;
            return (
              <li key={draft.purpose} className="decision-feature">
                {/* eslint-disable-next-line jsx-a11y/label-has-associated-control -- the label text is copy.label, rendered from a constant map the rule cannot see through */}
                <label className="settings-checkbox">
                  <input
                    type="checkbox"
                    checked={draft.enabled}
                    onChange={(event) => updateFeature(draft.purpose, { enabled: event.target.checked })}
                  />
                  <span>
                    <strong>{copy.label}</strong>
                    <span className="muted">{copy.description}</span>
                  </span>
                </label>
                <div className="decision-feature-models">
                  <input
                    id={modelsId}
                    aria-label={`${copy.label} models`}
                    className="input"
                    value={draft.models}
                    disabled={!draft.enabled}
                    spellCheck={false}
                    aria-invalid={error !== null}
                    aria-describedby={error ? errorId : undefined}
                    onChange={(event) => updateFeature(draft.purpose, { models: event.target.value })}
                  />
                </div>
                {error ? <p id={errorId} className="error-text">{error}</p> : null}
              </li>
            );
          })}
        </ul>
      </fieldset>
      <FoodLabelsPanel enabled={keyConfigured && (features.find((draft) => draft.purpose === "food_labels")?.enabled ?? false)} />
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
          disabled={save.isPending || !toleranceValid || !capValid || !featuresValid}
        >
          {apiKey.trim() ? <KeyRound aria-hidden="true" /> : <Save aria-hidden="true" />}
          {save.isPending ? "Saving…" : apiKey.trim() ? "Save key and settings" : "Save settings"}
        </Button>
      </div>
    </section>
  );
}
