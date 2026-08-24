import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import * as Dialog from "@radix-ui/react-dialog";
import { type FormEvent, useEffect, useRef, useState } from "react";
import { CalendarDays, MoreHorizontal, PackageCheck, Plus, RefreshCw, ShoppingBasket, X } from "lucide-react";
import { Link, useSearchParams } from "react-router-dom";

import { Button, ConfirmDialog, DecimalInput, DialogCloseButton, EmptyState, ErrorRecovery, Field, KitchenCompanion, PageHeader, PageState, SectionHeading, Select, Skeleton } from "../../components";
import { GroceryIcon } from "../../components/GroceryIcon";
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

type SourceMeal = { recipeId: string | null; recipeTitle: string };

export function GroceryRow({ item, weekStart, stops, readOnly, sourceMealsByEntry, today: todayProp }: { item: GroceryItem; weekStart: string; stops: GroceryShoppingStop[]; readOnly: boolean; sourceMealsByEntry: Map<string, SourceMeal>; today?: string }) {
  const queryClient = useQueryClient();
  const title = item.displayName ?? "Unnamed grocery item";
  const [name, setName] = useState(title);
  const [quantity, setQuantity] = useState(formatCookingInput(item.quantity));
  const [unit, setUnit] = useState(item.unit ?? "");
  const [checked, setChecked] = useState(item.checked ?? false);
  useEffect(() => setChecked(item.checked ?? false), [item.checked]);
  const refresh = () => queryClient.invalidateQueries({ queryKey: ["grocery-list", weekStart] });
  const fallbackToday = new Date().toISOString().slice(0, 10);
  const today = todayProp ?? fallbackToday;
  const plus90 = addDays(today, 90);
  const [showExpirySheet, setShowExpirySheet] = useState(false);
  const [draftExpiresOn, setDraftExpiresOn] = useState(item.expiresOn ?? "");
  useEffect(() => setDraftExpiresOn(item.expiresOn ?? ""), [item.expiresOn]);
  useEffect(() => {
    if (item.needsExpiryDate) setShowExpirySheet(true);
  }, [item.needsExpiryDate]);
  const badge = item.expiresOn ? expiryBadge(item.expiresOn, today) : null;
  const update = useMutation({
    mutationFn: (value: GroceryItemWrite) => groceryApi.update(item.id, item.version, value),
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

  return (
    <article className={`grocery-item ${checked ? "grocery-item--checked" : ""}`}>
      <div className="grocery-item__heading">
        <span className="grocery-item__icon"><GroceryIcon name={title} /></span>
        <label className="grocery-check"><Checkbox aria-label={`${title} purchased`} checked={checked} disabled={readOnly || update.isPending || remove.isPending} onCheckedChange={(value) => { if (readOnly || update.isPending || remove.isPending) return; const next = value === true; setChecked(next); update.mutate({ checked: next }, { onError: () => setChecked(!next) }); }} /></label>
        <div className="grocery-item__content"><h3>{title}</h3><p className="data-value">{item.quantity ? formatCookingNumber(item.quantity) : "As needed"}{item.unit ? ` ${item.unit}` : ""}{badge ? <button type="button" aria-label={`Expires ${item.expiresOn}`} className={`expiry-badge expiry-badge--${badge.tone}`} onClick={() => setShowExpirySheet(true)}>{badge.label}</button> : null}</p>{sourceMeals.length ? <p className="grocery-item__uses"><span>Used for</span>{sourceMeals.map((meal) => meal.recipeId ? <Link key={`${meal.recipeId}-${meal.recipeTitle}`} to={`/app/recipes/${meal.recipeId}`}>{meal.recipeTitle}</Link> : <span key={meal.recipeTitle}>{meal.recipeTitle}</span>)}</p> : item.sources.length ? <p className="grocery-item__uses"><span>Used for planned meals</span></p> : <p className="grocery-item__uses"><span>Added by you</span></p>}</div>
        <div className="grocery-item__controls">{item.needsReview ? <span className="review-badge">Needs review</span> : null}{!readOnly ? <ConfirmDialog trigger={<button className="grocery-item__remove" type="button" aria-label={`Remove ${title}`} title={`Remove ${title}`} disabled={remove.isPending || update.isPending}><X aria-hidden="true" /></button>} title={`Remove ${title} from your list?`} description={sourceMeals.length ? "This removes the item and its recipe-source context from this shopping pass." : "This removes the item from this shopping pass."} confirmLabel="Remove item" onConfirm={() => remove.mutate()} /> : null}</div>
      </div>
      {!readOnly ? <details className="grocery-item__edit"><summary aria-label={`Edit ${title}`} title={`Edit ${title}`}><MoreHorizontal aria-hidden="true" /></summary><form className="grocery-edit" onSubmit={save}><Field label={`${title} name`}><input className="input" disabled={remove.isPending} value={name} onChange={(event) => setName(event.target.value)} /></Field><Field label={`${title} quantity`}><DecimalInput value={quantity} onInput={(event) => setQuantity(event.currentTarget.value)} /></Field><Field label={`${title} unit`}><input className="input" disabled={remove.isPending} value={unit} onChange={(event) => setUnit(event.target.value)} /></Field><Field label={`Shopping stop for ${title}`}><Select value={item.shoppingStop?.id ?? ""} disabled={remove.isPending || update.isPending} onChange={(event) => update.mutate({ shoppingStopId: event.target.value || null })}><option value="">Unassigned</option>{stops.map((stop) => <option value={stop.id} key={stop.id}>{stop.name}</option>)}</Select></Field>{item.origin === "generated" && !item.needsReview && item.shoppingStop ? <label className="check-label"><Checkbox disabled={remove.isPending || update.isPending} onCheckedChange={(value) => { if (value === true) update.mutate({ rememberPlacement: true }); }} />Always put {title} at this stop</label> : null}<Button variant="secondary" type="submit" disabled={!name.trim() || update.isPending || remove.isPending}>Save changes</Button></form></details> : null}
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
  const [searchParams] = useSearchParams();
  const manualItemRef = useRef<HTMLInputElement>(null);
  const preferences = useQuery({ queryKey: ["owner-preferences"], queryFn: planningApi.preferences });
  const [weekStart, setWeekStart] = useState("");
  const [newItem, setNewItem] = useState<GroceryItemCreate>({ displayName: "", quantity: null, unit: null });
  const [deductions, setDeductions] = useState<PantryDeduction[]>([]);
  const [manualOpen, setManualOpen] = useState(searchParams.get("add") === "1");
  useEffect(() => {
    if (!preferences.data || weekStart) return;
    setWeekStart(weekStartFor(todayInTimezone(preferences.data.timezone), preferences.data.weekStartsOn));
  }, [preferences.data, weekStart]);
  useEffect(() => {
    if (searchParams.get("add") !== "1") return;
    setManualOpen(true);
    window.requestAnimationFrame(() => manualItemRef.current?.focus());
  }, [searchParams]);
  const list = useQuery({ queryKey: ["grocery-list", weekStart], queryFn: () => groceryApi.get(weekStart), enabled: Boolean(weekStart), retry: false });
  // The plan is only contextual metadata for source links; load it alongside
  // the grocery list instead of making it wait for the list response.
  const plan = useQuery({ queryKey: ["meal-plan", weekStart], queryFn: () => planningApi.plan(weekStart), enabled: Boolean(weekStart), retry: false });
  const stops = useQuery({ queryKey: ["grocery-shopping-stops"], queryFn: groceryApi.stops });
  const regenerate = useMutation({
    mutationFn: () => groceryApi.regenerate(weekStart),
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
  const anyMutationPending = regenerate.isPending || create.isPending || applyDeductions.isPending || reverseDeduction.isPending || complete.isPending || reopen.isPending;
  const reloadList = () => void queryClient.invalidateQueries({ queryKey: ["grocery-list", weekStart] });
  const missing = list.error instanceof ApiProblem && list.error.status === 404;

  if (preferences.isPending || !weekStart || list.isPending) return <PageState><Skeleton label="Loading grocery list" lines={8} /></PageState>;
  if (preferences.isError) return <PageState><ErrorRecovery title="Calendar preferences could not be loaded" onRetry={() => void preferences.refetch()} /></PageState>;
  if (list.isError && !missing) return <PageState><ErrorRecovery title="Grocery list could not be loaded" onRetry={() => void list.refetch()} /></PageState>;
  if (missing || !list.data) return (
    <main className="page-shell grocery-page grocery-page--onramp">
      <PageHeader
        eyebrow="Grocery"
        title="Your grocery list starts with your plan"
        description="Choose the meals first. Cookfully will gather what they need, preserve the quantities, and keep pantry decisions visible."
      />
      <section className="grocery-onramp" aria-labelledby="grocery-onramp-title">
        <div className="grocery-onramp__lead">
          <span className="grocery-onramp__mark" aria-hidden="true"><ShoppingBasket /></span>
          <p className="eyebrow">One useful shopping pass</p>
          <h2 id="grocery-onramp-title">From this week’s meals to one practical list</h2>
          <p>Plan as much or as little as you like. The list stays editable, so staples and last-minute extras still have a natural place.</p>
          <div className="actions"><Button asChild><Link to="/app/plan">Open meal plan</Link></Button><Button variant="secondary" onClick={() => regenerate.mutate()} disabled={regenerate.isPending}>{regenerate.isPending ? "Starting your list…" : "Start an empty list"}</Button></div>
        </div>
        <ol className="grocery-onramp__steps">
          <li><span><CalendarDays aria-hidden="true" /></span><div><strong>Plan the meals that matter</strong><p>Dinner-only is fine; breakfast, lunch, and snacks are available when useful.</p></div></li>
          <li><span><PackageCheck aria-hidden="true" /></span><div><strong>Use what is already home</strong><p>Reviewed pantry matches can reduce the list without hiding the deduction.</p></div></li>
          <li><span><ShoppingBasket aria-hidden="true" /></span><div><strong>Shop and check off</strong><p>Items stay grouped, editable, and easy to tap with one hand.</p></div></li>
        </ol>
      </section>
    </main>
  );

  const activeItems = list.data.items.filter((item) => !item.checked);
  const isListEmpty = list.data.items.length === 0;
  const readOnly = list.data.status === "completed";
  const sourceMealsByEntry = new Map(plan.data?.entries.map((entry) => [entry.id, { recipeId: entry.recipeId, recipeTitle: entry.recipeTitle }]) ?? []);
  const purchasedItems = list.data.items.filter((item) => item.checked);
  const progress = list.data.items.length ? Math.round((purchasedItems.length / list.data.items.length) * 100) : 0;
  const today = preferences.data ? todayInTimezone(preferences.data.timezone) : new Date().toISOString().slice(0, 10);
  const groups = [
    ...((stops.data ?? []).map((stop) => [stop.name, activeItems.filter((item) => item.shoppingStop?.id === stop.id)] as const)),
    ["Unassigned", activeItems.filter((item) => !item.shoppingStop)] as const,
    ["Purchased", list.data.items.filter((item) => item.checked)] as const,
  ].filter(([, items]) => items.length);
  const headerActions = readOnly ? undefined : isListEmpty
    ? <Button variant="secondary" onClick={() => regenerate.mutate()} disabled={anyMutationPending}><RefreshCw aria-hidden="true" />{regenerate.isPending ? "Refreshing…" : "Refresh from plan"}</Button>
    : <><Button asChild variant="secondary"><Link to="/app/plan">Back to meal plan</Link></Button><Button onClick={() => regenerate.mutate()} disabled={anyMutationPending}><RefreshCw aria-hidden="true" />{regenerate.isPending ? "Refreshing…" : "Refresh from plan"}</Button><ConfirmDialog trigger={<Button variant="secondary" disabled={anyMutationPending}><PackageCheck aria-hidden="true" />Use pantry stock</Button>} title="Use what is already in your pantry?" description="Cookfully will only subtract reviewed matches with compatible units. You can inspect and reverse every deduction below." confirmLabel="Use pantry stock" onConfirm={() => applyDeductions.mutate()} /></>;
  return (
    <main className={`page-shell grocery-page${readOnly ? " grocery-list--completed" : ""}`}>
      <PageHeader eyebrow={`Week of ${longDate(list.data.weekStart)}`} title="Everything you need this week" description="Built from the meals and servings in your plan. Check things off as they land in your basket." actions={headerActions} />
      {list.data.status === "completed" ? <section className="grocery-complete" role="status"><KitchenCompanion moment="milestone" size="sm" /><div><strong>This shopping pass is complete</strong><p>Kept as a record for this week. Reopen it only if you need to shop again.</p></div><Button variant="secondary" onClick={() => reopen.mutate()} disabled={anyMutationPending}>Reopen list</Button></section> : list.data.status === "dirty" ? <p className="notice grocery-notice">Your meal plan changed. Refresh the list to update quantities without losing checked items or things you added yourself.</p> : list.data.status === "generating" ? <p className="notice grocery-notice" role="status">Building your grocery list from the latest plan…</p> : !isListEmpty ? <section className="grocery-hero" aria-labelledby="grocery-hero-title">
        <div className="grocery-hero__lead">
          <span className="grocery-hero__mark" aria-hidden="true"><ShoppingBasket /></span>
          <p className="eyebrow">Shopping pass</p>
          <h2 id="grocery-hero-title">Ready when you are</h2>
          <p className="grocery-hero__description">Everything here came from this week’s meals. Check items as they land in your basket.</p>
          <div className="grocery-ready" role="status"><PackageCheck aria-hidden="true" /><span><strong>Ready to shop</strong><small>{activeItems.length} items left to pick up</small></span></div>
          <div className="grocery-progress" aria-label={`${progress}% of this shopping pass complete`}><span style={{ width: `${progress}%` }} /></div>
          <div className="grocery-progress__caption"><span>{progress}% complete</span><span>{purchasedItems.length} picked up</span></div>
        </div>
        <dl className="grocery-hero__stats">
          <div><dt>Still to pick up</dt><dd>{activeItems.length}</dd></div>
          <div><dt>Already in your basket</dt><dd>{purchasedItems.length}</dd></div>
          <div><dt>Plan coverage</dt><dd>{list.data.items.length} items</dd></div>
        </dl>
      </section> : null}
      {isListEmpty && list.data.status !== "generating" && list.data.status !== "completed" ? <EmptyState title="Nothing to pick up yet" description="Plan a meal and refresh this list, or add an extra manually below." action={<Button asChild><Link to="/app/plan">Open meal plan</Link></Button>} /> : null}
      {!isListEmpty ? <section className="grocery-list-stage" aria-labelledby="grocery-items-heading">
        <div className="grocery-list-stage__heading"><div><p className="eyebrow">Your shop</p><h2 id="grocery-items-heading">Items for this week</h2><p>Grouped by the places you visit, with the recipe context kept close by.</p></div><span>{activeItems.length ? `${activeItems.length} to pick up` : "All picked up"}</span></div>
        {list.data.status !== "completed" ? <ShoppingStopManager /> : null}
        {!readOnly ? <details className="manual-item grocery-manual" open={manualOpen} onToggle={(event) => setManualOpen(event.currentTarget.open)}><summary><Plus aria-hidden="true" /><span><strong>Add something else</strong><small>Staples and extras that are not part of a planned recipe</small></span></summary><form className="grocery-edit" onSubmit={(event) => { event.preventDefault(); create.mutate(); }}><Field label="Item"><input ref={manualItemRef} className="input" value={newItem.displayName} onChange={(event) => { const displayName = event.currentTarget.value; setNewItem((value) => ({ ...value, displayName })); }} /></Field><Field label="Quantity"><DecimalInput value={newItem.quantity ?? ""} onInput={(event) => { const quantity = event.currentTarget.value || null; setNewItem((value) => ({ ...value, quantity })); }} /></Field><Field label="Unit"><input className="input" value={newItem.unit ?? ""} onChange={(event) => { const unit = event.currentTarget.value || null; setNewItem((value) => ({ ...value, unit })); }} /></Field><Button type="submit" disabled={!newItem.displayName.trim() || create.isPending}>Add to list</Button></form></details> : null}
      {deductions.length ? <section className="pantry-deduction-panel" aria-labelledby="deduction-heading"><div><h2 id="deduction-heading">Pantry deductions from this action</h2><p className="muted">Conversions are recorded on both sides. Reverse newer deductions first if quantities overlap.</p></div><div className="deduction-list">{deductions.map((deduction) => <article key={deduction.id} className="deduction-row"><div><strong>{deduction.groceryQuantity} {deduction.groceryUnit} removed from groceries</strong><p className="data-value">Pantry change: {deduction.pantryQuantity} {deduction.pantryUnit}</p><small>{deduction.assumption}</small></div><span className="reliability-badge">{deduction.status}</span>{deduction.status === "applied" ? <ConfirmDialog trigger={<Button variant="secondary" disabled={reverseDeduction.isPending}>Reverse deduction</Button>} title="Reverse this pantry deduction?" description="Cookfully will restore the grocery quantity and undo the matching pantry change. Newer deductions may need to be reversed first." confirmLabel="Reverse deduction" onConfirm={() => reverseDeduction.mutate(deduction)} /> : null}</article>)}</div></section> : null}
        <div className="grocery-groups">{groups.map(([label, items]) => <section className="grocery-group" key={label}><SectionHeading title={label} meta={`${items.length} item${items.length === 1 ? "" : "s"}`} /><div className="grocery-items">{items.map((item) => <GroceryRow key={item.id} item={item} weekStart={weekStart} stops={stops.data ?? []} readOnly={readOnly} sourceMealsByEntry={sourceMealsByEntry} today={today} />)}</div></section>)}</div>
      </section> : null}
      {isListEmpty && !readOnly ? <details className="manual-item grocery-manual grocery-manual--empty" open={manualOpen} onToggle={(event) => setManualOpen(event.currentTarget.open)}><summary><Plus aria-hidden="true" /><span><strong>Add something else</strong><small>Staples and extras that are not part of a planned recipe</small></span></summary><form className="grocery-edit" onSubmit={(event) => { event.preventDefault(); create.mutate(); }}><Field label="Item"><input ref={manualItemRef} className="input" value={newItem.displayName} onChange={(event) => { const displayName = event.currentTarget.value; setNewItem((value) => ({ ...value, displayName })); }} /></Field><Field label="Quantity"><DecimalInput value={newItem.quantity ?? ""} onInput={(event) => { const quantity = event.currentTarget.value || null; setNewItem((value) => ({ ...value, quantity })); }} /></Field><Field label="Unit"><input className="input" value={newItem.unit ?? ""} onChange={(event) => { const unit = event.currentTarget.value || null; setNewItem((value) => ({ ...value, unit })); }} /></Field><Button type="submit" disabled={!newItem.displayName.trim() || create.isPending}>Add to list</Button></form></details> : null}
      {list.data.status !== "completed" && list.data.items.length > 0 && activeItems.length === 0 ? <ConfirmDialog trigger={<Button className="grocery-finish" disabled={anyMutationPending}>{complete.isPending ? "Finishing…" : "Finish this shopping pass"}</Button>} title="Finish this shopping pass?" description="This keeps the checked list as a record and makes it read-only until you reopen it." confirmLabel="Finish shopping pass" onConfirm={() => complete.mutate()} /> : null}
      {regenerate.error instanceof Error ? <p className="error-text" role="alert">{regenerate.error.message} <Button variant="ghost" onClick={() => regenerate.mutate()} disabled={anyMutationPending}>Retry</Button></p> : null}
      {create.error instanceof Error ? <p className="error-text" role="alert">{create.error.message} <Button variant="ghost" onClick={() => create.mutate()} disabled={anyMutationPending}>Retry</Button></p> : null}
      {applyDeductions.error instanceof Error ? <p className="error-text" role="alert">{applyDeductions.error.message} <Button variant="ghost" onClick={() => applyDeductions.mutate()} disabled={anyMutationPending}>Retry</Button></p> : null}
      {reverseDeduction.error instanceof Error ? <p className="error-text" role="alert">{reverseDeduction.error.message} <Button variant="ghost" onClick={() => { const failed = reverseDeduction.variables; if (failed) reverseDeduction.mutate(failed); }} disabled={anyMutationPending}>Retry</Button></p> : null}
      {complete.error instanceof Error ? <p className="error-text" role="alert">{complete.error.message} The list is still open. <Button variant="ghost" onClick={reloadList}>Reload list</Button></p> : null}
      {reopen.error instanceof Error ? <p className="error-text" role="alert">{reopen.error.message} <Button variant="ghost" onClick={reloadList}>Reload list</Button></p> : null}
      {plan.isError ? <div className="notice grocery-notice" role="alert">Recipe context is temporarily unavailable. <Button variant="ghost" onClick={() => void plan.refetch()}>Retry context</Button></div> : null}
      {stops.isError ? <div className="notice grocery-notice" role="alert">Shopping stops could not be loaded. Items remain safe and can be assigned after you retry. <Button variant="ghost" onClick={() => void stops.refetch()}>Retry stops</Button></div> : null}
    </main>
  );
}
