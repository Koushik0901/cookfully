import { DragDropProvider, DragOverlay, type DragEndEvent, type DragOverEvent, type DragStartEvent, useDraggable, useDroppable } from "@dnd-kit/react";
import { GripVertical, Move, Plus } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";

import { RecipeFallbackArt } from "../../components/cookfully/RecipeFallbackArt";
import { formatCookingNumber } from "../recipes/formatCooking";
import { RecipeMetadata } from "../recipes/RecipeMetadata";
import { longDate } from "./dates";
import { MoveMealSheet } from "./MoveMealSheet";
import type { MealPlanEntry, RecipePage } from "./types";

const SLOTS = ["breakfast", "lunch", "dinner", "snack"] as const;
type Recipe = RecipePage["items"][number];

type MealDragData = { kind: "meal"; entry: MealPlanEntry };
type SlotDropData = { kind: "slot"; date: string; slot: string };

function weekday(value: string, format: "long" | "short" = "long") {
  return new Intl.DateTimeFormat("en-CA", { weekday: format, timeZone: "UTC" }).format(new Date(`${value}T00:00:00Z`));
}

function DraggableWeekMeal({ entry, recipe, instructionsId, onMoveFallback }: { entry: MealPlanEntry; recipe?: Recipe; instructionsId: string; onMoveFallback: () => void }) {
  const { ref, handleRef, isDragging } = useDraggable<MealDragData>({ id: entry.id, data: { kind: "meal", entry }, disabled: !entry.recipeId });
  return (
    <article ref={ref} className={`week-meal${isDragging ? " is-dragging" : ""}`}>
      {entry.recipeId ? <Link className="week-meal__media" to={`/app/recipes/${entry.recipeId}`} aria-label={`Open ${entry.recipeTitle}`}>{recipe?.imageUrl ? <img src={recipe.imageUrl} alt="" loading="lazy" decoding="async" /> : <RecipeFallbackArt title={entry.recipeTitle} />}</Link> : <span className="week-meal__media"><RecipeFallbackArt title={entry.recipeTitle} /></span>}
      <div className="week-meal__copy"><strong>{entry.recipeTitle}</strong><span>{formatCookingNumber(entry.servings)} {Number(entry.servings) === 1 ? "serving" : "servings"}</span>{recipe ? <RecipeMetadata recipe={recipe} compact /> : null}</div>
      <div className="week-meal__actions">
        <button ref={handleRef} type="button" className="week-meal__drag" disabled={!entry.recipeId} aria-label={`Drag ${entry.recipeTitle}`} aria-describedby={instructionsId}><GripVertical aria-hidden="true" /></button>
        <button type="button" className="week-meal__move" disabled={!entry.recipeId} onClick={onMoveFallback} aria-label={`Move ${entry.recipeTitle}`}><Move aria-hidden="true" /></button>
      </div>
    </article>
  );
}

function WeekSlot({ date, slot, entries, recipesById, instructionsId, onAdd, onMoveFallback }: { date: string; slot: string; entries: MealPlanEntry[]; recipesById: Map<string, Recipe>; instructionsId: string; onAdd: () => void; onMoveFallback: (entry: MealPlanEntry) => void }) {
  const { ref, isDropTarget } = useDroppable<SlotDropData>({ id: `${date}:${slot}`, data: { kind: "slot", date, slot } });
  const label = slot[0].toUpperCase() + slot.slice(1);
  return (
    <section ref={ref} className={`week-slot${isDropTarget ? " is-drop-target" : ""}`} aria-label={`${label} on ${weekday(date)}`}>
      <header><span>{label}</span>{entries.length ? <small>{entries.length}</small> : null}</header>
      {entries.map((entry) => <DraggableWeekMeal key={entry.id} entry={entry} recipe={entry.recipeId ? recipesById.get(entry.recipeId) : undefined} instructionsId={instructionsId} onMoveFallback={() => onMoveFallback(entry)} />)}
      <button type="button" className="week-slot__add" onClick={onAdd} aria-label={`Add a recipe to ${label} on ${weekday(date)}`}><Plus aria-hidden="true" /><span>{entries.length ? "Add another" : "Add meal"}</span></button>
    </section>
  );
}

