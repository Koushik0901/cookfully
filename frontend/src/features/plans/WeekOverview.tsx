import { DragDropProvider, DragOverlay, KeyboardSensor, PointerSensor, type DragEndEvent, type DragOverEvent, type DragStartEvent, useDraggable, useDroppable } from "@dnd-kit/react";
import { Copy, GripVertical, Plus, X } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";

import { ConfirmDialog, RecipeMedia, SectionHeading } from "../../components";
import { RecipeFallbackArt } from "../../components/cookfully/RecipeFallbackArt";
import { formatCookingNumber } from "../recipes/formatCooking";
import { RecipeMetadata } from "../recipes/RecipeMetadata";
import { longDate } from "./dates";
import type { MealPlanEntry, RecipePage } from "./types";

const SLOTS = ["breakfast", "lunch", "dinner", "snack"] as const;
type Recipe = RecipePage["items"][number];

type MealDragData = { kind: "meal"; entry: MealPlanEntry };
type SlotDropData = { kind: "slot"; date: string; slot: string };
type CopyPlacement = { entry: MealPlanEntry };

const plannerSensors = [
  PointerSensor.configure({ preventActivation: () => false }),
  KeyboardSensor,
];

function weekday(value: string, format: "long" | "short" = "long") {
  return new Intl.DateTimeFormat("en-CA", { weekday: format, timeZone: "UTC" }).format(new Date(`${value}T00:00:00Z`));
}

function DraggableWeekMeal({ entry, recipe, onCopy, onDelete, pending, readOnly }: { entry: MealPlanEntry; recipe?: Recipe; onCopy: () => void; onDelete: () => void; pending: boolean; readOnly: boolean }) {
  const { ref, isDragging } = useDraggable<MealDragData>({ id: entry.id, data: { kind: "meal", entry }, disabled: !entry.recipeId || pending || readOnly });
  return (
    <article ref={ref} className={`week-meal${isDragging ? " is-dragging" : ""}`}>
      {entry.recipeId ? <Link className="week-meal__body" to={`/app/recipes/${entry.recipeId}`} aria-label={`Open ${entry.recipeTitle}`} draggable={false}><span className="week-meal__media">{recipe ? <RecipeMedia recipe={recipe} /> : <RecipeFallbackArt title={entry.recipeTitle} />}</span><div className="week-meal__copy"><strong>{entry.recipeTitle}</strong><span>{formatCookingNumber(entry.servings)} {Number(entry.servings) === 1 ? "serving" : "servings"}</span>{recipe ? <RecipeMetadata recipe={recipe} compact /> : null}</div></Link> : <div className="week-meal__body"><span className="week-meal__media"><RecipeFallbackArt title={entry.recipeTitle} /></span><div className="week-meal__copy"><strong>{entry.recipeTitle}</strong><span>{formatCookingNumber(entry.servings)} {Number(entry.servings) === 1 ? "serving" : "servings"}</span></div></div>}
      <div className="week-meal__actions">
        <button type="button" className="week-meal__copy-action" disabled={!entry.recipeId || pending || readOnly} onPointerDownCapture={(event) => event.stopPropagation()} onPointerDown={(event) => event.stopPropagation()} onClick={onCopy} aria-label={`Copy ${entry.recipeTitle}`} title="Copy meal"><Copy aria-hidden="true" /></button>
        <button type="button" className="week-meal__delete" disabled={pending || readOnly} onPointerDownCapture={(event) => event.stopPropagation()} onPointerDown={(event) => event.stopPropagation()} onClick={onDelete} aria-label={`Delete ${entry.recipeTitle}`} title="Delete meal"><X aria-hidden="true" /></button>
      </div>
    </article>
  );
}

