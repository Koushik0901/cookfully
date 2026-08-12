import { useQuery } from "@tanstack/react-query";
import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Button, ErrorRecovery, Skeleton } from "../../components";
import { recipesApi } from "./api";

export function CookModePage() {
  const { recipeId } = useParams();
  const recipe = useQuery({
    queryKey: ["recipe", recipeId],
    queryFn: () => recipesApi.get(recipeId!),
    enabled: Boolean(recipeId),
  });
  const [currentStep, setCurrentStep] = useState(0);
  const [checkedIngredients, setCheckedIngredients] = useState<Set<number>>(new Set());
  const wakeLock = useRef<WakeLockSentinel | null>(null);

  useEffect(() => {
    let released = false;
    async function acquire() {
      try {
        if ("wakeLock" in navigator) {
          wakeLock.current = await navigator.wakeLock.request("screen");
          wakeLock.current.addEventListener("release", () => {
            if (!released) wakeLock.current = null;
          });
        }
      } catch { /* page not visible or unsupported */ }
    }
    acquire();
    return () => {
      released = true;
      wakeLock.current?.release().catch(() => {});
    };
  }, []);

  const toggleIngredient = useCallback((index: number) => {
    setCheckedIngredients((prev) => {
      const next = new Set(prev);
      if (next.has(index)) next.delete(index);
      else next.add(index);
      return next;
    });
  }, []);

  function nextStep() {
    setCurrentStep((s) => Math.min(s + 1, (recipe.data?.instructions.length ?? 1) - 1));
  }
  function prevStep() {
    setCurrentStep((s) => Math.max(s - 1, 0));
  }

  if (recipe.isPending) return <Skeleton label="Loading recipe" lines={6} />;
  if (recipe.isError || !recipe.data) return <ErrorRecovery title="Could not load recipe" onRetry={() => recipe.refetch()} />;
  const r = recipe.data;
  const steps = r.instructions;
  const total = steps.length;
  const allIngredientsChecked = checkedIngredients.size >= r.ingredients.length;

  return (
    <div className="cook-mode">
      <header className="cook-mode__header">
        <Button asChild className="button--text cook-mode__back">
          <Link to={`/app/recipes/${recipeId}`}>Exit cook mode</Link>
        </Button>
        <h1 className="cook-mode__title">{r.title}</h1>
        <span className="cook-mode__yield">{r.yieldQuantity} {r.yieldUnit}</span>
      </header>

      <div className="cook-mode__body">
        <aside className="cook-mode__ingredients" aria-label="Ingredient checklist">
          <h2>Ingredients</h2>
          <ul className="cook-mode__ingredient-list">
            {r.ingredients.map((ing, i) => (
              <li key={ing.id}>
                <label className="cook-mode__ingredient">
                  <input
                    type="checkbox"
                    checked={checkedIngredients.has(i)}
                    onChange={() => toggleIngredient(i)}
                  />
                  <span className={checkedIngredients.has(i) ? "cook-mode__checked" : ""}>
                    {ing.originalText}
                  </span>
                </label>
              </li>
            ))}
          </ul>
          {allIngredientsChecked && (
            <p className="cook-mode__all-checked">All ingredients ready!</p>
          )}
        </aside>

        <main className="cook-mode__steps" aria-label="Cooking steps">
          <h2 className="cook-mode__steps-heading">Step {currentStep + 1} of {total}</h2>
          <div className="cook-mode__step-card">
            <span className="cook-mode__step-number data-value">{currentStep + 1}</span>
            <p className="cook-mode__step-text">{steps[currentStep]}</p>
          </div>
          <div className="cook-mode__progress">
            <progress value={currentStep + 1} max={total} aria-label={`Step ${currentStep + 1} of ${total}`} />
          </div>
          <div className="cook-mode__step-controls">
            <Button
              className="button--secondary"
              disabled={currentStep === 0}
              onClick={prevStep}
            >
              Previous
            </Button>
            {currentStep < total - 1 ? (
              <Button onClick={nextStep}>Next step</Button>
            ) : (
              <p className="cook-mode__done">Enjoy your meal!</p>
            )}
          </div>
        </main>
      </div>
    </div>
  );
}
