import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useEffect, useState } from "react";
import { Link } from "react-router-dom";

import {
  Button,
  ConfirmDialog,
  DecimalInput,
  EmptyState,
  ErrorRecovery,
  Field,
  PageHeader,
  Skeleton,
} from "../../components";
import { ApiProblem } from "../recipes/api";
import { pantryApi } from "./api";
import type { PantryItem, PantryItemWrite } from "./types";

const UNITS = ["g", "kg", "mg", "ml", "l", "count"] as const;

function PantryItemCard({ item }: { item: PantryItem }) {
  const queryClient = useQueryClient();
  const [displayName, setDisplayName] = useState(item.displayName);
  const [quantity, setQuantity] = useState(item.quantity);
  const [unit, setUnit] = useState(item.unit);
  const [referenceId, setReferenceId] = useState(item.foodReferenceId ?? "");
  useEffect(() => {
    setDisplayName(item.displayName);
    setQuantity(item.quantity);
    setUnit(item.unit);
    setReferenceId(item.foodReferenceId ?? "");
  }, [item]);
  const refresh = () => queryClient.invalidateQueries({ queryKey: ["pantry-items"] });
  const update = useMutation({
    mutationFn: (value: PantryItemWrite) => pantryApi.update(item.id, item.version, value),
    onSuccess: () => void refresh(),
  });
  const remove = useMutation({
    mutationFn: () => pantryApi.remove(item.id, item.version),
    onSuccess: () => void refresh(),
  });
  const error = update.error ?? remove.error;
  const conflict = error instanceof ApiProblem && error.status === 409;

  function save(event: FormEvent) {
    event.preventDefault();
    update.mutate({
      displayName: displayName.trim(),
      quantity,
      unit,
      foodReferenceId: referenceId.trim() || null,
    });
  }

  return (
    <article className="pantry-card" aria-label={item.displayName}>
      <div className="pantry-card__heading">
        <div>
          <h3>{item.displayName}</h3>
          <p className="data-value">{item.quantity} {item.unit}</p>
        </div>
        <span className={`match-badge match-badge--${item.matchStatus}`}>
          {item.matchStatus.replace("_", " ")}
          {item.matchConfidence ? ` · ${Math.round(Number(item.matchConfidence) * 100)}%` : ""}
        </span>
      </div>
      {item.matchStatus === "proposed" ? (
        <p className="notice">Review this proposed identity before it can be used for recipe matching or deductions.</p>
      ) : item.matchStatus === "unmatched" ? (
        <p className="muted">Unmatched items remain inventory only and are never deducted automatically.</p>
      ) : null}
      <form className="pantry-edit" onSubmit={save}>
        <Field label={`${item.displayName} food name`}>
          <input className="input" value={displayName} onChange={(event) => setDisplayName(event.currentTarget.value)} />
        </Field>
        <Field label={`${item.displayName} quantity`}>
          <DecimalInput value={quantity} onValueChange={setQuantity} />
        </Field>
        <Field label={`${item.displayName} unit`}>
          <select className="input" value={unit} onChange={(event) => setUnit(event.currentTarget.value)}>
            {UNITS.map((value) => <option key={value}>{value}</option>)}
          </select>
        </Field>
        <Field label={`${item.displayName} food reference ID`} hint="Optional advanced correction. Clear it to rematch by name.">
          <input className="input" value={referenceId} onChange={(event) => setReferenceId(event.currentTarget.value)} placeholder="UUID" />
        </Field>
        <Button className="button--secondary" type="submit" disabled={!displayName.trim() || update.isPending}>Save {item.displayName}</Button>
      </form>
      {error instanceof Error ? <p className="error-text" role="alert">{conflict ? "This pantry item changed. Reload before trying again." : error.message}</p> : null}
      <div className="actions">
        {conflict ? <Button onClick={() => void refresh()}>Reload</Button> : null}
        <ConfirmDialog
          trigger={<Button className="button--text">Remove {item.displayName}</Button>}
          title={`Remove ${item.displayName}?`}
          description="Applied grocery deductions must be reversed first. Removing an item cannot be undone."
          confirmLabel="Remove pantry item"
          onConfirm={() => remove.mutate()}
        />
      </div>
    </article>
  );
}

