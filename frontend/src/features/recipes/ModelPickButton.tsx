import { useMutation } from "@tanstack/react-query";
import { Sparkles } from "lucide-react";

import { Button } from "../../components";
import { foodsApi } from "../foods/api";
import { formatProbability, type ModelPick } from "./matchReview";
import type { JobAccepted } from "./types";

interface ModelPickButtonProps {
  recipeId: string;
  ingredientId: string;
  pick: ModelPick;
  onSelected: (accepted: JobAccepted) => void;
}

/** One-tap confirmation of the decision models' suggestion; saved like a hand-picked food. */
export function ModelPickButton({ recipeId, ingredientId, pick, onSelected }: ModelPickButtonProps) {
  const choose = useMutation({
    mutationFn: () => foodsApi.selectIngredientFood(recipeId, ingredientId, pick.foodReferenceId, true),
    onSuccess: (accepted) => onSelected(accepted),
  });
  return (
    <span className="model-pick">
      <span className="model-pick__chip" title="Suggested by decision models; they do not give reasons.">
        <Sparkles aria-hidden="true" /> Model pick · {formatProbability(pick.probability)}
      </span>
      <span className="model-pick__food">{pick.description}</span>
      <Button
        type="button"
        size="sm"
        aria-label={`Use ${pick.description}`}
        onClick={() => choose.mutate()}
        disabled={choose.isPending}
      >
        {choose.isPending ? "Saving…" : "Use this"}
      </Button>
      {choose.error instanceof Error ? <span className="error-text" role="alert">{choose.error.message}</span> : null}
    </span>
  );
}
