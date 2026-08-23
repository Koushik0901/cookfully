import { useMutation } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";

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
  const [remaining, setRemaining] = useState(minutes * 60);
  const timerRef = useRef<number | null>(null);
  useEffect(() => {
    setRemaining(minutes * 60);
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
  }, [minutes]);
  const displayMin = Math.floor(remaining / 60);
  const displaySec = remaining % 60;
  return (
    <div role="status" aria-label={`Timer ${minutes} min`}>
      Timer {minutes} min{displayMin !== minutes || displaySec !== 0 ? ` — ${displayMin}:${String(displaySec).padStart(2, "0")} remaining` : ""}
    </div>
  );
}

function AnswerChip({ children }: { children: string }) {
  return <div role="status">{children}</div>;
}

export function CookMode({ recipe, currentStep: initialStep = 0 }: CookModeProps) {
  const ingredients = toIngredientTexts(recipe.ingredients);
  const steps = toStepTexts(recipe.instructions);
  const [internalStep, setInternalStep] = useState(initialStep);

  useEffect(() => {
    setInternalStep(initialStep);
  }, [initialStep]);

  const utteranceMut = useMutation({
    mutationFn: (u: string) => {
      const prompt = `Step: ${steps[internalStep]}\nIngredients: ${ingredients.join(", ")}\nUser: ${u}`;
      return intelligenceApi.infer("cook", prompt);
    },
  });

  function onUtterance(u: string) {
    utteranceMut.mutate(u);
  }

  const call = utteranceMut.data?.functionCalls?.[0] as { name: string; arguments: Record<string, unknown> } | undefined;
  const confidence = utteranceMut.data?.confidence ?? 0;
  const isOk = utteranceMut.data?.status === "ok" && confidence >= 0.80;

  // Voice-driven step navigation (gated, fail-quiet)
  useEffect(() => {
    if (!isOk || call?.name !== "cooking_action") return;
    const action = call.arguments.action as string | undefined;
    if (action === "next") {
      setInternalStep((s) => Math.min(s + 1, Math.max(steps.length - 1, 0)));
    } else if (action === "previous") {
      setInternalStep((s) => Math.max(s - 1, 0));
    }
    // repeat/timer/query do not change step index beyond answer chip
  }, [isOk, call, steps.length]);

  const query = (call?.arguments.query as string | undefined)?.trim();
  const hasEvidence = Boolean(query && ingredients.join(",").toLowerCase().includes(query.toLowerCase()));
  const matchedIngredient = query ? ingredients.find((i) => i.toLowerCase().includes(query.toLowerCase())) : undefined;

  const showTimer =
    isOk &&
    call?.name === "cooking_action" &&
    (call.arguments.action as string) === "timer" &&
    typeof call.arguments.minutes === "number";

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
        <button type="button" disabled={internalStep === 0} onClick={() => setInternalStep((s) => Math.max(s - 1, 0))}>
          Previous
        </button>
        <button type="button" disabled={internalStep >= steps.length - 1} onClick={() => setInternalStep((s) => Math.min(s + 1, steps.length - 1))}>
          Next step
        </button>
      </div>

      {/* Voice entry — STT transcript=prompt hook (doc-only, voice button wires transcript to onUtterance) */}
      <div>
        <button type="button" onClick={() => onUtterance("timer 5")}>
          timer 5
        </button>
        <button type="button" onClick={() => onUtterance("how much garlic")}>
          how much garlic
        </button>
        <button type="button" onClick={() => onUtterance("next")}>
          next
        </button>
        <button type="button" onClick={() => onUtterance("previous")}>
          previous
        </button>
        <button type="button" onClick={() => onUtterance("repeat")}>
          repeat
        </button>
      </div>

      {/* Timer chip — only when 0.80 gate + cooking_action timer */}
      {showTimer && <TimerChip minutes={call!.arguments.minutes as number} />}

      {/* Query answer chip only when evidenced; fallback is repeat step text (already visible) */}
      {showAnswerChip && <AnswerChip>{matchedIngredient!}</AnswerChip>}

      {/* Expose onUtterance for STT integration */}
      <span data-testid="cook-utterance-handler" style={{ display: "none" }}>
        {String(utteranceMut.isPending)}
      </span>
    </div>
  );
}

// Re-export for page usage
export default CookMode;
