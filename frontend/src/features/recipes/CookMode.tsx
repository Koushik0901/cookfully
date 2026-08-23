import { useMutation } from "@tanstack/react-query";
import { useCallback, useEffect, useRef, useState } from "react";

import { intelligenceApi } from "../intelligence/api";

// STT transcript=prompt: Web Speech API transcript feeds directly into prompt User: field
// No draft table write; operation="cook" routes to _TOOLS["cook"] hardened Literal[4] + minutes 1..120 + query 3..80.
// System facts preserved via existing gateway; fail-quiet on unavailable/unsupported/low confidence.

type CookModeProps = {
  recipe: {
    id?: string;
    title: string;
    ingredients: Array<{ originalText: string } | string>;
    instructions: Array<{ text: string } | string>;
  };
  currentStep?: number;
};

function toIngredientTexts(ingredients: CookModeProps["recipe"]["ingredients"]): string[] {
  return ingredients.map((ing) => (typeof ing === "string" ? ing : ing.originalText));
}

function toStepTexts(instructions: CookModeProps["recipe"]["instructions"]): string[] {
  return instructions.map((step) => (typeof step === "string" ? step : step.text));
}

function TimerChip({ minutes }: { minutes: number }) {
  const clamped = Math.min(120, Math.max(1, minutes));
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

export function CookMode({ recipe, currentStep: initialStep = 0 }: CookModeProps) {
  const ingredients = toIngredientTexts(recipe.ingredients);
  const steps = toStepTexts(recipe.instructions);
  const [internalStep, setInternalStep] = useState(initialStep);
  const internalStepRef = useRef(internalStep);
  const stepsRef = useRef(steps);
  const ingredientsRef = useRef(ingredients);

  useEffect(() => {
    setInternalStep(initialStep);
  }, [initialStep]);

  useEffect(() => {
    internalStepRef.current = internalStep;
  }, [internalStep]);

  useEffect(() => {
    stepsRef.current = steps;
  }, [steps]);

  useEffect(() => {
    ingredientsRef.current = ingredients;
  }, [ingredients]);

  const utteranceMut = useMutation({
    mutationFn: (payload: { utterance: string; stepIdx: number }) => {
      const stepText = stepsRef.current[payload.stepIdx] ?? "";
      const ing = ingredientsRef.current.join(", ");
      const prompt = `Step: ${stepText}\nIngredients: ${ing}\nUser: ${payload.utterance}`;
      return intelligenceApi.infer("cook", prompt);
    },
    onSuccess: (data) => {
      const call = data?.functionCalls?.[0] as { name: string; arguments: Record<string, unknown> } | undefined;
      const confidence = data?.confidence ?? 0;
      const isOk = data?.status === "ok" && confidence >= 0.80;
      if (!isOk || call?.name !== "cooking_action") return;
      const action = call.arguments.action as string | undefined;
      if (action === "next") {
        setInternalStep((s) => Math.min(s + 1, Math.max(stepsRef.current.length - 1, 0)));
      } else if (action === "previous") {
        setInternalStep((s) => Math.max(s - 1, 0));
      }
    },
  });

  const onUtterance = useCallback(
    (u: string) => {
      const idx = internalStepRef.current;
      utteranceMut.mutate({ utterance: u, stepIdx: idx });
    },
    [utteranceMut],
  );

  const call = utteranceMut.data?.functionCalls?.[0] as { name: string; arguments: Record<string, unknown> } | undefined;
  const confidence = utteranceMut.data?.confidence ?? 0;
  const isOk = utteranceMut.data?.status === "ok" && confidence >= 0.80;

  const query = (call?.arguments.query as string | undefined)?.trim();
  const hasEvidence = Boolean(query && ingredients.join(",").toLowerCase().includes(query.toLowerCase()));
  const matchedIngredient = query ? ingredients.find((i) => i.toLowerCase().includes(query.toLowerCase())) : undefined;

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
    <div className="cook-mode-voice">
      <h2>{recipe.title}</h2>
      <p>
        Step {internalStep + 1} of {steps.length}
      </p>
      <p>{steps[internalStep] ?? "No step"}</p>

      {/* Manual step controls */}
      <div>
        <button
          type="button"
          aria-label="Previous step"
          disabled={internalStep === 0}
          onClick={() => setInternalStep((s) => Math.max(s - 1, 0))}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") {
              e.preventDefault();
              setInternalStep((s) => Math.max(s - 1, 0));
            }
          }}
        >
          Previous
        </button>
        <button
          type="button"
          aria-label="Next step"
          disabled={internalStep >= steps.length - 1}
          onClick={() => setInternalStep((s) => Math.min(s + 1, steps.length - 1))}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") {
              e.preventDefault();
              setInternalStep((s) => Math.min(s + 1, steps.length - 1));
            }
          }}
        >
          Next step
        </button>
      </div>

      {/* Voice entry — STT transcript=prompt hook (doc-only, voice button wires transcript to onUtterance) */}
      <div aria-label="Voice commands">
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

      {/* Timer chip — only when 0.80 gate + cooking_action timer + clamped 1..120 */}
      {showTimer && <TimerChip minutes={clampedMinutes!} />}

      {/* Query answer chip only when evidenced; fallback is repeat step text (already visible) */}
      {showAnswerChip && <AnswerChip>{matchedIngredient!}</AnswerChip>}
    </div>
  );
}

// Re-export for page usage
export default CookMode;
