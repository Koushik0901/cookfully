import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import * as Dialog from "@radix-ui/react-dialog";
import { type FormEvent, useEffect, useRef, useState } from "react";
import { CalendarDays, ChevronDown, ListPlus, MoreHorizontal, PackageCheck, Plus, RefreshCw, ShoppingBasket, X } from "lucide-react";
import { Link, useSearchParams } from "react-router-dom";

import { Button, ConfirmDialog, DecimalInput, DialogCloseButton, EmptyState, ErrorRecovery, Field, KitchenCompanion, PageHeader, PageState, Select, Skeleton } from "../../components";
import { FoodCategoryIcon } from "../../components/FoodCategoryIcon";
import { Checkbox } from "@/components/ui/checkbox";
import { pantryApi } from "../pantry/api";
import { expiryBadge } from "../pantry/expiry";
import type { PantryDeduction } from "../pantry/types";
import { planningApi } from "../plans/api";
import { addDays, longDate, todayInTimezone, weekStartFor } from "../plans/dates";
import { ApiProblem } from "../recipes/api";
import { formatCookingInput, formatCookingNumber } from "../recipes/formatCooking";
import { groceryApi } from "./api";
import { ShoppingStopManager } from "./ShoppingStopManager";
import type { GroceryItem, GroceryItemCreate, GroceryItemWrite, GroceryList, GroceryShoppingStop } from "./types";
import { AISLE_LABELS } from "./aisles";
import { GroceryTidyLine } from "./GroceryTidyLine";

type SourceMeal = { recipeId: string | null; recipeTitle: string };

