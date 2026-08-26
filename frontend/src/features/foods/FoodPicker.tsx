import { useEffect, useState } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button, DialogCloseButton, SearchField } from "../../components";
import { Checkbox } from "@/components/ui/checkbox";
import { foodsApi } from "./api";
import { invalidateFoodChoiceQueries } from "./foodChoiceQueries";
import { CreateFoodDialog } from "./CreateFoodDialog";
import { FoodRow } from "./FoodCandidateRow";
import type { FoodCandidate, OwnerFood } from "./types";
import type { JobAccepted } from "../recipes/types";

interface FoodPickerProps {
  trigger: React.ReactNode;
  recipeId: string;
  ingredientId: string;
  ingredientName: string;
  onSelected: (accepted: JobAccepted) => void;
}

export function FoodPicker({
  trigger,
  recipeId,
  ingredientId,
  ingredientName,
  onSelected,
}: FoodPickerProps) {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [rememberMatch, setRememberMatch] = useState(true);
  const [searchValue, setSearchValue] = useState("");
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedFoodDescription, setSelectedFoodDescription] = useState<string | null>(null);

  useEffect(() => {
    const handle = window.setTimeout(() => setSearchQuery(searchValue.trim()), 220);
    return () => window.clearTimeout(handle);
  }, [searchValue]);

  useEffect(() => {
    if (!open) {
      setSearchValue("");
      setSearchQuery("");
      setSelectedFoodDescription(null);
    }
  }, [open]);

  const candidates = useQuery({
    queryKey: searchQuery
      ? ["ingredient-candidates", recipeId, ingredientId, searchQuery]
      : ["ingredient-candidates", recipeId, ingredientId],
    queryFn: () => foodsApi.ingredientCandidates(recipeId, ingredientId, searchQuery),
    enabled: open,
    staleTime: 60_000,
  });
  const selectFood = useMutation({
    mutationFn: (candidate: FoodCandidate) => candidate.source === "owner"
      ? foodsApi.selectOwnerFood(recipeId, ingredientId, candidate.id, rememberMatch)
      : foodsApi.selectIngredientFood(recipeId, ingredientId, candidate.id, rememberMatch),
    onMutate: (candidate) => {
      setSelectedFoodDescription(candidate.description);
    },
    onSuccess: (accepted) => {
      setOpen(false);
      void invalidateFoodChoiceQueries(queryClient);
      onSelected(accepted);
    },
    onError: () => {
      setSelectedFoodDescription(null);
    },
  });

  return (
    <Dialog.Root open={open} onOpenChange={setOpen}>
      <Dialog.Trigger asChild>{trigger}</Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Overlay className="dialog-overlay" />
        <Dialog.Content className="dialog food-picker-dialog" aria-describedby="food-picker-desc" aria-busy={selectFood.isPending}>
          <header className="food-picker__header">
            <div>
              <p className="eyebrow">Nutrition reference</p>
              <Dialog.Title>Match &ldquo;{ingredientName}&rdquo;</Dialog.Title>
              <Dialog.Description id="food-picker-desc">
                Choose the food this ingredient represents. The choice can update similar ingredients across your kitchen.
              </Dialog.Description>
            </div>
            <DialogCloseButton label="Close food matching dialog" />
          </header>

          <SearchField
            label="Search foods"
            value={searchValue}
            onChange={(event) => setSearchValue(event.currentTarget.value)}
            onClear={() => setSearchValue("")}
            placeholder="Search foods by name"
            autoFocus
          />

          <div className="food-picker__results-heading">
            <strong>{searchQuery ? `Results for “${searchQuery}”` : "Best matches"}</strong>
            <span>Showing up to 5</span>
          </div>

          {candidates.isError && (
            <p className="error-text">Could not load candidates. Try again.</p>
          )}

          {candidates.isLoading ? <p className="muted food-picker__loading">Searching foods…</p> : null}

          {selectFood.isPending ? (
            <p className="food-picker__applying" role="status">
              Applying “{selectedFoodDescription ?? "this match"}”…
            </p>
          ) : null}

          {candidates.data && candidates.data.candidates.length > 0 && (
            <ul className="food-candidate-list">
              {candidates.data.candidates.slice(0, 5).map((cand) => (
                <li key={`${cand.source}:${cand.id}`}>
                  <button
                    type="button"
                    className="food-candidate-button"
                    onClick={() => selectFood.mutate(cand)}
                    disabled={selectFood.isPending}
                  >
                    <FoodRow candidate={cand} />
                  </button>
                </li>
              ))}
            </ul>
          )}

          {!candidates.isLoading && candidates.data && candidates.data.candidates.length === 0 ? (
            <div className="food-picker__empty">
              <strong>No foods found</strong>
              <span>Try a broader search, or add this food from its package label.</span>
            </div>
          ) : null}

          {candidates.data && candidates.data.candidates.some((candidate) => candidate.compatibility === "review") ? (
            <p className="muted">Some results are compatible estimates and still need your review.</p>
          ) : null}

          {selectFood.error instanceof Error ? (
            <p className="error-text" role="alert">{selectFood.error.message}</p>
          ) : null}

          <div className="food-picker__create">
            <div>
              <strong>Not seeing the right food?</strong>
              <span>Create a reusable custom food from a label.</span>
            </div>
            <CreateFoodDialog
              ingredientName={searchValue.trim() || searchQuery || ingredientName}
              trigger={
                <Button variant="secondary" size="sm">Create custom food</Button>
              }
              onCreated={(food: OwnerFood) => {
                selectFood.mutate({
                  source: "owner",
                  id: food.id,
                  description: food.displayName,
                  brandOwner: food.brand,
                  servingSizeG: food.typicalServingG,
                  servingUnit: food.typicalServingUnit,
                });
              }}
            />
          </div>

          <div className="food-picker__footer">
          <label className="checkbox-row">
              <Checkbox checked={rememberMatch} onCheckedChange={(checked) => setRememberMatch(checked === true)} />
              Use this choice for similar ingredients everywhere
            </label>
            <Dialog.Close asChild><Button variant="ghost" disabled={selectFood.isPending}>Cancel</Button></Dialog.Close>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