function WeekSlot({ date, slot, entries, recipesById, onAdd, copyPlacement, pending, onPlace, onStartCopy, onDelete, readOnly }: { date: string; slot: string; entries: MealPlanEntry[]; recipesById: Map<string, Recipe>; onAdd: () => void; copyPlacement: CopyPlacement | null; pending: boolean; onPlace: (date: string, slot: string) => void; onStartCopy: (entry: MealPlanEntry) => void; onDelete: (entry: MealPlanEntry) => void; readOnly: boolean }) {
  const { ref, isDropTarget } = useDroppable<SlotDropData>({ id: `${date}:${slot}`, data: { kind: "slot", date, slot }, disabled: readOnly });
  const label = slot[0].toUpperCase() + slot.slice(1);
  const sameSpot = copyPlacement?.entry.localDate === date && copyPlacement.entry.mealSlot === slot;
  const placementLabel = copyPlacement ? `Copy ${copyPlacement.entry.recipeTitle} to ${label} on ${weekday(date)}` : "";
  return (
    <section ref={ref} className={`week-slot${isDropTarget ? " is-drop-target" : ""}${copyPlacement && !readOnly ? " week-slot--placement-target" : ""}${readOnly ? " week-slot--past" : ""}`} aria-label={`${label} on ${weekday(date)}${readOnly ? " (past)" : ""}${copyPlacement && !readOnly ? ` — ${placementLabel}` : ""}`}>
      <header><span>{label}</span>{entries.length ? <small>{entries.length}</small> : null}</header>
      {entries.map((entry) => <DraggableWeekMeal key={entry.id} entry={entry} recipe={entry.recipeId ? recipesById.get(entry.recipeId) : undefined} pending={pending} readOnly={readOnly} onCopy={() => onStartCopy(entry)} onDelete={() => onDelete(entry)} />)}
      {readOnly ? <div className="week-slot__past" aria-label={`${label} on ${weekday(date)} is in the past`}>Past</div> : copyPlacement ? <button type="button" className="week-slot__placement" onClick={() => onPlace(date, slot)} disabled={sameSpot || pending} aria-label={placementLabel}><span>{sameSpot ? "Current spot" : "Copy here"}</span><strong>{label}</strong></button> : <button type="button" className="week-slot__add" onClick={onAdd} aria-label={`Add a recipe to ${label} on ${weekday(date)}`}><Plus aria-hidden="true" /><span>{entries.length ? "Add another" : "Add meal"}</span></button>}
    </section>
  );
}