export function PantryPage() {
  const queryClient = useQueryClient();
  const items = useQuery({ queryKey: ["pantry-items"], queryFn: pantryApi.list });
  const [draft, setDraft] = useState<PantryItemWrite>({
    displayName: "",
    quantity: "",
    unit: "g",
    foodReferenceId: null,
  });
  const [recipeQuery, setRecipeQuery] = useState("");
  const [searchEnabled, setSearchEnabled] = useState(false);
  const matches = useQuery({
    queryKey: ["pantry-recipe-matches", recipeQuery],
    queryFn: () => pantryApi.search(recipeQuery),
    enabled: searchEnabled,
  });
  const create = useMutation({
    mutationFn: () => pantryApi.create(draft),
    onSuccess: () => {
      setDraft({ displayName: "", quantity: "", unit: "g", foodReferenceId: null });
      void queryClient.invalidateQueries({ queryKey: ["pantry-items"] });
    },
  });

  if (items.isPending) return <Skeleton label="Loading pantry" lines={8} />;
  if (items.isError) return <ErrorRecovery title="Pantry could not be loaded" onRetry={() => void items.refetch()} />;

  return (
    <main className="page-shell">
      <PageHeader eyebrow="Inventory and availability" title="Pantry" description="Track exact quantities, review food identities, and see what is actually makeable without guessing conversions." actions={<Button asChild className="button--secondary"><Link to="/app/grocery">Open grocery list</Link></Button>} />

      <section className="pantry-section">
        <div className="section-heading"><div><h2>Add pantry food</h2><p className="muted">Mass, volume, and count remain separate dimensions.</p></div></div>
        <form className="pantry-create" onSubmit={(event) => { event.preventDefault(); create.mutate(); }}>
          <Field label="Food name"><input className="input" value={draft.displayName} onChange={(event) => { const displayName = event.currentTarget.value; setDraft((value) => ({ ...value, displayName })); }} /></Field>
          <Field label="Quantity"><DecimalInput value={draft.quantity} onValueChange={(quantity) => setDraft((value) => ({ ...value, quantity }))} /></Field>
          <Field label="Unit"><select className="input" value={draft.unit} onChange={(event) => { const unit = event.currentTarget.value; setDraft((value) => ({ ...value, unit })); }}>{UNITS.map((value) => <option key={value}>{value}</option>)}</select></Field>
          <Button type="submit" disabled={!draft.displayName.trim() || !draft.quantity || create.isPending}>Add pantry item</Button>
        </form>
        {create.error instanceof Error ? <p className="error-text" role="alert">{create.error.message}</p> : null}
      </section>

      <section className="pantry-section">
        <div className="section-heading"><h2>Inventory</h2><span className="data-value">{items.data.length} item{items.data.length === 1 ? "" : "s"}</span></div>
        {items.data.length ? <div className="pantry-grid">{items.data.map((item) => <PantryItemCard item={item} key={item.id} />)}</div> : <EmptyState title="Your pantry is empty" description="Add only what you can identify and measure. Unknown amounts should stay out of automatic availability checks." />}
      </section>

      <section className="pantry-section">
        <div><h2>Makeable recipes</h2><p className="muted">Proposed and unmatched foods are excluded until reviewed.</p></div>
        <div className="pantry-search"><Field label="Recipe title filter"><input className="input" value={recipeQuery} onChange={(event) => { setRecipeQuery(event.currentTarget.value); setSearchEnabled(false); }} /></Field><Button onClick={() => setSearchEnabled(true)}>Find makeable recipes</Button></div>
        {matches.isFetching ? <p role="status">Checking exact pantry coverage…</p> : null}
        {matches.isError ? <ErrorRecovery title="Recipe availability could not be checked" onRetry={() => void matches.refetch()} /> : null}
        {matches.data?.length ? <div className="pantry-results">{matches.data.map((match) => <article className="pantry-result" aria-label={match.recipeTitle} key={match.recipeId}><div className="pantry-card__heading"><h3><Link to={`/app/recipes/${match.recipeId}`}>{match.recipeTitle}</Link></h3><span className={`match-badge match-badge--${match.availability}`}>{match.availability === "full" ? "Fully makeable" : match.availability === "partial" ? "Partially makeable" : "Not makeable"}</span></div><p className="data-value">{Math.round(Number(match.coverageRatio) * 100)}% of required ingredients covered</p>{match.missingIngredients.length ? <div><strong>Still needed</strong><ul>{match.missingIngredients.map((value) => <li key={value}>{value}</li>)}</ul></div> : <p className="success-text">No required ingredients missing.</p>}</article>)}</div> : searchEnabled && matches.data ? <EmptyState title="No recipes found" description="Try a different title filter or add recipes first." /> : null}
      </section>
    </main>
  );
}
