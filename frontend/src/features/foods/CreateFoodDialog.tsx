import { useState } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import { useMutation } from "@tanstack/react-query";
import { Button, DialogCloseButton, Field } from "../../components";
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
    const basis = parseFloat(basisGrams);

    if (!displayName.trim()) {
      setError("Food name is required.");
      return;
    }
    if (isNaN(cal) || cal < 0 || isNaN(p) || p < 0 || isNaN(c) || c < 0 || isNaN(f) || f < 0) {
      setError("All macro values must be non-negative numbers.");
      return;
    }
    if (isNaN(basis) || basis <= 0) {
      setError("Label serving weight must be greater than zero.");
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
      typicalServingG: servingUnit.trim() ? basis : undefined,
      typicalServingUnit: servingUnit.trim() || undefined,
    });
  }

  return (
    <Dialog.Root open={open} onOpenChange={(v) => { setOpen(v); if (!v) reset(); }}>
      <Dialog.Trigger asChild>{trigger}</Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Overlay className="dialog-overlay" />
        <Dialog.Content className="dialog food-dialog" aria-describedby="create-food-desc">
          <header className="food-dialog__header">
            <div>
              <p className="eyebrow">From a product label</p>
              <Dialog.Title>Add a food you know</Dialog.Title>
              <Dialog.Description id="create-food-desc" className="food-dialog__description">
                Copy one serving from the package. Cookfully will keep these values together for future recipes.
              </Dialog.Description>
            </div>
            <DialogCloseButton label="Close add food dialog" />
          </header>

          <form className="food-dialog__form" onSubmit={submit}>
            <fieldset className="food-dialog__section">
              <legend><span>1</span>Identify the food</legend>
              <p>Use the name you expect to see in a recipe.</p>
              <div className="food-dialog__identity-grid">
                <Field label="Food name" error={error && !displayName.trim() ? error : undefined}>
                  <input className="input" value={displayName} onChange={(e) => setDisplayName(e.target.value)} placeholder={ingredientName || "Plain Greek yogurt"} autoFocus />
                </Field>
                <Field label="Brand (optional)">
                  <input className="input" value={brand} onChange={(e) => setBrand(e.target.value)} placeholder="Island Farms" />
                </Field>
              </div>
            </fieldset>

            <fieldset className="food-dialog__section food-dialog__section--label">
              <legend><span>2</span>Copy one label serving</legend>
              <p>Enter the four values shown for a single serving, then tell us how much that serving weighs.</p>
              <div className="food-dialog__macro-grid">
                <Field label="Calories"><input className="input" type="number" inputMode="decimal" min="0" step="0.1" value={calories} onChange={(e) => setCalories(e.target.value)} placeholder="120" /></Field>
                <Field label="Protein (g)"><input className="input" type="number" inputMode="decimal" min="0" step="0.1" value={protein} onChange={(e) => setProtein(e.target.value)} placeholder="25" /></Field>
                <Field label="Carbohydrate (g)"><input className="input" type="number" inputMode="decimal" min="0" step="0.1" value={carbs} onChange={(e) => setCarbs(e.target.value)} placeholder="3" /></Field>
                <Field label="Fat (g)"><input className="input" type="number" inputMode="decimal" min="0" step="0.1" value={fat} onChange={(e) => setFat(e.target.value)} placeholder="1" /></Field>
              </div>
              <div className="food-dialog__serving-grid">
                <Field label="Label serving weight" hint="The gram weight those nutrition values describe.">
                  <input className="input" type="number" inputMode="decimal" min="0.1" step="0.1" value={basisGrams} onChange={(e) => setBasisGrams(e.target.value)} placeholder="31" />
                </Field>
                <Field label="Serving name (optional)" hint="For example: scoop, bar, cup.">
                  <input className="input" value={servingUnit} onChange={(e) => setServingUnit(e.target.value)} placeholder="scoop" />
                </Field>
              </div>
            </fieldset>

            {error && <p className="error-text food-dialog__error" role="alert">{error}</p>}

            <div className="food-dialog__actions">
              <Dialog.Close asChild>
                <Button type="button" variant="secondary">Cancel</Button>
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
