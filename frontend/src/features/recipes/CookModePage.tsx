import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, ChevronLeft, ChevronRight, RotateCcw, X } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";

import { Button, DecimalInput, ErrorRecovery, Field, KitchenCompanion, PageState, RecipeMedia, Skeleton } from "../../components";
import { RecipeFallbackArt } from "../../components/cookfully/RecipeFallbackArt";
import { readOfflineResponse } from "../../app/offlineCache";
import { Checkbox } from "@/components/ui/checkbox";
import { intelligenceApi } from "../intelligence/api";
import { planningApi } from "../plans/api";
import { addDays } from "../plans/dates";
import type { MealPlan, MealPlanEntry } from "../plans/types";
import { recipesApi } from "./api";
import { formatCookingText, servingLabel } from "./formatCooking";
import { RecipeMetadata } from "./RecipeMetadata";

type CookSession = { currentStep: number; complete: boolean; checkedIngredients: number[] };
const COMPACT_COOK_MODE_QUERY = "(max-width: 63.99rem)";

function loadCookSession(recipeId?: string): CookSession | null {
  if (!recipeId || typeof window === "undefined") return null;
  try {
    const value = window.sessionStorage.getItem(`cookfully:cook:${recipeId}`);
    return value ? (JSON.parse(value) as CookSession) : null;
  } catch {
    return null;
  }
}

function TimerChip({ minutes }: { minutes: number }) {
  const clamped = Math.min(120, Math.max(1, Math.floor(minutes)));
  const [remaining, setRemaining] = useState(clamped * 60);
  const timerRef = useRef<number | null>(null);
  useEffect(() => {
    setRemaining(clamped * 60);
    if (timerRef.current) window.clearInterval(timerRef.current);
    timerRef.current = window.setInterval(() => {
      setRemaining((prev) => {
        if (prev <= 1) {
          if (timerRef.current) window.clearInterval(timerRef.current);
          return 0;
        }
        return prev - 1;
      });
    }, 1000);
    return () => {
      if (timerRef.current) window.clearInterval(timerRef.current);
    };
  }, [clamped]);
  const displayMin = Math.floor(remaining / 60);
  const displaySec = remaining % 60;
  const remainingLabel = `${displayMin}:${String(displaySec).padStart(2, "0")}`;
  return <div role="status" aria-live="polite" aria-label={`Timer ${clamped} min`}>{remaining ? `Timer set for ${clamped} min — ${remainingLabel} remaining` : "Timer finished"}</div>;
}

function AnswerChip({ children }: { children: string }) {
  return (
    <div role="status" aria-live="polite">
      {children}
    </div>
  );
}