/** Mobile is a distinct shopping mode: rows are check-off first and edit in a sheet. */
function useMobileLayout() {
  const [isMobile, setIsMobile] = useState(() => typeof window !== "undefined" && typeof window.matchMedia === "function" && window.matchMedia("(max-width: 767.98px)").matches);
  useEffect(() => {
    if (typeof window.matchMedia !== "function") return;
    const media = window.matchMedia("(max-width: 767.98px)");
    const update = () => setIsMobile(media.matches);
    update();
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, []);
  return isMobile;
}

export function GroceryRow({ item, weekStart, stops, readOnly, sourceMealsByEntry, today: todayProp }: { item: GroceryItem; weekStart: string; stops: GroceryShoppingStop[]; readOnly: boolean; sourceMealsByEntry: Map<string, SourceMeal>; today?: string }) {
  const queryClient = useQueryClient();
  const title = item.displayName ?? "Unnamed grocery item";
  const [name, setName] = useState(title);
  const [quantity, setQuantity] = useState(formatCookingInput(item.quantity));
  const [unit, setUnit] = useState(item.unit ?? "");
  const [checked, setChecked] = useState(item.checked ?? false);
  const isMobile = useMobileLayout();
  const [mobileEditOpen, setMobileEditOpen] = useState(false);
  useEffect(() => setChecked(item.checked ?? false), [item.checked]);
  const refresh = () => queryClient.invalidateQueries({ queryKey: ["grocery-list", weekStart] });
  const fallbackToday = todayInTimezone(Intl.DateTimeFormat().resolvedOptions().timeZone);
  const today = todayProp ?? fallbackToday;
  const plus90 = addDays(today, 90);
  const [showExpirySheet, setShowExpirySheet] = useState(false);
  const [draftExpiresOn, setDraftExpiresOn] = useState(item.expiresOn ?? "");
  useEffect(() => setDraftExpiresOn(item.expiresOn ?? ""), [item.expiresOn]);
  useEffect(() => {
    if (item.needsExpiryDate) setShowExpirySheet(true);
  }, [item.needsExpiryDate]);
  const badge = item.expiresOn ? expiryBadge(item.expiresOn, today) : null;
  const keepSeparate = useMutation({
    mutationFn: () => groceryApi.keepSeparate(item.id),
    onSuccess: async () => { await queryClient.invalidateQueries({ queryKey: ["grocery-list", weekStart] }); },
  });
  const update = useMutation({
    mutationFn: (value: GroceryItemWrite) => groceryApi.update(item.id, item.version, value),
    // A refetch started by an earlier edit must not land after this one and
    // undo it (e.g. ticking an item right after moving it to a stop).
    onMutate: () => queryClient.cancelQueries({ queryKey: ["grocery-list", weekStart] }),
    onSuccess: (saved, value) => {
      if (value.displayName != null) setName(value.displayName);
      if ("quantity" in value) setQuantity(formatCookingInput(value.quantity));
      if ("unit" in value) setUnit(value.unit ?? "");
      queryClient.setQueryData<GroceryList>(["grocery-list", weekStart], (current) => current
        ? { ...current, items: current.items.map((candidate) => candidate.id === item.id ? saved : candidate) }
        : current);
      if ((saved as GroceryItem).needsExpiryDate) setShowExpirySheet(true);
      if ((saved as GroceryItem).expiresOn) {
        setDraftExpiresOn((saved as GroceryItem).expiresOn ?? "");
        // keep sheet closed after successful save unless needsExpiryDate still true
        if (!(saved as GroceryItem).needsExpiryDate) setShowExpirySheet(false);
      }
      void refresh();
    },
  });
  const remove = useMutation({
    mutationFn: () => groceryApi.remove(item.id, item.version),
    onSuccess: () => {
      queryClient.setQueryData<GroceryList>(["grocery-list", weekStart], (current) => current
        ? { ...current, items: current.items.filter((candidate) => candidate.id !== item.id) }
        : current);
      void refresh();
    },
  });
  const error = update.error ?? remove.error;
  const conflict = error instanceof ApiProblem && error.status === 409;
  const sourceMeals = Array.from(new Map(item.sources
    .map((source) => sourceMealsByEntry.get(source.mealPlanEntryId))
    .filter((meal): meal is SourceMeal => Boolean(meal))
    .map((meal) => [`${meal.recipeId ?? "title"}:${meal.recipeTitle}`, meal]))
    .values());

  function save(event: FormEvent) {
    event.preventDefault();
    update.mutate({ displayName: name, quantity: quantity || null, unit: unit || null });
  }

  const checkOff = (value: boolean | "indeterminate") => {
    if (readOnly || update.isPending || remove.isPending) return;
    const next = value === true;
    setChecked(next);
    update.mutate({ checked: next }, { onError: () => setChecked(!next) });
  };

  const quantityLabel = item.quantity ? `${formatCookingNumber(item.quantity)}${item.unit ? ` ${item.unit}` : ""}` : item.unit ?? "As needed";
  const itemDetail = <>
    <h3>{title}</h3>
    <p className="grocery-item__amount data-value">{quantityLabel}{badge ? <button type="button" aria-label={`Expires ${item.expiresOn}`} className={`expiry-badge expiry-badge--${badge.tone}`} onClick={() => setShowExpirySheet(true)}>{badge.label}</button> : null}</p>
    {sourceMeals.length
      ? <p className="grocery-item__uses"><span>For</span>{sourceMeals.map((meal) => meal.recipeId ? <Link key={`${meal.recipeId}-${meal.recipeTitle}`} to={`/app/recipes/${meal.recipeId}`}>{meal.recipeTitle}</Link> : <span key={meal.recipeTitle}>{meal.recipeTitle}</span>)}</p>
      : item.sources.length ? <p className="grocery-item__uses"><span>For planned meals</span></p> : <p className="grocery-item__uses"><span>Added by you</span></p>}
    {item.needsReview ? <span className="review-badge grocery-item__review" title="Check this item's quantity or recipe sources">Check item</span> : null}
    <GroceryTidyLine item={item} title={title} readOnly={readOnly} busy={update.isPending} onStaple={(likelyStaple) => update.mutate({ likelyStaple })} onKeepSeparate={() => keepSeparate.mutate()} />
  </>;
  const checkbox = <label className="grocery-check"><Checkbox aria-label={`${title} purchased`} checked={checked} disabled={readOnly || update.isPending || remove.isPending} onCheckedChange={checkOff} /></label>;
  const icon = <span className="grocery-item__icon"><FoodCategoryIcon name={title} size={isMobile ? "compact" : "row"} /></span>;

  return (
    <article className={`grocery-item ${checked ? "grocery-item--checked" : ""}`}>
      <div className="grocery-item__main">
        {checkbox}
        {icon}
        <div className="grocery-item__content">{itemDetail}</div>
        {isMobile && !readOnly ? <button type="button" className="grocery-item__more" aria-label={`Edit ${title}`} onClick={() => setMobileEditOpen(true)}><MoreHorizontal aria-hidden="true" /></button> : null}
        {!isMobile && !readOnly ? <div className="grocery-item__controls"><ConfirmDialog trigger={<button className="grocery-item__remove" type="button" aria-label={`Remove ${title}`} title={`Remove ${title}`} disabled={remove.isPending || update.isPending}><X aria-hidden="true" /></button>} title={`Remove ${title} from your list?`} description={sourceMeals.length ? "This removes the item and its recipe-source context from this shopping pass." : "This removes the item from this shopping pass."} confirmLabel="Remove item" onConfirm={() => remove.mutate()} /></div> : null}
      </div>
      {isMobile && !readOnly ? <Dialog.Root open={mobileEditOpen} onOpenChange={setMobileEditOpen}><Dialog.Portal><Dialog.Overlay className="dialog-overlay" /><Dialog.Content className="dialog grocery-sheet" aria-describedby="grocery-mobile-sheet-description"><span className="grocery-sheet__handle" aria-hidden="true" /><header><div><p className="eyebrow">Grocery item</p><Dialog.Title>{title}</Dialog.Title><Dialog.Description id="grocery-mobile-sheet-description" className="muted">Update this item without losing its meal context.</Dialog.Description></div><DialogCloseButton label="Close item editor" /></header><form className="grocery-edit" onSubmit={(event) => { save(event); setMobileEditOpen(false); }}><Field label="Item"><input className="input" disabled={remove.isPending} value={name} onChange={(event) => setName(event.target.value)} /></Field><div className="grocery-sheet__measure"><Field label="Quantity"><DecimalInput value={quantity} onInput={(event) => setQuantity(event.currentTarget.value)} /></Field><Field label="Unit"><input className="input" disabled={remove.isPending} value={unit} onChange={(event) => setUnit(event.target.value)} /></Field></div><Field label="Shopping stop"><Select value={item.shoppingStop?.id ?? ""} disabled={remove.isPending || update.isPending} onChange={(event) => update.mutate({ shoppingStopId: event.target.value || null })}><option value="">Unassigned</option>{stops.map((stop) => <option value={stop.id} key={stop.id}>{stop.name}</option>)}</Select></Field><Field label="Aisle"><Select value={item.aisle ?? ""} disabled={remove.isPending || update.isPending} onChange={(event) => update.mutate({ aisle: (event.target.value || null) as GroceryItemWrite["aisle"] })}><option value="">No aisle</option>{Object.entries(AISLE_LABELS).map(([key, label]) => <option value={key} key={key}>{label}</option>)}</Select></Field><Button type="submit" disabled={!name.trim() || update.isPending || remove.isPending}>Save changes</Button></form><ConfirmDialog trigger={<Button variant="ghost" className="grocery-sheet__remove" disabled={remove.isPending || update.isPending}>Remove from list</Button>} title={`Remove ${title} from your list?`} description="This removes the item from this shopping pass." confirmLabel="Remove item" onConfirm={() => remove.mutate()} /></Dialog.Content></Dialog.Portal></Dialog.Root> : null}
      {!isMobile && !readOnly ? <details className="grocery-item__edit"><summary aria-label={`Edit ${title}`} title={`Edit ${title}`}><MoreHorizontal aria-hidden="true" /></summary><form className="grocery-edit" onSubmit={save}><Field label={`${title} name`}><input className="input" disabled={remove.isPending} value={name} onChange={(event) => setName(event.target.value)} /></Field><Field label={`${title} quantity`}><DecimalInput value={quantity} onInput={(event) => setQuantity(event.currentTarget.value)} /></Field><Field label={`${title} unit`}><input className="input" disabled={remove.isPending} value={unit} onChange={(event) => setUnit(event.target.value)} /></Field><Field label={`Shopping stop for ${title}`}><Select value={item.shoppingStop?.id ?? ""} disabled={remove.isPending || update.isPending} onChange={(event) => update.mutate({ shoppingStopId: event.target.value || null })}><option value="">Unassigned</option>{stops.map((stop) => <option value={stop.id} key={stop.id}>{stop.name}</option>)}</Select></Field><Field label={`Aisle for ${title}`}><Select value={item.aisle ?? ""} disabled={remove.isPending || update.isPending} onChange={(event) => update.mutate({ aisle: (event.target.value || null) as GroceryItemWrite["aisle"] })}><option value="">No aisle</option>{Object.entries(AISLE_LABELS).map(([key, label]) => <option value={key} key={key}>{label}</option>)}</Select></Field>{item.origin === "generated" && !item.needsReview && item.shoppingStop ? <label className="check-label"><Checkbox disabled={remove.isPending || update.isPending} onCheckedChange={(value) => { if (value === true) update.mutate({ rememberPlacement: true }); }} />Always put {title} at this stop</label> : null}<Button variant="secondary" type="submit" disabled={!name.trim() || update.isPending || remove.isPending}>Save changes</Button></form></details> : null}
      {error instanceof Error ? <p className="error-text" role="alert">{conflict ? "This item changed elsewhere. Reload the list before trying again." : error.message}</p> : null}
      {conflict ? <div className="actions"><Button onClick={() => void refresh()}>Reload list</Button></div> : null}
      <Dialog.Root open={showExpirySheet} onOpenChange={setShowExpirySheet}>
        <Dialog.Portal>
          <Dialog.Overlay className="dialog-overlay" />
          <Dialog.Content className="dialog expiry-sheet" aria-describedby="expiry-sheet-description">
            <header className="expiry-sheet__header">
              <div>
                <p className="eyebrow">Freshness</p>
                <Dialog.Title>When does {title} expire?</Dialog.Title>
                <Dialog.Description id="expiry-sheet-description" className="muted">Add the date from the label so Cookfully can nudge you before it spoils.</Dialog.Description>
              </div>
              <DialogCloseButton label="Close expiry sheet" />
            </header>
            <div className="expiry-sheet__form">
              <Field label="Expiry date">
                <input className="input" type="date" min={today} max={plus90} value={draftExpiresOn} onChange={(event) => setDraftExpiresOn(event.currentTarget.value)} />
              </Field>
              <div className="actions">
                <Button onClick={() => update.mutate({ expiresOn: draftExpiresOn || null })} disabled={!draftExpiresOn || update.isPending}>Save expiry</Button>
                <Button variant="ghost" onClick={() => setShowExpirySheet(false)}>Skip</Button>
              </div>
            </div>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
    </article>
  );
}

export function GroceryListPage() {
  const queryClient = useQueryClient();
  const isMobile = useMobileLayout();
  const [searchParams] = useSearchParams();
  const manualItemRef = useRef<HTMLInputElement>(null);
  const preferences = useQuery({ queryKey: ["owner-preferences"], queryFn: planningApi.preferences });
  const [weekStart, setWeekStart] = useState("");
  const [newItem, setNewItem] = useState<GroceryItemCreate>({ displayName: "", quantity: null, unit: null });
  const [deductions, setDeductions] = useState<PantryDeduction[]>([]);
  // On a phone the add-item field is always on screen; the sheet is only the
  // "with quantity" path, so ?add=1 focuses the field instead of opening it.
  const [manualOpen, setManualOpen] = useState(searchParams.get("add") === "1" && !isMobile);
  const [mobileActionsOpen, setMobileActionsOpen] = useState(false);
  const [basketOpen, setBasketOpen] = useState<boolean | null>(null);
  useEffect(() => {
    if (!preferences.data || weekStart) return;
    setWeekStart(weekStartFor(todayInTimezone(preferences.data.timezone), preferences.data.weekStartsOn));
  }, [preferences.data, weekStart]);
  useEffect(() => {
    if (searchParams.get("add") !== "1") return;
    if (!isMobile) setManualOpen(true);
    window.requestAnimationFrame(() => manualItemRef.current?.focus());
  }, [searchParams, isMobile]);
  const list = useQuery({
    queryKey: ["grocery-list", weekStart],
    queryFn: () => groceryApi.get(weekStart),
    enabled: Boolean(weekStart),
    retry: false,
    refetchInterval: (query) => query.state.data?.status === "generating" ? 2_000 : false,
  });
  // The plan is only contextual metadata for source links; load it alongside
  // the grocery list instead of making it wait for the list response.
  const plan = useQuery({ queryKey: ["meal-plan", weekStart], queryFn: () => planningApi.plan(weekStart), enabled: Boolean(weekStart), retry: false });
  const stops = useQuery({ queryKey: ["grocery-shopping-stops"], queryFn: groceryApi.stops });
  const regenerate = useMutation({
    mutationFn: () => groceryApi.regenerate(weekStart),
    onSuccess: (value) => queryClient.setQueryData(["grocery-list", weekStart], value),
  });
  const createEmpty = useMutation({
    mutationFn: () => groceryApi.createEmpty(weekStart),
    onSuccess: (value) => queryClient.setQueryData(["grocery-list", weekStart], value),
  });
  const create = useMutation({
    mutationFn: () => groceryApi.create(weekStart, newItem),
    onSuccess: (saved) => {
      setNewItem({ displayName: "", quantity: null, unit: null });
      queryClient.setQueryData<GroceryList>(["grocery-list", weekStart], (current) => current
        ? { ...current, items: [...current.items, saved] }
        : current);
      void queryClient.invalidateQueries({ queryKey: ["grocery-list", weekStart] });
    },
  });
  const applyDeductions = useMutation({
    mutationFn: () => pantryApi.applyDeductions(weekStart, { expectedGroceryListVersion: list.data!.version }),
    onSuccess: (value) => {
      setDeductions(value);
      void queryClient.invalidateQueries({ queryKey: ["grocery-list", weekStart] });
      void queryClient.invalidateQueries({ queryKey: ["pantry-items"] });
    },
  });
  const reverseDeduction = useMutation({
    mutationFn: (value: PantryDeduction) => pantryApi.reverseDeduction(value.id, value.version),
    onSuccess: (value) => {
      setDeductions((current) => current.map((item) => item.id === value.id ? value : item));
      void queryClient.invalidateQueries({ queryKey: ["grocery-list", weekStart] });
      void queryClient.invalidateQueries({ queryKey: ["pantry-items"] });
    },
  });
  const complete = useMutation({ mutationFn: () => groceryApi.complete(weekStart, list.data!.version), onSuccess: (value) => queryClient.setQueryData(["grocery-list", weekStart], value) });
  const reopen = useMutation({ mutationFn: () => groceryApi.reopen(weekStart, list.data!.version), onSuccess: (value) => queryClient.setQueryData(["grocery-list", weekStart], value) });
  const anyMutationPending = regenerate.isPending || createEmpty.isPending || create.isPending || applyDeductions.isPending || reverseDeduction.isPending || complete.isPending || reopen.isPending;
  const reloadList = () => void queryClient.invalidateQueries({ queryKey: ["grocery-list", weekStart] });
  const missing = list.error instanceof ApiProblem && list.error.status === 404;

  if (preferences.isPending || !weekStart || list.isPending) return <PageState><Skeleton label="Loading grocery list" lines={8} /></PageState>;
  if (preferences.isError) return <PageState><ErrorRecovery title="Calendar preferences could not be loaded" onRetry={() => void preferences.refetch()} /></PageState>;
  if (list.isError && !missing) return <PageState><ErrorRecovery title="Grocery list could not be loaded" onRetry={() => void list.refetch()} /></PageState>;
  if (missing || !list.data) return (
    <main className="page-shell grocery-page grocery-page--onramp">
      <PageHeader
        eyebrow="Grocery"
        title="Plan meals. Shop with a clear list."
        description="Cookfully gathers ingredients from your plan and keeps the list editable."
      />
      <section className="grocery-onramp" aria-labelledby="grocery-onramp-title">
        <div className="grocery-onramp__lead">
          <span className="grocery-onramp__mark" aria-hidden="true"><ShoppingBasket /></span>
          <p className="eyebrow">One useful shopping pass</p>
          <h2 id="grocery-onramp-title">Everything for the meals you actually want to cook.</h2>
          <p>Start with your plan, or make a list for anything else you need.</p>
          <div className="actions"><Button asChild><Link to="/app/plan">Open meal plan</Link></Button><Button variant="secondary" onClick={() => createEmpty.mutate()} disabled={createEmpty.isPending}>{createEmpty.isPending ? "Starting your list…" : "Start an empty list"}</Button></div>
          {createEmpty.error instanceof Error ? <p className="error-text grocery-onramp__error" role="alert">{createEmpty.error.message} <Button variant="ghost" onClick={() => createEmpty.mutate()} disabled={createEmpty.isPending}>Try again</Button></p> : null}
        </div>
        <ol className="grocery-onramp__steps">
          <li><span><CalendarDays aria-hidden="true" /></span><div><strong>Plan meals</strong><p>Pick what you want to cook.</p></div></li>
          <li><span><PackageCheck aria-hidden="true" /></span><div><strong>Use what you have</strong><p>Pantry matches reduce the list.</p></div></li>
          <li><span><ShoppingBasket aria-hidden="true" /></span><div><strong>Shop and check off</strong><p>Keep the list editable as you go.</p></div></li>
        </ol>
      </section>
    </main>
  );


  const activeItems = list.data.items.filter((item) => !item.checked);
  const purchasedItems = list.data.items.filter((item) => item.checked);
  const isListEmpty = list.data.items.length === 0;
  const plannedEntries = plan.data?.entries ?? [];
  const plannedMealCount = plannedEntries.length;
  const readOnly = list.data.status === "completed";
  const status = list.data.status;
  const sourceMealsByEntry = new Map(plannedEntries.map((entry) => [entry.id, { recipeId: entry.recipeId, recipeTitle: entry.recipeTitle }]));
  const progress = list.data.items.length ? Math.round((purchasedItems.length / list.data.items.length) * 100) : 0;
  const today = preferences.data ? todayInTimezone(preferences.data.timezone) : todayInTimezone(Intl.DateTimeFormat().resolvedOptions().timeZone);
  const summary = isListEmpty
    ? "Nothing on the list yet"
    : activeItems.length ? `${activeItems.length} to pick up · ${purchasedItems.length} in the basket` : "Everything is in the basket.";
  const stopGroups = [
    ...((stops.data ?? []).map((stop) => [stop.name, activeItems.filter((item) => item.shoppingStop?.id === stop.id)] as const)),
    ["Unassigned", activeItems.filter((item) => !item.shoppingStop)] as const,
  ].filter(([, items]) => items.length);
  const basketIsOpen = basketOpen ?? activeItems.length === 0;
  const renderRow = (item: GroceryItem) => <GroceryRow key={item.id} item={item} weekStart={weekStart} stops={stops.data ?? []} readOnly={readOnly} sourceMealsByEntry={sourceMealsByEntry} today={today} />;
  const addFormFields = <>
    <Field label="Item"><input ref={manualItemRef} className="input" value={newItem.displayName} onChange={(event) => { const displayName = event.currentTarget.value; setNewItem((value) => ({ ...value, displayName })); }} /></Field>
    <Field label="Quantity"><DecimalInput value={newItem.quantity ?? ""} onInput={(event) => { const quantity = event.currentTarget.value || null; setNewItem((value) => ({ ...value, quantity })); }} /></Field>
    <Field label="Unit"><input className="input" value={newItem.unit ?? ""} onChange={(event) => { const unit = event.currentTarget.value || null; setNewItem((value) => ({ ...value, unit })); }} /></Field>
    <Button type="submit" disabled={!newItem.displayName.trim() || create.isPending}>Add to list</Button>
  </>;
  const desktopAdd = !readOnly && !isMobile
    ? <details className="grocery-manual" open={manualOpen} onToggle={(event) => setManualOpen(event.currentTarget.open)}><summary><Plus aria-hidden="true" /><span><strong>Add something else</strong><small>Staples and extras that are not part of a planned recipe</small></span></summary><form className="grocery-edit" onSubmit={(event) => { event.preventDefault(); create.mutate(); }}>{addFormFields}</form></details>
    : null;
  const finishDialog = (variant: "primary" | "secondary") => <ConfirmDialog trigger={<Button variant={variant === "primary" ? "default" : "secondary"} disabled={anyMutationPending}>{complete.isPending ? "Finishing…" : "Finish shop"}</Button>} title="Finish this shopping pass?" description={activeItems.length ? `${activeItems.length} unchecked ${activeItems.length === 1 ? "item stays" : "items stay"} on the list as a record. The list becomes read-only until you reopen it.` : "This keeps the checked list as a record and makes it read-only until you reopen it."} confirmLabel="Finish shopping pass" onConfirm={() => complete.mutate()} />;
  const pantryDialog = <ConfirmDialog trigger={<Button variant="secondary" disabled={anyMutationPending}><PackageCheck aria-hidden="true" />Use pantry stock</Button>} title="Use what is already in your pantry?" description="Cookfully will only subtract reviewed matches with compatible units. You can inspect and reverse every deduction below." confirmLabel="Use pantry stock" onConfirm={() => applyDeductions.mutate()} />;
  const canFinish = !readOnly && !isListEmpty;

  const statusNotice = status === "completed" ? (
    <section className="grocery-complete" role="status"><KitchenCompanion moment="milestone" size="sm" /><div><strong>This shopping pass is complete</strong><p>Your ingredients are ready. Open today’s plan when you are ready to cook.</p></div><div className="grocery-complete__actions"><Button asChild><Link to="/app/plan">See today’s plan</Link></Button><Button variant="secondary" onClick={() => reopen.mutate()} disabled={anyMutationPending}>Reopen list</Button></div></section>
  ) : status === "generating" ? <p className="notice grocery-notice" role="status">Building your grocery list from the latest plan…</p> : null;

  const stalePanel = !readOnly && status === "dirty" && !isListEmpty ? (
    <section className="grocery-stale" aria-labelledby="grocery-stale-title">
      <h2 id="grocery-stale-title">Your plan changed</h2>
      <p>Your meal plan changed. Refresh the list to update quantities without losing checked items or things you added yourself.</p>
      <Button onClick={() => regenerate.mutate()} disabled={anyMutationPending}><RefreshCw aria-hidden="true" />{regenerate.isPending ? "Updating…" : isMobile ? "Update grocery list" : "Refresh from plan"}</Button>
    </section>
  ) : null;

  const buildCard = isMobile && !readOnly && isListEmpty && status !== "generating" ? (
    <section className="grocery-build" aria-labelledby="grocery-build-title">
      <div><p className="eyebrow">From your meal plan</p><h2 id="grocery-build-title">{plannedMealCount ? `${plannedMealCount} planned meal${plannedMealCount === 1 ? "" : "s"}, one shopping list` : "Start with one planned meal"}</h2><p>{plannedMealCount ? "Cookfully gathers the ingredients, then you can edit anything before you shop." : "Pick a recipe you want to cook. The grocery list will be ready when you come back."}</p></div>
      {plannedMealCount ? <Button onClick={() => regenerate.mutate()} disabled={anyMutationPending}><RefreshCw aria-hidden="true" />{regenerate.isPending ? "Building…" : "Build grocery list"}</Button> : <Button asChild><Link to="/app/plan">Open meal plan</Link></Button>}
    </section>
  ) : null;

  const header = (
    <header className="grocery-intro">
      <div className="grocery-intro__copy">
        <p className="grocery-intro__week">Week of {longDate(list.data.weekStart)}</p>
        <h1>Grocery</h1>
        <p className="grocery-intro__summary" aria-live="polite">{summary}</p>
        {isMobile && !isListEmpty ? <div className="grocery-progress"><progress value={purchasedItems.length} max={list.data.items.length} aria-label={`${progress}% complete`} /><span>{progress}%</span></div> : null}
      </div>
      <div className="grocery-intro__actions">
        {isMobile
          ? <>{!readOnly ? <button type="button" className="grocery-icon-button" aria-label="More grocery actions" onClick={() => setMobileActionsOpen(true)}><MoreHorizontal aria-hidden="true" /></button> : null}{canFinish ? finishDialog(activeItems.length === 0 ? "primary" : "secondary") : null}</>
          : readOnly ? null
          : isListEmpty ? <Button variant="secondary" onClick={() => regenerate.mutate()} disabled={anyMutationPending}><RefreshCw aria-hidden="true" />{regenerate.isPending ? "Refreshing…" : "Refresh from plan"}</Button>
          : <><Button asChild variant="secondary"><Link to="/app/plan">Back to meal plan</Link></Button>{pantryDialog}{finishDialog(activeItems.length === 0 ? "primary" : "secondary")}</>}
      </div>
    </header>
  );

  const aside = !isMobile && !isListEmpty ? (
    <aside className="grocery-aside" aria-label="About this list">
      {stalePanel ?? (!readOnly ? <section className="grocery-panel grocery-panel--status">
        <div className="grocery-ready" role="status"><PackageCheck aria-hidden="true" /><span><strong>{activeItems.length ? "Ready to shop" : "Everything picked up"}</strong><small>{activeItems.length ? `${activeItems.length} ${activeItems.length === 1 ? "item" : "items"} left to pick up` : "Finish the shop when you are out the door."}</small></span></div>
        <Button variant="secondary" onClick={() => regenerate.mutate()} disabled={anyMutationPending}><RefreshCw aria-hidden="true" />{regenerate.isPending ? "Refreshing…" : "Refresh from plan"}</Button>
      </section> : null)}
      <section className="grocery-panel" aria-labelledby="grocery-progress-title">
        <h2 id="grocery-progress-title">Progress</h2>
        <div className="grocery-progress" aria-label={`${progress}% of this shopping pass complete`}><progress value={purchasedItems.length} max={list.data.items.length} aria-hidden="true" /><span>{progress}%</span></div>
        <p className="grocery-panel__caption">{purchasedItems.length} of {list.data.items.length} picked up</p>
      </section>
      {plannedEntries.length ? <section className="grocery-panel" aria-labelledby="grocery-for-title">
        <h2 id="grocery-for-title">Shopping for</h2>
        <ul className="grocery-for">{plannedEntries.map((entry) => {
          const count = list.data.items.filter((item) => item.sources.some((source) => source.mealPlanEntryId === entry.id)).length;
          return <li key={entry.id}>{entry.recipeId ? <Link to={`/app/recipes/${entry.recipeId}`}>{entry.recipeTitle}</Link> : <span>{entry.recipeTitle}</span>}<small><span>{entry.mealSlot}</span> · {count ? `${count} item${count === 1 ? "" : "s"}` : "nothing to buy"}</small></li>;
        })}</ul>
        <Link className="grocery-panel__link" to="/app/plan">Open plan</Link>
      </section> : null}
    </aside>
  ) : null;

  const deductionPanel = deductions.length ? <section className="pantry-deduction-panel" aria-labelledby="deduction-heading"><div><h2 id="deduction-heading">Pantry deductions from this action</h2><p className="muted">Conversions are recorded on both sides. Reverse newer deductions first if quantities overlap.</p></div><div className="deduction-list">{deductions.map((deduction) => <article key={deduction.id} className="deduction-row"><div><strong>{deduction.groceryQuantity} {deduction.groceryUnit} removed from groceries</strong><p className="data-value">Pantry change: {deduction.pantryQuantity} {deduction.pantryUnit}</p><small>{deduction.assumption}</small></div><span className="reliability-badge">{deduction.status}</span>{deduction.status === "applied" ? <ConfirmDialog trigger={<Button variant="secondary" disabled={reverseDeduction.isPending}>Reverse deduction</Button>} title="Reverse this pantry deduction?" description="Cookfully will restore the grocery quantity and undo the matching pantry change. Newer deductions may need to be reversed first." confirmLabel="Reverse deduction" onConfirm={() => reverseDeduction.mutate(deduction)} /> : null}</article>)}</div></section> : null;

  const listCard = !isListEmpty ? (
    <section className="grocery-list" aria-label="Items for this week">
      {stopGroups.map(([label, items]) => <section className="grocery-group" key={label}><div className="grocery-group__title"><h2>{label}</h2><small>{items.length}</small></div><div className="grocery-items">{items.map(renderRow)}</div></section>)}
      {!stopGroups.length && !readOnly ? <p className="grocery-list__done">Everything is in the basket. Finish the shop when you are ready.</p> : null}
      {purchasedItems.length ? <details className="grocery-basket" open={basketIsOpen} onToggle={(event) => { if (event.currentTarget.open !== basketIsOpen) setBasketOpen(event.currentTarget.open); }}><summary><span>In basket</span><small>{purchasedItems.length}</small><ChevronDown aria-hidden="true" /></summary><div className="grocery-items">{purchasedItems.map(renderRow)}</div></details> : null}
    </section>
  ) : null;

  return (
    <main className={`page-shell grocery-page${readOnly ? " grocery-list--completed" : ""}${isMobile ? " grocery-page--mobile" : ""}`}>
      {header}
      {statusNotice}
      {isMobile ? <>{stalePanel}{buildCard}</> : null}
      {isListEmpty && status !== "generating" && status !== "completed" && !isMobile ? <EmptyState title="Nothing to pick up yet" description="Plan a meal, then build the list from the ingredients you need." action={<><Button onClick={() => regenerate.mutate()} disabled={anyMutationPending}><RefreshCw aria-hidden="true" />{regenerate.isPending ? "Building…" : "Build grocery list"}</Button><Button variant="secondary" asChild><Link to="/app/plan">Open meal plan</Link></Button></>} /> : null}
      {isListEmpty && !isMobile ? desktopAdd : null}
      {!isListEmpty ? <div className="grocery-layout">
        <div className="grocery-main">
          {!readOnly && !isMobile ? <ShoppingStopManager /> : null}
          {desktopAdd}
          {deductionPanel}
          {listCard}
        </div>
        {aside}
      </div> : deductionPanel}
      {regenerate.error instanceof Error ? <p className="error-text" role="alert">{regenerate.error.message} <Button variant="ghost" onClick={() => regenerate.mutate()} disabled={anyMutationPending}>Retry</Button></p> : null}
      {create.error instanceof Error ? <p className="error-text" role="alert">{create.error.message} <Button variant="ghost" onClick={() => create.mutate()} disabled={anyMutationPending}>Retry</Button></p> : null}
      {applyDeductions.error instanceof Error ? <p className="error-text" role="alert">{applyDeductions.error.message} <Button variant="ghost" onClick={() => applyDeductions.mutate()} disabled={anyMutationPending}>Retry</Button></p> : null}
      {reverseDeduction.error instanceof Error ? <p className="error-text" role="alert">{reverseDeduction.error.message} <Button variant="ghost" onClick={() => { const failed = reverseDeduction.variables; if (failed) reverseDeduction.mutate(failed); }} disabled={anyMutationPending}>Retry</Button></p> : null}
      {complete.error instanceof Error ? <p className="error-text" role="alert">{complete.error.message} The list is still open. <Button variant="ghost" onClick={reloadList}>Reload list</Button></p> : null}
      {reopen.error instanceof Error ? <p className="error-text" role="alert">{reopen.error.message} <Button variant="ghost" onClick={reloadList}>Reload list</Button></p> : null}
      {plan.isError ? <div className="notice grocery-notice" role="alert">Recipe context is temporarily unavailable. <Button variant="ghost" onClick={() => void plan.refetch()}>Retry context</Button></div> : null}
      {stops.isError ? <div className="notice grocery-notice" role="alert">Shopping stops could not be loaded. Items remain safe and can be assigned after you retry. <Button variant="ghost" onClick={() => void stops.refetch()}>Retry stops</Button></div> : null}
      {isMobile && !readOnly ? <form className="grocery-quickadd" onSubmit={(event) => { event.preventDefault(); if (newItem.displayName.trim()) create.mutate(); }}>
        <label className="grocery-quickadd__field"><Plus aria-hidden="true" /><span className="sr-only">Add an item</span><input ref={manualItemRef} type="text" enterKeyHint="done" autoComplete="off" placeholder="Add an item" value={newItem.displayName} onChange={(event) => { const displayName = event.currentTarget.value; setNewItem((value) => ({ ...value, displayName })); }} /></label>
        <button type="submit" className="grocery-quickadd__submit" disabled={!newItem.displayName.trim() || create.isPending}>Add</button>
        <button type="button" className="grocery-icon-button" aria-label="Add grocery item" title="Add with quantity" onClick={() => setManualOpen(true)}><ListPlus aria-hidden="true" /></button>
      </form> : null}
      {/* eslint-disable-next-line jsx-a11y/no-autofocus -- first field of a modal dialog, so focus belongs here on open */}
      {isMobile && !readOnly ? <Dialog.Root open={manualOpen} onOpenChange={setManualOpen}><Dialog.Portal><Dialog.Overlay className="dialog-overlay" /><Dialog.Content className="dialog grocery-sheet" aria-describedby="grocery-add-description"><span className="grocery-sheet__handle" aria-hidden="true" /><header><div><p className="eyebrow">Grocery</p><Dialog.Title>Add an item</Dialog.Title><Dialog.Description id="grocery-add-description" className="muted">A quick extra for this shopping pass.</Dialog.Description></div><DialogCloseButton label="Close add item" /></header><form className="grocery-edit" onSubmit={(event) => { event.preventDefault(); create.mutate(); setManualOpen(false); }}><Field label="Item"><input autoFocus className="input" value={newItem.displayName} onChange={(event) => { const displayName = event.currentTarget.value; setNewItem((value) => ({ ...value, displayName })); }} /></Field><div className="grocery-sheet__measure"><Field label="Quantity"><DecimalInput value={newItem.quantity ?? ""} onInput={(event) => { const quantity = event.currentTarget.value || null; setNewItem((value) => ({ ...value, quantity })); }} /></Field><Field label="Unit"><input className="input" value={newItem.unit ?? ""} onChange={(event) => { const unit = event.currentTarget.value || null; setNewItem((value) => ({ ...value, unit })); }} /></Field></div><Button type="submit" disabled={!newItem.displayName.trim() || create.isPending}>Add to list</Button></form></Dialog.Content></Dialog.Portal></Dialog.Root> : null}
      {isMobile && !readOnly ? <Dialog.Root open={mobileActionsOpen} onOpenChange={setMobileActionsOpen}><Dialog.Portal><Dialog.Overlay className="dialog-overlay" /><Dialog.Content className="dialog grocery-sheet grocery-sheet--actions" aria-describedby="grocery-actions-description"><span className="grocery-sheet__handle" aria-hidden="true" /><header><div><p className="eyebrow">Shopping pass</p><Dialog.Title>List actions</Dialog.Title><Dialog.Description id="grocery-actions-description" className="muted">Keep list maintenance out of the way while you shop.</Dialog.Description></div><DialogCloseButton label="Close grocery actions" /></header><div className="grocery-mobile-actions">{!isListEmpty && status !== "dirty" ? <Button variant="secondary" onClick={() => { regenerate.mutate(); setMobileActionsOpen(false); }} disabled={anyMutationPending}><RefreshCw aria-hidden="true" />{regenerate.isPending ? "Refreshing…" : "Refresh from plan"}</Button> : null}{!isListEmpty ? <ConfirmDialog trigger={<Button variant="secondary" disabled={anyMutationPending}><PackageCheck aria-hidden="true" />Use pantry stock</Button>} title="Use what is already in your pantry?" description="Cookfully will only subtract reviewed matches with compatible units." confirmLabel="Use pantry stock" onConfirm={() => applyDeductions.mutate()} /> : null}<ShoppingStopManager /></div></Dialog.Content></Dialog.Portal></Dialog.Root> : null}
    </main>
  );
}
