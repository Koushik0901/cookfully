import { useMutation, useQuery } from "@tanstack/react-query";
import { Check, ChevronLeft, ChevronRight, RotateCcw, X } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { Button, ErrorRecovery, KitchenCompanion, PageState, RecipeMedia, Skeleton } from "../../components";
import { RecipeFallbackArt } from "../../components/cookfully/RecipeFallbackArt";
import { Checkbox } from "@/components/ui/checkbox";
import { intelligenceApi } from "../intelligence/api";
import { recipesApi } from "./api";
import { formatCookingText, servingLabel } from "./formatCooking";
import { RecipeMetadata } from "./RecipeMetadata";

type CookSession = { currentStep: number; complete: boolean; checkedIngredients: number[] };
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
  return (
    <div role="status" aria-live="polite" aria-label={`Timer ${clamped} min`}>
      Timer {clamped} min{displayMin !== clamped || displaySec !== 0 ? ` — ${displayMin}:${String(displaySec).padStart(2, "0")} remaining` : ""}
    </div>
  );
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
  const recipe = useQuery({
    queryKey: ["recipe", recipeId],
    queryFn: () => recipesApi.get(recipeId!),
    enabled: Boolean(recipeId),
  });
  const [currentStep, setCurrentStep] = useState(() => loadCookSession(recipeId)?.currentStep ?? 0);
  const [complete, setComplete] = useState(() => loadCookSession(recipeId)?.complete ?? false);
  const [checkedIngredients, setCheckedIngredients] = useState<Set<number>>(() => new Set(loadCookSession(recipeId)?.checkedIngredients ?? []));
  const [ingredientsOpen, setIngredientsOpen] = useState(
    () => typeof window === "undefined" || typeof window.matchMedia !== "function" || !window.matchMedia("(max-width: 60rem)").matches,
  );
  const [screenAwake, setScreenAwake] = useState(false);
  const wakeLock = useRef<WakeLockSentinel | null>(null);
  const currentStepRef = useRef(currentStep);

  useEffect(() => {
    currentStepRef.current = currentStep;
  }, [currentStep]);

  // Voice-ready handler: Step+Ingredients+User prompt via same gateway
  const utteranceMut = useMutation({
    mutationFn: (payload: { utterance: string; stepIdx: number; ingredientTexts: string[]; stepText: string }) => {
      const prompt = `Step: ${payload.stepText}\nIngredients: ${payload.ingredientTexts.join(", ")}\nUser: ${payload.utterance}`;
      return intelligenceApi.infer("cook", prompt);
    },
    onSuccess: (data, variables) => {
      const call = data?.functionCalls?.[0] as { name: string; arguments: Record<string, unknown> } | undefined;
      const confidence = data?.confidence ?? 0;
      const isOk = data?.status === "ok" && confidence >= 0.80;
      if (!isOk || call?.name !== "cooking_action") return;
      const action = call.arguments.action as string | undefined;
      if (action === "next") {
        setCurrentStep((s) => {
          const stepsLen = recipe.data?.instructions.length ?? 0;
          if (s < stepsLen - 1) return s + 1;
          if (stepsLen) setComplete(true);
          return s;
        });
        // avoid using stale total; handler above uses latest recipe.data length via closure but we also read ref
        void variables;
      } else if (action === "previous") {
        setComplete(false);
        setCurrentStep((s) => Math.max(s - 1, 0));
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
      return next;
    });
  }, []);

  const total = recipe.data?.instructions.length ?? 0;
  const nextStep = useCallback(() => {
    if (currentStep < total - 1) setCurrentStep((step) => step + 1);
    else if (total) setComplete(true);
  }, [currentStep, total]);
  const prevStep = useCallback(() => {
    setComplete(false);
    setCurrentStep((step) => Math.max(step - 1, 0));
  }, []);

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
  const confidence = utteranceMut.data?.confidence ?? 0;
  const isOk = utteranceMut.data?.status === "ok" && confidence >= 0.80;
  const query = (call?.arguments.query as string | undefined)?.trim();
  const ingredientTexts = currentRecipe.ingredients.map((i) => i.originalText);
  const hasEvidence = Boolean(query && ingredientTexts.join(",").toLowerCase().includes(query.toLowerCase()));
  const matchedIngredient = query ? ingredientTexts.find((i) => i.toLowerCase().includes(query.toLowerCase())) : undefined;
  const rawMinutes = call?.arguments.minutes as number | undefined;
  const clampedMinutes = typeof rawMinutes === "number" ? Math.min(120, Math.max(1, Math.floor(rawMinutes))) : undefined;
  const showTimer =
    isOk &&
    call?.name === "cooking_action" &&
    (call.arguments.action as string) === "timer" &&
    typeof clampedMinutes === "number" &&
    clampedMinutes >= 1 &&
    clampedMinutes <= 120;
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
            <div className="cook-mode__complete-actions">
              <Button asChild>
                <Link to={"/app/recipes/" + recipeId}>Back to recipe</Link>
              </Button>
              <Button
                variant="secondary"
                onClick={() => {
                  setCurrentStep(0);
                  setComplete(false);
                  setCheckedIngredients(new Set());
                }}
              >
                <RotateCcw aria-hidden="true" />
                Cook again
              </Button>
            </div>
          </div>
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

          <main className="cook-mode__steps" aria-label="Cooking steps">
            <div className="cook-mode__stage">
              <div className="cook-mode__stage-heading">
                <p className="eyebrow">
                  Step {currentStep + 1} of {total}
                </p>
                <span>Use ← → to move between steps</span>
              </div>
              <div className="cook-mode__step">
                <span className="cook-mode__step-number data-value" aria-hidden="true">
                  {String(currentStep + 1).padStart(2, "0")}
                </span>
                <p className="cook-mode__step-text">{steps[currentStep]?.text}</p>
              </div>
              <progress className="cook-mode__progress" value={progress} max={total} aria-label={"Step " + (currentStep + 1) + " of " + total} />
            </div>
            <div className="cook-mode__step-controls">
              <Button variant="secondary" disabled={currentStep === 0} onClick={prevStep}>
                <ChevronLeft aria-hidden="true" />
                Previous
              </Button>
              <Button onClick={nextStep}>
                {currentStep < total - 1 ? "Next step" : "Finish cooking"}
                <ChevronRight aria-hidden="true" />
              </Button>
            </div>

            {/* Voice entry — STT transcript=prompt hook */}
            <div className="cook-mode-voice" aria-label="Voice commands" style={{ marginTop: "1rem" }}>
              <div>
                <button type="button" aria-label="Set timer 5 minutes" onClick={() => onUtterance("timer 5")}>
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
              {showTimer && <TimerChip minutes={clampedMinutes!} />}
              {showAnswerChip && <AnswerChip>{matchedIngredient!}</AnswerChip>}
            </div>
          </main>
        </div>
      )}
    </div>
  );
}
