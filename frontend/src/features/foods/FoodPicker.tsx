import { useState } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import { useQuery } from "@tanstack/react-query";
import { Button } from "../../components";
import { foodsApi } from "./api";
import { CreateFoodDialog } from "./CreateFoodDialog";
import type { FoodCandidate } from "./types";

interface FoodPickerProps {
  trigger: React.ReactNode;
  recipeId: string;
  ingredientId: string;
  ingredientName: string;
  onSelected: () => void;
}

export function FoodPicker({
  trigger,
  recipeId,
  ingredientId,
  ingredientName,
  onSelected,
}: FoodPickerProps) {
  const [open, setOpen] = useState(false);

  const candidates = useQuery({
    queryKey: ["ingredient-candidates", recipeId, ingredientId],
    queryFn: () => foodsApi.ingredientCandidates(recipeId, ingredientId),
    enabled: open,
    staleTime: 60_000,
  });

  return (
    <Dialog.Root open={open} onOpenChange={setOpen}>
      <Dialog.Trigger asChild>{trigger}</Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Overlay className="dialog-overlay" />
        <Dialog.Content className="dialog" aria-describedby="food-picker-desc">
          <Dialog.Title>Match &ldquo;{ingredientName}&rdquo;</Dialog.Title>
          <Dialog.Description id="food-picker-desc">
            {candidates.isLoading
              ? "Searching reference foods\u2026"
              : candidates.data?.candidates.length
                ? "Select the best nutrition reference for this ingredient."
                : "No matches found. You can create your own food with nutrition data from your label."
            }
          </Dialog.Description>

          {candidates.isError && (
            <p className="error-text">Could not load candidates. Try again.</p>
          )}

          {candidates.data && candidates.data.candidates.length > 0 && (
            <ul className="food-candidate-list">
              {candidates.data.candidates.map((cand) => (
                <li key={`${cand.source}:${cand.id}`}>
                  <FoodRow candidate={cand} />
                </li>
              ))}
            </ul>
          )}

          <div className="actions">
            <Dialog.Close asChild>
              <Button className="button--secondary">Cancel</Button>
            </Dialog.Close>
            <CreateFoodDialog
              ingredientName={ingredientName}
              trigger={
                <Button className="button--text">Create your own</Button>
              }
              onCreated={() => {
                onSelected();
                setOpen(false);
              }}
            />
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

function FoodRow({ candidate }: { candidate: FoodCandidate }) {
  const brand = candidate.brandOwner;
  const source = candidate.source === "owner" ? "Yours" : "USDA";
  const serving = candidate.servingSizeG
    ? `${candidate.servingSizeG}g${candidate.servingUnit ? ` (${candidate.servingUnit})` : ""}`
    : null;

  return (
    <span className="food-candidate-row">
      <span className="food-candidate-name">
        <strong>{candidate.description}</strong>
        {brand && <span className="muted"> &mdash; {brand}</span>}
      </span>
      <span className="food-candidate-meta">
        <span className="food-candidate-source">{source}</span>
        {serving && <span className="muted">{serving}</span>}
      </span>
    </span>
  );
}
