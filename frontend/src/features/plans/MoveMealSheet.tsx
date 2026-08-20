import * as Dialog from "@radix-ui/react-dialog";
import { Move, X } from "lucide-react";
import { useEffect, useState } from "react";

import { Button, Field, Select } from "../../components";
import { longDate } from "./dates";
import type { MealPlanEntry } from "./types";

const SLOTS = ["breakfast", "lunch", "dinner", "snack"] as const;

export function MoveMealSheet({
  entry,
  dates,
  open,
  pending,
  onOpenChange,
  onMove,
}: {
  entry: MealPlanEntry | null;
  dates: string[];
  open: boolean;
  pending: boolean;
  onOpenChange: (open: boolean) => void;
  onMove: (entry: MealPlanEntry, date: string, slot: string) => void;
}) {
  const [date, setDate] = useState(entry?.localDate ?? dates[0] ?? "");
  const [slot, setSlot] = useState(entry?.mealSlot ?? "dinner");

  useEffect(() => {
    if (!entry) return;
    setDate(entry.localDate);
    setSlot(entry.mealSlot);
  }, [entry]);

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="recipe-picker-overlay" />
        <Dialog.Content className="move-meal-sheet">
          <header>
            <div><p className="eyebrow">Move a meal</p><Dialog.Title>{entry?.recipeTitle ?? "Planned meal"}</Dialog.Title><Dialog.Description>Choose another day and meal. The nutrition snapshot moves with it.</Dialog.Description></div>
            <Dialog.Close className="recipe-picker__close" aria-label="Close move meal"><X aria-hidden="true" /></Dialog.Close>
          </header>
          <div className="move-meal-sheet__fields">
            <Field label="Day"><Select value={date} onChange={(event) => setDate(event.target.value)}>{dates.map((value) => <option key={value} value={value}>{longDate(value)}</option>)}</Select></Field>
            <Field label="Meal"><Select value={slot} onChange={(event) => setSlot(event.target.value)}>{SLOTS.map((value) => <option key={value} value={value}>{value[0].toUpperCase() + value.slice(1)}</option>)}</Select></Field>
          </div>
          <footer><Dialog.Close asChild><Button variant="secondary">Cancel</Button></Dialog.Close><Button disabled={!entry || !date || pending || (date === entry.localDate && slot === entry.mealSlot)} onClick={() => { if (entry) onMove(entry, date, slot); }}><Move aria-hidden="true" />{pending ? "Moving…" : "Move meal"}</Button></footer>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