export function WeekOverview({
  dates,
  entries,
  recipesById,
  selectedDate,
  movePending,
  onOpenDay,
  onAdd,
  onMove,
}: {
  dates: string[];
  entries: MealPlanEntry[];
  recipesById: Map<string, Recipe>;
  selectedDate: string;
  movePending: boolean;
  onOpenDay: (date: string) => void;
  onAdd: (date: string, slot: string) => void;
  onMove: (entry: MealPlanEntry, date: string, slot: string, position: number) => void;
}) {
  const [activeEntry, setActiveEntry] = useState<MealPlanEntry | null>(null);
  const [moveEntry, setMoveEntry] = useState<MealPlanEntry | null>(null);
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
    const position = entries.filter((entry) => entry.id !== source.entry.id && entry.localDate === target.date && entry.mealSlot === target.slot).length;
    setAnnouncement(`${source.entry.recipeTitle} moved to ${target.slot} on ${weekday(target.date)}.`);
    onMove(source.entry, target.date, target.slot, position);
  }

  const fallbackMove = (entry: MealPlanEntry, date: string, slot: string) => {
    const position = entries.filter((item) => item.id !== entry.id && item.localDate === date && item.mealSlot === slot).length;
    onMove(entry, date, slot, position);
  };

  return (
    <section className="week-overview" aria-labelledby="week-overview-title">
      <header className="week-overview__heading">
        <div><p className="eyebrow">Week view</p><h2 id="week-overview-title">Place the meals that matter</h2></div>
        <p>{entries.length ? `${entries.length} meals across ${plannedDays} ${plannedDays === 1 ? "day" : "days"}. Drag a meal or use Move to change its place.` : "The week is open. Start with dinner or the busiest day."}</p>
      </header>
      <p id={instructionsId} className="visually-hidden">To move a planned meal with the keyboard, focus its drag button and press Space or Enter. Use arrow keys to choose a destination and press Space or Enter again. Press Escape to cancel. The Move button provides the same action without dragging.</p>
      <p className="visually-hidden" aria-live="assertive" aria-atomic="true">{announcement}</p>
      <DragDropProvider onDragStart={dragStart} onDragOver={dragOver} onDragEnd={dragEnd}>
        <div className="week-board" aria-label="Meals across the week">
          {dates.map((date) => (
            <article className={`week-day${date === selectedDate ? " week-day--selected" : ""}`} key={date}>
              <button className="week-day__header" onClick={() => onOpenDay(date)} aria-label={`Open day view for ${weekday(date)}, ${longDate(date)}`}>
                <span>{weekday(date, "short")}</span><strong>{longDate(date)}</strong>
              </button>
              <div className="week-day__slots">
                {SLOTS.map((slot) => <WeekSlot key={slot} date={date} slot={slot} entries={entries.filter((entry) => entry.localDate === date && entry.mealSlot === slot).sort((a, b) => a.position - b.position)} recipesById={recipesById} instructionsId={instructionsId} onAdd={() => onAdd(date, slot)} onMoveFallback={setMoveEntry} />)}
              </div>
            </article>
          ))}
        </div>
        <DragOverlay className="week-meal-overlay" dropAnimation={{ duration: 220, easing: "cubic-bezier(0.22, 1, 0.36, 1)" }}>
          {activeEntry ? <div><GripVertical aria-hidden="true" /><strong>{activeEntry.recipeTitle}</strong><span>{activeEntry.mealSlot}</span></div> : null}
        </DragOverlay>
      </DragDropProvider>
      <MoveMealSheet entry={moveEntry} dates={dates} open={Boolean(moveEntry)} pending={movePending} onOpenChange={(open) => { if (!open) setMoveEntry(null); }} onMove={(entry, date, slot) => { fallbackMove(entry, date, slot); setMoveEntry(null); }} />
    </section>
  );
}
