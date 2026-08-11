import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { Button, ConfirmDialog, DecimalInput, EmptyState, ErrorRecovery, Field, PageHeader, Skeleton } from "../../components";
import { pantryApi } from "../pantry/api";
import type { PantryDeduction } from "../pantry/types";
import { planningApi } from "../plans/api";
import { todayInTimezone, weekStartFor } from "../plans/dates";
import { ApiProblem } from "../recipes/api";
import { groceryApi } from "./api";
import type { GroceryItem, GroceryItemCreate, GroceryItemWrite } from "./types";

function GroceryRow({ item, weekStart }: { item: GroceryItem; weekStart: string }) {
  const queryClient = useQueryClient();
  const title = item.displayName ?? "Unnamed grocery item";
  const [name, setName] = useState(title);
  const [quantity, setQuantity] = useState(item.quantity ?? "");
  const [unit, setUnit] = useState(item.unit ?? "");
  const [checked, setChecked] = useState(item.checked ?? false);
  const [showSources, setShowSources] = useState(false);
  useEffect(() => setChecked(item.checked ?? false), [item.checked]);
  const refresh = () => queryClient.invalidateQueries({ queryKey: ["grocery-list", weekStart] });
  const update = useMutation({
    mutationFn: (value: GroceryItemWrite) => groceryApi.update(item.id, item.version, value),
    onSuccess: () => void refresh(),
  });
  const remove = useMutation({
    mutationFn: () => groceryApi.remove(item.id, item.version),
    onSuccess: () => void refresh(),
  });
  const error = update.error ?? remove.error;
  const conflict = error instanceof ApiProblem && error.status === 409;

  function save(event: FormEvent) {
    event.preventDefault();
    update.mutate({ displayName: name, quantity: quantity || null, unit: unit || null });
  }

  return (
    <article className={`grocery-item ${checked ? "grocery-item--checked" : ""}`}>
      <div className="grocery-item__heading">
        <label className="grocery-check"><input type="checkbox" aria-label={`${title} purchased`} checked={checked} onChange={(event) => { const next = event.currentTarget.checked; setChecked(next); update.mutate({ checked: next }, { onError: () => setChecked(!next) }); }} /><span aria-hidden="true" /></label>
        <div><h3>{title}</h3><p className="data-value">{item.quantity ?? "As needed"}{item.unit ? ` ${item.unit}` : ""}</p></div>
        <div className="item-badges"><span className="reliability-badge">{item.origin}</span>{item.needsReview ? <span className="review-badge">Needs review</span> : null}</div>
      </div>
      <form className="grocery-edit" onSubmit={save}><Field label={`${title} name`}><input className="input" value={name} onChange={(event) => setName(event.target.value)} /></Field><Field label={`${title} quantity`}><DecimalInput value={quantity} onInput={(event) => setQuantity(event.currentTarget.value)} /></Field><Field label={`${title} unit`}><input className="input" value={unit} onChange={(event) => setUnit(event.target.value)} /></Field><Button className="button--secondary" type="submit" disabled={!name.trim() || update.isPending}>Save {title}</Button></form>
      {item.sources.length ? <div><Button className="button--text" aria-expanded={showSources} onClick={() => setShowSources((value) => !value)}>{showSources ? "Hide" : "Show"} {title} sources</Button>{showSources ? <ul className="source-list">{item.sources.map((source) => <li key={`${source.mealPlanEntryId}-${source.originalText}`}><span>{source.originalText}</span><span className="data-value">{source.quantityContribution ?? "Unquantified"}{item.unit && source.quantityContribution ? ` ${item.unit}` : ""}</span></li>)}</ul> : null}</div> : <p className="muted">Manual item</p>}
      {error instanceof Error ? <p className="error-text" role="alert">{conflict ? "This item changed elsewhere. Reload the list before trying again." : error.message}</p> : null}
      <div className="actions">{conflict ? <Button onClick={() => void refresh()}>Reload list</Button> : null}<Button className="button--text" onClick={() => remove.mutate()} disabled={remove.isPending}>Remove {title}</Button></div>
    </article>
  );
}