export function WeekOverview({
  dates,
  entries,
  recipesById,
  selectedDate,
  today,
  copyPending,
  swapPending,
  deletePending,
  onOpenDay,
  onAdd,
  onMove,
  onCopy,
  onSwap,
  onDelete,
}: {
  dates: string[];
  entries: MealPlanEntry[];
  recipesById: Map<string, Recipe>;
  selectedDate: string;
  today: string;
  copyPending: boolean;
  swapPending: boolean;
  deletePending: boolean;
  onOpenDay: (date: string) => void;
  onAdd: (date: string, slot: string) => void;
  onMove: (entry: MealPlanEntry, date: string, slot: string, position: number) => void;
  onCopy: (entry: MealPlanEntry, date: string, slot: string, position: number) => void;
  onSwap: (source: MealPlanEntry, target: MealPlanEntry) => void;
  onDelete: (entry: MealPlanEntry) => void;
}) {
  const [activeEntry, setActiveEntry] = useState<MealPlanEntry | null>(null);
  const [copyPlacement, setCopyPlacement] = useState<CopyPlacement | null>(null);
  const [swapCandidate, setSwapCandidate] = useState<{ source: MealPlanEntry; target: MealPlanEntry } | null>(null);
  const [deleteCandidate, setDeleteCandidate] = useState<MealPlanEntry | null>(null);
  const [announcement, setAnnouncement] = useState("");
  const instructionsId = "planner-drag-instructions";
  const plannedDays = new Set(entries.map((entry) => entry.localDate)).size;

  function dragStart(event: DragStartEvent) {
    const data = event.operation.source?.data as MealDragData | undefined;
    if (!data || data.kind !== "meal") return;
    setActiveEntry(data.entry);
    setAnnouncement(`Moving ${data.entry.recipeTitle}. Use the arrow keys to choose another meal slot, then press Space or Enter to drop.`);
  }

  function dragOver(event: DragOverEvent) {
    const data = event.operation.target?.data as SlotDropData | undefined;
    if (!data || data.kind !== "slot" || !activeEntry) return;
    setAnnouncement(`${activeEntry.recipeTitle} over ${data.slot} on ${weekday(data.date)}.`);
  }

  function dragEnd(event: DragEndEvent) {
    const source = event.operation.source?.data as MealDragData | undefined;
    const target = event.operation.target?.data as SlotDropData | undefined;
    setActiveEntry(null);
    if (event.canceled || !source || source.kind !== "meal" || !target || target.kind !== "slot") {
      setAnnouncement("Move cancelled. The meal stayed where it was.");
      return;
    }
    if (source.entry.localDate === target.date && source.entry.mealSlot === target.slot) {
      setAnnouncement(`${source.entry.recipeTitle} stayed in ${target.slot} on ${weekday(target.date)}.`);
      return;
    }
    const destinationEntries = entries.filter((entry) => entry.id !== source.entry.id && entry.localDate === target.date && entry.mealSlot === target.slot).sort((a, b) => a.position - b.position);
    const occupied = destinationEntries[0];
    if (occupied) {
      setSwapCandidate({ source: source.entry, target: occupied });
      setAnnouncement(`${source.entry.recipeTitle} would replace ${occupied.recipeTitle}. Confirm to swap their places.`);
      return;
    }
    const position = destinationEntries.length;
    setAnnouncement(`${source.entry.recipeTitle} moved to ${target.slot} on ${weekday(target.date)}.`);
    onMove(source.entry, target.date, target.slot, position);
  }

  const placeCopy = (date: string, slot: string) => {
    if (!copyPlacement) return;
    const position = entries.filter((item) => item.localDate === date && item.mealSlot === slot).length;
    setAnnouncement(`${copyPlacement.entry.recipeTitle} copied to ${slot} on ${weekday(date)}.`);
    onCopy(copyPlacement.entry, date, slot, position);
    setCopyPlacement(null);
  };

  return (
    <section className={`week-overview${activeEntry ? " week-overview--dragging" : ""}`} aria-labelledby="week-overview-title">
      <SectionHeading
        id="week-overview-title"
        eyebrow="Week view"
        title="Your week at a glance"
        description={entries.length ? `${entries.length} meals planned across ${plannedDays} ${plannedDays === 1 ? "day" : "days"}. Drag a meal anywhere on the board to rearrange it.` : "The week is open. Start with dinner or the busiest day."}
      />
      <p id={instructionsId} className="visually-hidden">Drag a planned meal card to another day and meal slot to move it. The Copy action creates a second instance without changing the original.</p>
      <p className="visually-hidden" aria-live="assertive" aria-atomic="true">{announcement}</p>
      {swapCandidate ? <div className="week-replace-bar" role="alert"><div><strong>Swap these meals?</strong><span>{swapCandidate.source.recipeTitle} will take {swapCandidate.target.recipeTitle}&apos;s place, and {swapCandidate.target.recipeTitle} will move back to {weekday(swapCandidate.source.localDate)} {swapCandidate.source.mealSlot}.</span></div><div className="week-replace-bar__actions"><button type="button" className="cf-button cf-button--secondary cf-button--sm" onClick={() => setSwapCandidate(null)} disabled={swapPending}>Keep as is</button><button type="button" className="cf-button cf-button--primary cf-button--sm" onClick={() => { onSwap(swapCandidate.source, swapCandidate.target); setSwapCandidate(null); }} disabled={swapPending}>{swapPending ? "Swapping…" : "Swap meals"}</button></div></div> : null}
      {copyPlacement ? <div className="week-placement-bar" role="status"><span className="week-placement-bar__icon"><Copy aria-hidden="true" /></span><div><strong>Copy {copyPlacement.entry.recipeTitle}</strong><span>Choose another day and meal. The original will stay where it is.</span></div><button type="button" onClick={() => setCopyPlacement(null)} aria-label={`Cancel copy ${copyPlacement.entry.recipeTitle}`}><X aria-hidden="true" /><span>Cancel</span></button></div> : null}
      <DragDropProvider sensors={plannerSensors} onDragStart={dragStart} onDragOver={dragOver} onDragEnd={dragEnd}>
        <div className="week-board" aria-label="Meals across the week">
          {dates.map((date) => {
            const dayEntries = entries.filter((entry) => entry.localDate === date);
            const readOnly = date < today;
            return (
            <article className={`week-day${date === selectedDate ? " week-day--selected" : ""}${readOnly ? " week-day--past" : ""}`} key={date}>
              <button className="week-day__header" onClick={() => onOpenDay(date)} aria-label={`Open day view for ${weekday(date)}, ${longDate(date)}`}>
                <span className="week-day__date"><span>{weekday(date, "short")}</span><strong>{longDate(date)}</strong></span>
                <small>{readOnly ? "Past" : dayEntries.length ? `${dayEntries.length} ${dayEntries.length === 1 ? "meal" : "meals"}` : "Open"}</small>
              </button>
              <div className="week-day__slots">
                {SLOTS.map((slot) => <WeekSlot key={slot} date={date} slot={slot} entries={dayEntries.filter((entry) => entry.mealSlot === slot).sort((a, b) => a.position - b.position)} recipesById={recipesById} onAdd={() => onAdd(date, slot)} copyPlacement={copyPlacement} pending={copyPending || deletePending} onPlace={placeCopy} onStartCopy={(entry) => setCopyPlacement({ entry })} onDelete={(entry) => setDeleteCandidate(entry)} readOnly={readOnly} />)}
              </div>
            </article>
            );
          })}
        </div>
        <DragOverlay className="week-meal-overlay" dropAnimation={{ duration: 220, easing: "cubic-bezier(0.22, 1, 0.36, 1)" }}>
          {activeEntry ? <div><GripVertical aria-hidden="true" /><strong>{activeEntry.recipeTitle}</strong><span>{activeEntry.mealSlot}</span></div> : null}
        </DragOverlay>
      </DragDropProvider>
      {deleteCandidate ? <ConfirmDialog open onOpenChange={(open) => { if (!open) setDeleteCandidate(null); }} title={`Remove ${deleteCandidate.recipeTitle} from your plan?`} description="This also marks the grocery list for refresh. The meal will be removed from its current day." confirmLabel="Remove meal" onConfirm={() => { onDelete(deleteCandidate); setDeleteCandidate(null); }} /> : null}
    </section>
  );
}
