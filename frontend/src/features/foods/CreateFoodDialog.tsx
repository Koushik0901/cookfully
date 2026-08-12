import { useState } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import { useMutation } from "@tanstack/react-query";
import { Button, Field } from "../../components";
import { foodsApi } from "./api";
import type { OwnerFoodWrite } from "./types";

interface CreateFoodDialogProps {
  trigger: React.ReactNode;
  ingredientName: string;
  prefill?: { servingGrams?: number; servingUnit?: string };
  onCreated: (foodId: string) => void;
}

export function CreateFoodDialog({
  trigger,
  ingredientName,
  prefill,
  onCreated,
}: CreateFoodDialogProps) {
  const [open, setOpen] = useState(false);

  const [displayName, setDisplayName] = useState(ingredientName);
  const [brand, setBrand] = useState("");
  const [calories, setCalories] = useState("");
  const [protein, setProtein] = useState("");
  const [carbs, setCarbs] = useState("");
  const [fat, setFat] = useState("");
  const [basisGrams, setBasisGrams] = useState(
    prefill?.servingGrams ? String(prefill.servingGrams) : "100"
  );
  const [servingUnit, setServingUnit] = useState(prefill?.servingUnit ?? "");
  const [error, setError] = useState("");

  const create = useMutation({
    mutationFn: (write: OwnerFoodWrite) => foodsApi.createUserFood(write),
    onSuccess: (food) => {
      setOpen(false);
      onCreated(food.id);
      reset();
    },
    onError: (err: unknown) => {
      setError(err instanceof Error ? err.message : "Could not create food.");
    },
  });

  function reset() {
    setDisplayName(ingredientName);
    setBrand("");
    setCalories("");
    setProtein("");
    setCarbs("");
    setFat("");
    setBasisGrams(prefill?.servingGrams ? String(prefill.servingGrams) : "100");
    setServingUnit(prefill?.servingUnit ?? "");
    setError("");
  }

  function submit(e: React.FormEvent) {
    e.preventDefault();
    const cal = parseFloat(calories);
    const p = parseFloat(protein);
    const c = parseFloat(carbs);
    const f = parseFloat(fat);
    const basis = parseFloat(basisGrams) || 100;

    if (!displayName.trim()) {
      setError("Food name is required.");
      return;
    }
    if (isNaN(cal) || cal < 0 || isNaN(p) || p < 0 || isNaN(c) || c < 0 || isNaN(f) || f < 0) {
      setError("All macro values must be non-negative numbers.");
      return;
    }

    create.mutate({
      displayName: displayName.trim(),
      brand: brand.trim() || undefined,
      caloriesKcal: cal,
      proteinG: p,
      carbohydrateG: c,
      fatG: f,
      basisGrams: basis,
      typicalServingG: prefill?.servingGrams ?? undefined,
      typicalServingUnit: servingUnit.trim() || undefined,
    });
  }

  return (
    <Dialog.Root open={open} onOpenChange={(v) => { setOpen(v); if (!v) reset(); }}>
      <Dialog.Trigger asChild>{trigger}</Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Overlay className="dialog-overlay" />
        <Dialog.Content className="dialog" aria-describedby="create-food-desc">
          <Dialog.Title>Create your own food</Dialog.Title>
          <Dialog.Description id="create-food-desc">
            Enter the nutrition values from your product label.
          </Dialog.Description>

          <form className="stack" onSubmit={submit}>
            <Field label="Food name" error={error && !displayName.trim() ? error : undefined}>
              <input
                className="input"
                value={displayName}
                onChange={(e) => setDisplayName(e.target.value)}
                placeholder={ingredientName}
              />
            </Field>

            <Field label="Brand (optional)">
              <input
                className="input"
                value={brand}
                onChange={(e) => setBrand(e.target.value)}
                placeholder="e.g. Optimum Nutrition"
              />
            </Field>

            <Field label="Calories (kcal per serving)">
              <input
                className="input"
                type="number"
                inputMode="decimal"
                step="0.1"
                value={calories}
                onChange={(e) => setCalories(e.target.value)}
                placeholder="120"
              />
            </Field>

            <Field label="Protein (g per serving)">
              <input
                className="input"
                type="number"
                inputMode="decimal"
                step="0.1"
                value={protein}
                onChange={(e) => setProtein(e.target.value)}
                placeholder="25"
              />
            </Field>

            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "var(--space-sm)" }}>
              <Field label="Carbs (g)">
                <input
                  className="input"
                  type="number"
                  inputMode="decimal"
                  step="0.1"
                  value={carbs}
                  onChange={(e) => setCarbs(e.target.value)}
                  placeholder="3"
                />
              </Field>
              <Field label="Fat (g)">
                <input
                  className="input"
                  type="number"
                  inputMode="decimal"
                  step="0.1"
                  value={fat}
                  onChange={(e) => setFat(e.target.value)}
                  placeholder="1"
                />
              </Field>
            </div>

            <details className="disclosure">
              <summary>Serving size details</summary>
              <div className="stack" style={{ marginBlockStart: "var(--space-sm)" }}>
                <Field label="Grams per serving">
                  <input
                    className="input"
                    type="number"
                    inputMode="decimal"
                    step="0.1"
                    value={basisGrams}
                    onChange={(e) => setBasisGrams(e.target.value)}
                    placeholder="100"
                  />
                </Field>
                <Field label="Serving unit (optional)">
                  <input
                    className="input"
                    value={servingUnit}
                    onChange={(e) => setServingUnit(e.target.value)}
                    placeholder="scoop"
                  />
                </Field>
              </div>
            </details>

            {error && <p className="error-text">{error}</p>}

            <div className="actions">
              <Dialog.Close asChild>
                <Button type="button" className="button--secondary">Cancel</Button>
              </Dialog.Close>
              <Button type="submit" disabled={create.isPending}>
                {create.isPending ? "Saving\u2026" : "Create food"}
              </Button>
            </div>
          </form>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