export function CookModePage() {
  const { recipeId } = useParams();
  const queryClient = useQueryClient();
  const [searchParams] = useSearchParams();
  const plannedEntryId = searchParams.get("entry");
  const plannedWeekStart = searchParams.get("week");
  const plan = useQuery({
    queryKey: ["meal-plan", plannedWeekStart],
    queryFn: () => planningApi.plan(plannedWeekStart!),
    enabled: Boolean(plannedEntryId && plannedWeekStart),
    retry: false,
  });
  const plannedEntry = plan.data?.entries.find((entry) => entry.id === plannedEntryId && entry.recipeId === recipeId);
  const recipe = useQuery({
    queryKey: ["recipe", recipeId],
    queryFn: () => recipesApi.get(recipeId!),
    enabled: Boolean(recipeId),
  });
  const [currentStep, setCurrentStep] = useState(() => loadCookSession(recipeId)?.currentStep ?? 0);
  const [stepDirection, setStepDirection] = useState<"forward" | "backward">("forward");
  const [complete, setComplete] = useState(() => loadCookSession(recipeId)?.complete ?? false);
  const [finishing, setFinishing] = useState(false);
  const [checkedIngredients, setCheckedIngredients] = useState<Set<number>>(() => new Set(loadCookSession(recipeId)?.checkedIngredients ?? []));
  const [preparedServings, setPreparedServings] = useState("1");
  const [leftoverServings, setLeftoverServings] = useState("0");
  const [leftoversExpireOn, setLeftoversExpireOn] = useState("");
  const [syncError, setSyncError] = useState("");
  const [ingredientsOpen, setIngredientsOpen] = useState(
    () => typeof window === "undefined" || typeof window.matchMedia !== "function" || !window.matchMedia(COMPACT_COOK_MODE_QUERY).matches,
  );
  const [screenAwake, setScreenAwake] = useState(false);
  const [offlineRecipeReady, setOfflineRecipeReady] = useState(false);
  const [timer, setTimer] = useState<{ minutes: number; run: number } | null>(null);
  const wakeLock = useRef<WakeLockSentinel | null>(null);
  const currentStepRef = useRef(currentStep);
  const touchStartX = useRef<number | null>(null);
  const hydratedEntryVersion = useRef<number | null>(null);
  const startAttempted = useRef<string | null>(null);

  const updatePlannedEntry = useCallback((nextEntry: MealPlanEntry) => {
    if (!plannedWeekStart) return;
    queryClient.setQueryData<MealPlan>(["meal-plan", plannedWeekStart], (current) => {
      if (!current) return current;
      return {
        ...current,
        entries: current.entries.map((entry) => entry.id === nextEntry.id && entry.version < nextEntry.version ? nextEntry : entry),
      };
    });
    void queryClient.invalidateQueries({ queryKey: ["home-bootstrap"] });
  }, [plannedWeekStart, queryClient]);

  const startCooking = useMutation({
    mutationFn: (entry: MealPlanEntry) => planningApi.startCooking(entry.id, entry.version),
    onSuccess: updatePlannedEntry,
    onError: (error) => setSyncError(error instanceof Error ? error.message : "Cooking progress could not be started."),
  });
  const saveProgress = useMutation({
    mutationFn: ({ entryId, step, checked }: { entryId: string; step: number; checked: number[] }) => planningApi.saveCookingProgress(entryId, { currentStep: step, checkedIngredients: checked }),
    onSuccess: updatePlannedEntry,
    onError: () => setSyncError("This cooking step is saved on this device, but could not be synced yet."),
  });
  const completeCooking = useMutation({
    mutationFn: ({ entry, prepared, leftovers, expiresOn }: { entry: MealPlanEntry; prepared: string; leftovers: string; expiresOn: string }) => planningApi.completeCooking(entry.id, entry.version, {
      preparedServings: prepared,
      leftoverServings: leftovers,
      leftoversExpireOn: Number(leftovers) > 0 ? expiresOn : null,
    }),
    onSuccess: (entry) => {
      updatePlannedEntry(entry);
      setSyncError("");
      setFinishing(false);
      setComplete(true);
    },
    onError: (error) => setSyncError(error instanceof Error ? error.message : "Cooking completion could not be saved."),
  });
  const undoCooking = useMutation({
    mutationFn: (entry: MealPlanEntry) => planningApi.undoCooking(entry.id, entry.version),
    onSuccess: (entry) => {
      updatePlannedEntry(entry);
      setComplete(false);
      setFinishing(false);
      setSyncError("");
    },
    onError: (error) => setSyncError(error instanceof Error ? error.message : "Cooking completion could not be undone."),
  });
  const finishLeftovers = useMutation({
    mutationFn: (entry: MealPlanEntry) => planningApi.finishLeftovers(entry.id, entry.version),
    onSuccess: (entry) => {
      updatePlannedEntry(entry);
      setSyncError("");
    },
    onError: (error) => setSyncError(error instanceof Error ? error.message : "Leftovers could not be updated."),
  });

  useEffect(() => {
    currentStepRef.current = currentStep;
  }, [currentStep]);

  useEffect(() => {
    if (!plannedEntry || hydratedEntryVersion.current === plannedEntry.version) return;
    hydratedEntryVersion.current = plannedEntry.version;
    setCurrentStep(plannedEntry.cookingStep ?? 0);
    setCheckedIngredients(new Set(plannedEntry.checkedIngredients ?? []));
    setComplete(plannedEntry.cookingStatus === "cooked");
    if (plannedEntry.cookingStatus === "cooked") setFinishing(false);
    setPreparedServings(plannedEntry.preparedServings ?? plannedEntry.servings);
    setLeftoverServings(plannedEntry.leftoverServings ?? "0");
    setLeftoversExpireOn(plannedEntry.leftoversExpireOn ?? addDays(plannedEntry.localDate, 3));
  }, [plannedEntry]);

  useEffect(() => {
    if (!plannedEntry || plannedEntry.cookingStatus !== "planned" || startAttempted.current === plannedEntry.id) return;
    startAttempted.current = plannedEntry.id;
    startCooking.mutate(plannedEntry);
  }, [plannedEntry, startCooking]);

  useEffect(() => {
    let cancelled = false;
    setOfflineRecipeReady(false);
    if (!recipeId || !recipe.data?.id) return;
    void readOfflineResponse(`/api/v1/recipes/${recipeId}`).then((cachedRecipe) => {
      if (!cancelled) setOfflineRecipeReady(cachedRecipe !== undefined);
    });
    return () => {
      cancelled = true;
    };
  }, [recipe.data?.id, recipeId]);

  const persistProgress = useCallback((step: number, checked: Set<number>) => {
    if (!plannedEntry) return;
    setSyncError("");
    saveProgress.mutate({ entryId: plannedEntry.id, step, checked: [...checked].sort((a, b) => a - b) });
  }, [plannedEntry, saveProgress]);

  // Voice-ready handler: Step+Ingredients+User prompt via same gateway
  const utteranceMut = useMutation({
    mutationFn: (payload: { utterance: string; stepIdx: number; ingredientTexts: string[]; stepText: string }) => {
      const prompt = `Step: ${payload.stepText}\nIngredients: ${payload.ingredientTexts.join(", ")}\nUser: ${payload.utterance}`;
      return intelligenceApi.infer("cook", prompt);
    },
    onSuccess: (data) => {
      const call = data?.functionCalls?.[0] as { name: string; arguments: Record<string, unknown> } | undefined;
      const confidence = data?.confidence ?? 0;
      const isOk = data?.status === "ok" && confidence >= 0.80;
      if (!isOk || call?.name !== "cooking_action") return;
      const action = call.arguments.action as string | undefined;
      if (action === "next") {
        setStepDirection("forward");
        setCurrentStep((s) => {
          const stepsLen = recipe.data?.instructions.length ?? 0;
          if (s < stepsLen - 1) {
            const next = s + 1;
            persistProgress(next, checkedIngredients);
            return next;
          }
          if (stepsLen) {
            if (plannedEntry) setFinishing(true);
            else setComplete(true);
          }
          return s;
        });
      } else if (action === "previous") {
        setFinishing(false);
        setStepDirection("backward");
        setCurrentStep((s) => {
          const previous = Math.max(s - 1, 0);
          persistProgress(previous, checkedIngredients);
          return previous;
        });
      } else if (action === "timer") {
        const minutes = Number(call.arguments.minutes);
        if (Number.isFinite(minutes)) setTimer({ minutes: Math.min(120, Math.max(1, Math.floor(minutes))), run: Date.now() });
      }
    },
  });

  const onUtterance = useCallback(
    (utterance: string) => {
      const stepText = recipe.data?.instructions[currentStepRef.current]?.text ?? "";
      const ingredientTexts = (recipe.data?.ingredients ?? []).map((i) => i.originalText);
      utteranceMut.mutate({ utterance, stepIdx: currentStepRef.current, ingredientTexts, stepText });
    },
    [recipe.data, utteranceMut],
  );

  const startTimer = useCallback((minutes: number) => {
    setTimer({ minutes: Math.min(120, Math.max(1, Math.floor(minutes))), run: Date.now() });
  }, []);

  useEffect(() => {
    let released = false;
    async function acquire() {
      try {
        if ("wakeLock" in navigator) {
          wakeLock.current = await navigator.wakeLock.request("screen");
          if (!released) setScreenAwake(true);
          wakeLock.current.addEventListener("release", () => {
            if (!released) {
              wakeLock.current = null;
              setScreenAwake(false);
            }
          });
        }
      } catch {
        if (!released) setScreenAwake(false);
      }
    }
    void acquire();
    return () => {
      released = true;
      wakeLock.current?.release().catch(() => {});
    };
  }, []);

  useEffect(() => {
    if (!recipeId || typeof window === "undefined") return;
    try {
      window.sessionStorage.setItem(
        `cookfully:cook:${recipeId}`,
        JSON.stringify({ currentStep, complete, checkedIngredients: [...checkedIngredients] } satisfies CookSession),
      );
    } catch {
      // Cooking still works if storage is unavailable (private browsing or a restricted WebView).
    }
  }, [checkedIngredients, complete, currentStep, recipeId]);

  const toggleIngredient = useCallback((index: number) => {
    setCheckedIngredients((previous) => {
      const next = new Set(previous);
      if (next.has(index)) next.delete(index);
      else next.add(index);
      persistProgress(currentStepRef.current, next);
      return next;
    });
  }, [persistProgress]);

  const total = recipe.data?.instructions.length ?? 0;
  const nextStep = useCallback(() => {
    if (currentStep < total - 1) {
      setStepDirection("forward");
      const next = currentStep + 1;
      setCurrentStep(next);
      persistProgress(next, checkedIngredients);
    }
    else if (total) {
      if (plannedEntry) setFinishing(true);
      else setComplete(true);
    }
  }, [checkedIngredients, currentStep, persistProgress, plannedEntry, total]);
  const prevStep = useCallback(() => {
    setFinishing(false);
    setStepDirection("backward");
    const previous = Math.max(currentStep - 1, 0);
    setCurrentStep(previous);
    persistProgress(previous, checkedIngredients);
  }, [checkedIngredients, currentStep, persistProgress]);

  useEffect(() => {
    function navigateSteps(event: KeyboardEvent) {
      if (event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return;
      if (event.target instanceof HTMLElement && event.target.closest("button, a, summary, input, select, textarea")) return;
      if (event.key === "ArrowRight") {
        event.preventDefault();
        nextStep();
      }
      if (event.key === "ArrowLeft") {
        event.preventDefault();
        prevStep();
      }
    }
    window.addEventListener("keydown", navigateSteps);
    return () => window.removeEventListener("keydown", navigateSteps);
  }, [nextStep, prevStep]);

  if (recipe.isPending)
    return (
      <PageState>
        <Skeleton label="Loading recipe" lines={6} />
      </PageState>
    );
  if (recipe.isError || !recipe.data)
    return (
      <PageState>
        <ErrorRecovery title="Could not load recipe" onRetry={() => recipe.refetch()} />
      </PageState>
    );
  const currentRecipe = recipe.data;
  const steps = currentRecipe.instructions;
  const allIngredientsChecked = Boolean(currentRecipe.ingredients.length) && checkedIngredients.size >= currentRecipe.ingredients.length;
  const progress = complete ? total : currentStep + 1;

  // Voice derived chips
  const call = utteranceMut.data?.functionCalls?.[0] as { name: string; arguments: Record<string, unknown> } | undefined;
  const query = (call?.arguments.query as string | undefined)?.trim();
  const ingredientTexts = currentRecipe.ingredients.map((i) => i.originalText);
  const hasEvidence = Boolean(query && ingredientTexts.join(",").toLowerCase().includes(query.toLowerCase()));
  const matchedIngredient = query ? ingredientTexts.find((i) => i.toLowerCase().includes(query.toLowerCase())) : undefined;
  const showAnswerChip = Boolean(hasEvidence && matchedIngredient);

  return (
    <div className="cook-mode">
      <header className="cook-mode__header">
        <Button asChild variant="ghost" className="cook-mode__back">
          <Link to={"/app/recipes/" + recipeId}>
            <X aria-hidden="true" />
            Leave
          </Link>
        </Button>
        <div className="cook-mode__identity">
          <p>Now cooking</p>
          <h1 className="cook-mode__title">{currentRecipe.title}</h1>
        </div>
        <div className="cook-mode__meta">
          <strong>{servingLabel(currentRecipe.yieldQuantity, currentRecipe.yieldUnit)}</strong>
          <RecipeMetadata recipe={currentRecipe} compact />
          <span>{screenAwake ? "Screen stays awake" : "Cook mode"}</span>
        </div>
      </header>
      {syncError ? <p className="cook-mode__sync-error" role="alert">{syncError}</p> : plannedEntry?.cookingStatus === "cooking" ? <p className="cook-mode__sync-status" role="status">Progress is saved to your plan.</p> : null}

      {!steps.length ? (
        <main className="cook-mode__empty">
          <RecipeFallbackArt title={currentRecipe.title} />
          <div>
            <p className="eyebrow">No method yet</p>
            <h2>Add cooking steps before starting cook mode</h2>
            <p>The ingredients are saved, but this recipe does not have a method to guide you through.</p>
            <Button asChild>
              <Link to={"/app/recipes/" + recipeId + "/edit"}>Add the method</Link>
            </Button>
          </div>
        </main>
      ) : complete ? (
        <main className="cook-mode__complete">
          <div className="cook-mode__complete-media">
            <RecipeMedia recipe={currentRecipe} loading="eager" />
          </div>
          <div className="cook-mode__complete-copy">
            <KitchenCompanion moment="milestone" size="lg" className="cook-mode__complete-companion" />
            <p className="eyebrow">Cooking complete</p>
            <h2>Time to eat.</h2>
            <p>{currentRecipe.title} is ready. Plate it, take a breath, and enjoy what you made.</p>
            {plannedEntry && Number(plannedEntry.leftoverServings ?? 0) > 0 ? <p className="cook-mode__leftovers"><strong>{plannedEntry.leftoverServings} leftover {Number(plannedEntry.leftoverServings) === 1 ? "serving" : "servings"}</strong> saved until {plannedEntry.leftoversExpireOn}.</p> : null}
            <div className="cook-mode__complete-actions">
              <Button asChild>
                <Link to={plannedEntry ? `/app/plan?date=${plannedEntry.localDate}` : "/app/recipes/" + recipeId}>{plannedEntry ? "Back to today’s plan" : "Back to recipe"}</Link>
              </Button>
              {plannedEntry && Number(plannedEntry.leftoverServings ?? 0) > 0 ? <Button variant="secondary" disabled={finishLeftovers.isPending} onClick={() => finishLeftovers.mutate(plannedEntry)}>Leftovers finished</Button> : null}
              {plannedEntry ? <Button variant="ghost" disabled={undoCooking.isPending} onClick={() => undoCooking.mutate(plannedEntry)}>
                <RotateCcw aria-hidden="true" />
                Undo completion
              </Button> : <Button
                variant="secondary"
                onClick={() => {
                  setCurrentStep(0);
                  setComplete(false);
                  setFinishing(false);
                  setCheckedIngredients(new Set());
                }}
              >
                <RotateCcw aria-hidden="true" />
                Cook again
              </Button>}
            </div>
          </div>
        </main>
      ) : finishing ? (
        <main className="cook-mode__finish">
          <div className="cook-mode__finish-copy">
            <p className="eyebrow">Dinner is ready</p>
            <h2>Finish this cooking session</h2>
            <p>Save only what is useful. Leftovers are optional and never change your pantry automatically.</p>
          </div>
          <form className="cook-mode__finish-form" onSubmit={(event) => {
            event.preventDefault();
            const prepared = Number(preparedServings);
            const leftovers = Number(leftoverServings || 0);
            if (!Number.isFinite(prepared) || prepared <= 0 || !Number.isFinite(leftovers) || leftovers < 0 || leftovers > prepared) {
              setSyncError("Enter how much you made, with leftovers no greater than that amount.");
              return;
            }
            if (leftovers > 0 && !leftoversExpireOn) {
              setSyncError("Choose a use-by date for the leftovers.");
              return;
            }
            if (plannedEntry) completeCooking.mutate({ entry: plannedEntry, prepared: preparedServings, leftovers: leftoverServings || "0", expiresOn: leftoversExpireOn });
            else {
              setFinishing(false);
              setComplete(true);
            }
          }}>
            <div className="cook-mode__finish-fields">
              <Field label="Servings made"><DecimalInput value={preparedServings} onInput={(event) => setPreparedServings(event.currentTarget.value)} /></Field>
              <Field label="Leftover servings (optional)"><DecimalInput value={leftoverServings} onInput={(event) => setLeftoverServings(event.currentTarget.value)} /></Field>
              {Number(leftoverServings) > 0 ? <Field label="Use leftovers by"><input className="input data-value" type="date" min={plannedEntry?.localDate} value={leftoversExpireOn} onChange={(event) => setLeftoversExpireOn(event.currentTarget.value)} /></Field> : null}
            </div>
            <div className="cook-mode__finish-actions">
              <Button type="button" variant="secondary" onClick={() => setFinishing(false)}>Back to last step</Button>
              <Button type="submit" disabled={completeCooking.isPending || saveProgress.isPending}>{completeCooking.isPending ? "Saving…" : "Finish cooking"}</Button>
            </div>
          </form>
        </main>
      ) : (
        <div className="cook-mode__body">
          <aside className="cook-mode__ingredients" aria-label="Ingredient checklist">
            <details open={ingredientsOpen} onToggle={(event) => setIngredientsOpen(event.currentTarget.open)}>
              <summary>
                <span>
                  <strong>Ingredients</strong>
                  <small>
                    {checkedIngredients.size} of {currentRecipe.ingredients.length} ready
                  </small>
                </span>
                <span className="cook-mode__ingredients-toggle">{ingredientsOpen ? "Hide" : "Show"}</span>
              </summary>
              <ul className="cook-mode__ingredient-list">
                {currentRecipe.ingredients.map((ingredient, index) => (
                  <li key={ingredient.id}>
                    <label className="cook-mode__ingredient">
                      <Checkbox checked={checkedIngredients.has(index)} onCheckedChange={() => toggleIngredient(index)} />
                      <span className={checkedIngredients.has(index) ? "cook-mode__checked" : ""}>{formatCookingText(ingredient.originalText)}</span>
                    </label>
                  </li>
                ))}
              </ul>
              {allIngredientsChecked ? (
                <p className="cook-mode__all-checked">
                  <Check aria-hidden="true" />
                  Everything’s ready to cook.
                </p>
              ) : null}
            </details>
          </aside>

          <main
            className="cook-mode__steps"
            aria-label="Cooking steps"
            onPointerDown={(event) => { if (event.pointerType === "touch") touchStartX.current = event.clientX; }}
            onPointerUp={(event) => {
              if (touchStartX.current == null) return;
              const distance = event.clientX - touchStartX.current;
              touchStartX.current = null;
              if (Math.abs(distance) < 56) return;
              if (distance < 0) nextStep();
              else prevStep();
            }}
          >
            <div key={currentStep} className={`cook-mode__stage cook-mode__stage--${stepDirection}`}>
              <div className="cook-mode__stage-heading">
                <p className="eyebrow">
                  Step {currentStep + 1} of {total}
                </p>
                <span className={offlineRecipeReady ? "cook-mode__offline-ready" : undefined}>
                  {offlineRecipeReady ? "Available offline · Use ← → to move between steps" : "Use ← → to move between steps"}
                </span>
              </div>
              <div className="cook-mode__step">
                <span className="cook-mode__step-number data-value" aria-hidden="true">
                  {String(currentStep + 1).padStart(2, "0")}
                </span>
                <p className="cook-mode__step-text">{steps[currentStep]?.text}</p>
              </div>
              <progress className="cook-mode__progress" value={progress} max={total} aria-label={"Step " + (currentStep + 1) + " of " + total} />
              <button type="button" className="cook-mode__quick-timer" onClick={() => startTimer(15)}>Start 15 min timer</button>
            </div>
            <div className="cook-mode__step-controls">
              <Button variant="secondary" disabled={currentStep === 0} onClick={prevStep}>
                <ChevronLeft aria-hidden="true" />
                Previous
              </Button>
              <Button disabled={saveProgress.isPending} onClick={nextStep}>
                {currentStep < total - 1 ? "Next step" : "Finish cooking"}
                <ChevronRight aria-hidden="true" />
              </Button>
            </div>

            {/* Voice entry — STT transcript=prompt hook */}
            <div className="cook-mode-voice" aria-label="Voice commands" style={{ marginTop: "1rem" }}>
              <div>
                <button type="button" aria-label="Set timer 5 minutes" onClick={() => { startTimer(5); onUtterance("timer 5"); }}>
                  timer 5
                </button>
                <button type="button" aria-label="Ask how much garlic" onClick={() => onUtterance("how much garlic")}>
                  how much garlic
                </button>
                <button type="button" aria-label="Next step voice" onClick={() => onUtterance("next")}>
                  next
                </button>
                <button type="button" aria-label="Previous step voice" onClick={() => onUtterance("previous")}>
                  previous
                </button>
                <button type="button" aria-label="Repeat step voice" onClick={() => onUtterance("repeat")}>
                  repeat
                </button>
              </div>
              {timer && <TimerChip key={timer.run} minutes={timer.minutes} />}
              {showAnswerChip && <AnswerChip>{matchedIngredient!}</AnswerChip>}
            </div>
          </main>
        </div>
      )}
    </div>
  );
}
