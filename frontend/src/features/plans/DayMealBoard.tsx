import { DragDropProvider, DragOverlay, KeyboardSensor, PointerSensor, type DragEndEvent, type DragStartEvent, useDraggable, useDroppable } from "@dnd-kit/react";
import { GripVertical } from "lucide-react";
import { useState } from "react";

import { MealPlanEntry } from "./MealPlanEntry";
import type { MealPlanEntry as PlannedEntry, RecipePage } from "./types";
import { ConfirmDialog } from "../../components";

type Recipe = RecipePage["items"][number];
type MealDragData = { kind: "meal"; entry: PlannedEntry };
type SlotDropData = { kind: "slot"; slot: string };
type DaySlot = { slot: string; label: string; entries: PlannedEntry[] };

// JSDOM does not expose PointerEvent; keeping sensors empty there preserves a
// stable, testable static board while real browsers get pointer + keyboard drag.
const sensors = typeof window !== "undefined" && "PointerEvent" in window
  ? [PointerSensor.configure({ preventActivation: () => false }), KeyboardSensor]
  : [];

function DraggableDayEntry({ entry, weekStart, recipe, readOnly }: { entry: PlannedEntry; weekStart: string; recipe?: Recipe; readOnly: boolean }) {
  const { ref, isDragging } = useDraggable<MealDragData>({ id: `day-${entry.id}`, data: { kind: "meal", entry }, disabled: !entry.recipeId || readOnly });
  return <div ref={ref} className={`day-entry-drag${isDragging ? " is-dragging" : ""}`}><MealPlanEntry entry={entry} weekStart={weekStart} recipe={recipe} readOnly={readOnly} /></div>;
}

function DaySlot({ date, slot, weekStart, recipesById, readOnly, renderEmpty }: { date: string; slot: DaySlot; weekStart: string; recipesById: Map<string, Recipe>; readOnly: boolean; renderEmpty: (slot: string, readOnly: boolean) => React.ReactNode }) {
  const { ref, isDropTarget } = useDroppable<SlotDropData>({ id: `day-slot-${date}-${slot.slot}`, data: { kind: "slot", slot: slot.slot }, disabled: readOnly });
  return <section ref={ref} className={`meal-slot${isDropTarget ? " is-drop-target" : ""}`}><div className="section-heading"><h3>{slot.label}</h3><span>{slot.entries.length ? `${slot.entries.length} planned` : readOnly ? "Past" : "Open"}</span></div>{slot.entries.length ? <div className="entry-list">{slot.entries.map((entry) => <DraggableDayEntry key={entry.id} entry={entry} weekStart={weekStart} recipe={entry.recipeId ? recipesById.get(entry.recipeId) : undefined} readOnly={readOnly} />)}</div> : renderEmpty(slot.slot, readOnly)}</section>;
}

export function DayMealBoard({ date, slots, weekStart, recipesById, readOnly, onMove, onSwap, renderEmpty }: { date: string; slots: DaySlot[]; weekStart: string; recipesById: Map<string, Recipe>; readOnly: boolean; onMove: (entry: PlannedEntry, slot: string, position: number) => void; onSwap: (source: PlannedEntry, target: PlannedEntry) => void; renderEmpty: (slot: string, readOnly: boolean) => React.ReactNode }) {
  const [activeEntry, setActiveEntry] = useState<PlannedEntry | null>(null);
  const [swapCandidate, setSwapCandidate] = useState<{ source: PlannedEntry; target: PlannedEntry } | null>(null);
  const [announcement, setAnnouncement] = useState("");
  const allEntries = slots.flatMap((item) => item.entries);

  function dragStart(event: DragStartEvent) {
    const data = event.operation.source?.data as MealDragData | undefined;
    if (!data || data.kind !== "meal") return;
    setActiveEntry(data.entry);
    setAnnouncement(`Moving ${data.entry.recipeTitle}. Drop it on another meal slot to move it.`);
  }

  function dragEnd(event: DragEndEvent) {
    const source = event.operation.source?.data as MealDragData | undefined;
    const target = event.operation.target?.data as SlotDropData | undefined;
    setActiveEntry(null);
    if (event.canceled || !source || source.kind !== "meal" || !target || target.kind !== "slot") {
      setAnnouncement("Move cancelled. The meal stayed where it was.");
      return;
    }
    if (source.entry.mealSlot === target.slot) {
      setAnnouncement(`${source.entry.recipeTitle} stayed in ${target.slot}.`);
      return;
    }
    const destinationEntries = allEntries.filter((entry) => entry.id !== source.entry.id && entry.mealSlot === target.slot).sort((a, b) => a.position - b.position);
    const occupied = destinationEntries[0];
    if (occupied) {
      setSwapCandidate({ source: source.entry, target: occupied });
      setAnnouncement(`${source.entry.recipeTitle} would replace ${occupied.recipeTitle}. Confirm to swap their places.`);
      return;
    }
    onMove(source.entry, target.slot, destinationEntries.length);
    setAnnouncement(`${source.entry.recipeTitle} moved to ${target.slot}.`);
  }

  return <DragDropProvider sensors={sensors} onDragStart={dragStart} onDragEnd={dragEnd}>
    <div className="day-meal-board">
      {slots.map((slot) => <DaySlot key={slot.slot} date={date} slot={slot} weekStart={weekStart} recipesById={recipesById} readOnly={readOnly} renderEmpty={renderEmpty} />)}
    </div>
    <p className="visually-hidden" aria-live="assertive">{announcement}</p>
    <DragOverlay className="day-meal-overlay"><div>{activeEntry ? <><GripVertical aria-hidden="true" /><strong>{activeEntry.recipeTitle}</strong></> : null}</div></DragOverlay>
    {swapCandidate ? <ConfirmDialog open onOpenChange={(open) => { if (!open) setSwapCandidate(null); }} title="Swap these meals?" description={`${swapCandidate.source.recipeTitle} will take ${swapCandidate.target.recipeTitle}'s place, and ${swapCandidate.target.recipeTitle} will move back to ${swapCandidate.source.mealSlot}.`} confirmLabel="Swap meals" onConfirm={() => { onSwap(swapCandidate.source, swapCandidate.target); setSwapCandidate(null); }} /> : null}
  </DragDropProvider>;
}
