import { useQuery } from "@tanstack/react-query";
import { Check, ChevronLeft, ChevronRight, RotateCcw, X } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { Button, ErrorRecovery, KitchenCompanion, Skeleton } from "../../components";
import { RecipeFallbackArt } from "../../components/cookfully/RecipeFallbackArt";
import { Checkbox } from "@/components/ui/checkbox";
import { recipesApi } from "./api";
import { formatCookingText, servingLabel } from "./formatCooking";
import { RecipeMetadata } from "./RecipeMetadata";

export function CookModePage() {
  const { recipeId } = useParams();
  const recipe = useQuery({
    queryKey: ["recipe", recipeId],
    queryFn: () => recipesApi.get(recipeId!),
    enabled: Boolean(recipeId),
  });
  const [currentStep, setCurrentStep] = useState(0);
  const [complete, setComplete] = useState(false);
  const [checkedIngredients, setCheckedIngredients] = useState<Set<number>>(new Set());
  const [ingredientsOpen, setIngredientsOpen] = useState(
    () => typeof window === "undefined" || typeof window.matchMedia !== "function" || !window.matchMedia("(max-width: 60rem)").matches,
  );
  const [screenAwake, setScreenAwake] = useState(false);
  const wakeLock = useRef<WakeLockSentinel | null>(null);

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

  if (recipe.isPending) return <Skeleton label="Loading recipe" lines={6} />;
  if (recipe.isError || !recipe.data) return <ErrorRecovery title="Could not load recipe" onRetry={() => recipe.refetch()} />;
  const currentRecipe = recipe.data;
  const steps = currentRecipe.instructions;
  const allIngredientsChecked = Boolean(currentRecipe.ingredients.length) && checkedIngredients.size >= currentRecipe.ingredients.length;
  const progress = complete ? total : currentStep + 1;

  return (
    <div className="cook-mode">
      <header className="cook-mode__header">
        <Button asChild variant="ghost" className="cook-mode__back">
          <Link to={"/app/recipes/" + recipeId}><X aria-hidden="true" />Leave</Link>
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
          <div><p className="eyebrow">No method yet</p><h2>Add cooking steps before starting cook mode</h2><p>The ingredients are saved, but this recipe does not have a method to guide you through.</p><Button asChild><Link to={"/app/recipes/" + recipeId + "/edit"}>Add the method</Link></Button></div>
        </main>
      ) : complete ? (
        <main className="cook-mode__complete">
          <div className="cook-mode__complete-media">{currentRecipe.imageUrl ? <img src={currentRecipe.imageUrl} alt="" /> : <RecipeFallbackArt title={currentRecipe.title} />}</div>
          <div className="cook-mode__complete-copy">
            <KitchenCompanion moment="milestone" size="lg" className="cook-mode__complete-companion" />
            <p className="eyebrow">Cooking complete</p>
            <h2>Time to eat.</h2>
            <p>{currentRecipe.title} is ready. Plate it, take a breath, and enjoy what you made.</p>
            <div className="cook-mode__complete-actions">
              <Button asChild><Link to={"/app/recipes/" + recipeId}>Back to recipe</Link></Button>
              <Button variant="secondary" onClick={() => { setCurrentStep(0); setComplete(false); }}><RotateCcw aria-hidden="true" />Cook again</Button>
            </div>
          </div>
        </main>
      ) : (
        <div className="cook-mode__body">
          <aside className="cook-mode__ingredients" aria-label="Ingredient checklist">
            <details open={ingredientsOpen} onToggle={(event) => setIngredientsOpen(event.currentTarget.open)}>
              <summary>
                <span><strong>Ingredients</strong><small>{checkedIngredients.size} of {currentRecipe.ingredients.length} ready</small></span>
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
              {allIngredientsChecked ? <p className="cook-mode__all-checked"><Check aria-hidden="true" />Everything’s ready to cook.</p> : null}
            </details>
          </aside>

          <main className="cook-mode__steps" aria-label="Cooking steps">
            <div className="cook-mode__stage">
              <div className="cook-mode__stage-heading">
                <p className="eyebrow">Step {currentStep + 1} of {total}</p>
                <span>Use ← → to move between steps</span>
              </div>
              <div className="cook-mode__step">
                <span className="cook-mode__step-number data-value" aria-hidden="true">{String(currentStep + 1).padStart(2, "0")}</span>
                <p className="cook-mode__step-text">{steps[currentStep]?.text}</p>
              </div>
              <progress className="cook-mode__progress" value={progress} max={total} aria-label={"Step " + (currentStep + 1) + " of " + total} />
            </div>
            <div className="cook-mode__step-controls">
              <Button variant="secondary" disabled={currentStep === 0} onClick={prevStep}><ChevronLeft aria-hidden="true" />Previous</Button>
              <Button onClick={nextStep}>{currentStep < total - 1 ? "Next step" : "Finish cooking"}<ChevronRight aria-hidden="true" /></Button>
            </div>
          </main>
        </div>
      )}
    </div>
  );
}