export function GroceryListPage() {
  const queryClient = useQueryClient();
  const preferences = useQuery({ queryKey: ["owner-preferences"], queryFn: planningApi.preferences });
  const [weekStart, setWeekStart] = useState("");
  const [newItem, setNewItem] = useState<GroceryItemCreate>({ displayName: "", quantity: null, unit: null });
  const [deductions, setDeductions] = useState<PantryDeduction[]>([]);
  useEffect(() => {
    if (!preferences.data || weekStart) return;
    setWeekStart(weekStartFor(todayInTimezone(preferences.data.timezone), preferences.data.weekStartsOn));
  }, [preferences.data, weekStart]);
  const list = useQuery({ queryKey: ["grocery-list", weekStart], queryFn: () => groceryApi.get(weekStart), enabled: Boolean(weekStart), retry: false });
  const regenerate = useMutation({
    mutationFn: () => groceryApi.regenerate(weekStart),
    onSuccess: (value) => queryClient.setQueryData(["grocery-list", weekStart], value),
  });
  const create = useMutation({
    mutationFn: () => groceryApi.create(weekStart, newItem),
    onSuccess: () => {
      setNewItem({ displayName: "", quantity: null, unit: null });
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
  const missing = list.error instanceof ApiProblem && list.error.status === 404;

  if (preferences.isPending || !weekStart || list.isPending) return <Skeleton label="Loading grocery list" lines={8} />;
  if (preferences.isError) return <ErrorRecovery title="Calendar preferences could not be loaded" onRetry={() => void preferences.refetch()} />;
  if (list.isError && !missing) return <ErrorRecovery title="Grocery list could not be loaded" onRetry={() => void list.refetch()} />;
  if (missing || !list.data) return <main className="page-shell"><EmptyState title="No grocery list yet" description="Generate a traceable list from the exact servings in this week’s plan." action={<Button onClick={() => regenerate.mutate()} disabled={regenerate.isPending}>{regenerate.isPending ? "Generating…" : "Generate grocery list"}</Button>} /></main>;

  const groups = [
    ["To buy", list.data.items.filter((item) => !item.checked)],
    ["Purchased", list.data.items.filter((item) => item.checked)],
  ] as const;
  return (
    <main className="page-shell">
      <PageHeader eyebrow={`Week of ${list.data.weekStart}`} title="Grocery list" description="Generated quantities retain the recipe ingredient text and plan entry that produced them." actions={<><Button asChild className="button--secondary"><Link to="/app/plan">Weekly plan</Link></Button><Button onClick={() => regenerate.mutate()} disabled={regenerate.isPending}>{regenerate.isPending ? "Regenerating…" : "Regenerate grocery list"}</Button><ConfirmDialog trigger={<Button className="button--secondary">Apply pantry quantities</Button>} title="Deduct safe pantry matches?" description="Only reviewed exact food identities with compatible units will be deducted. Every applied conversion is shown below and can be reversed until either quantity changes." confirmLabel="Apply safe deductions" onConfirm={() => applyDeductions.mutate()} /></>} />
      {list.data.status === "dirty" ? <p className="notice">The plan changed after this list was generated. Regenerate to reconcile quantities while preserving checks and manual edits.</p> : list.data.status === "generating" ? <p className="notice" role="status">Grocery list is generating.</p> : <p className="success-text" role="status">List is current</p>}
      <section className="manual-item"><h2>Add an item</h2><div className="grocery-edit"><Field label="New item name"><input className="input" value={newItem.displayName} onChange={(event) => { const displayName = event.currentTarget.value; setNewItem((value) => ({ ...value, displayName })); }} /></Field><Field label="New item quantity"><DecimalInput value={newItem.quantity ?? ""} onInput={(event) => { const quantity = event.currentTarget.value || null; setNewItem((value) => ({ ...value, quantity })); }} /></Field><Field label="New item unit"><input className="input" value={newItem.unit ?? ""} onChange={(event) => { const unit = event.currentTarget.value || null; setNewItem((value) => ({ ...value, unit })); }} /></Field><Button onClick={() => create.mutate()} disabled={!newItem.displayName.trim() || create.isPending}>Add grocery item</Button></div></section>
      {deductions.length ? <section className="pantry-deduction-panel" aria-labelledby="deduction-heading"><div><h2 id="deduction-heading">Pantry deductions from this action</h2><p className="muted">Conversions are recorded on both sides. Reverse newer deductions first if quantities overlap.</p></div><div className="deduction-list">{deductions.map((deduction) => <article key={deduction.id} className="deduction-row"><div><strong>{deduction.groceryQuantity} {deduction.groceryUnit} removed from groceries</strong><p className="data-value">Pantry change: {deduction.pantryQuantity} {deduction.pantryUnit}</p><small>{deduction.assumption}</small></div><span className="reliability-badge">{deduction.status}</span>{deduction.status === "applied" ? <Button className="button--secondary" onClick={() => reverseDeduction.mutate(deduction)} disabled={reverseDeduction.isPending}>Reverse deduction</Button> : null}</article>)}</div></section> : null}
      {groups.map(([label, items]) => items.length ? <section className="grocery-group" key={label}><div className="section-heading"><h2>{label}</h2><span className="data-value">{items.length} item{items.length === 1 ? "" : "s"}</span></div><div className="grocery-items">{items.map((item) => <GroceryRow key={item.id} item={item} weekStart={weekStart} />)}</div></section> : null)}
      {regenerate.error instanceof Error ? <p className="error-text" role="alert">{regenerate.error.message}</p> : null}
      {create.error instanceof Error ? <p className="error-text" role="alert">{create.error.message}</p> : null}
      {applyDeductions.error instanceof Error ? <p className="error-text" role="alert">{applyDeductions.error.message}</p> : null}
      {reverseDeduction.error instanceof Error ? <p className="error-text" role="alert">{reverseDeduction.error.message}</p> : null}
    </main>
  );
}
