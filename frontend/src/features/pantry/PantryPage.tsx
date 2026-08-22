import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import * as Dialog from "@radix-ui/react-dialog";
import { CalendarClock, PackagePlus, Search } from "lucide-react";
import { type FormEvent, type ReactNode, useEffect, useState } from "react";
import { Link } from "react-router-dom";

import {
  Button,
  ConfirmDialog,
  DecimalInput,
  DialogCloseButton,
  EmptyState,
  ErrorRecovery,
  Field,
  KitchenCompanion,
  PageHeader,
  PageState,
  SearchField,
  SectionHeading,
  Select,
  Skeleton,
} from "../../components";
import { ApiProblem } from "../recipes/api";
import { formatCookingInput, formatCookingNumber } from "../recipes/formatCooking";
import { RecipeMetadata } from "../recipes/RecipeMetadata";
import { planningApi } from "../plans/api";
import { todayInTimezone } from "../plans/dates";
import { pantryApi } from "./api";
import type { PantryItem, PantryItemWrite } from "./types";

const UNITS = ["g", "kg", "mg", "ml", "l", "count"] as const;

function formatUseBy(value: string) {
  return new Intl.DateTimeFormat("en-CA", { month: "short", day: "numeric", timeZone: "UTC" }).format(new Date(`${value}T00:00:00Z`));
}

function formatUseByUrgency(value: string, todayValue: string) {
  const today = new Date(`${todayValue}T00:00:00Z`);
  const expires = new Date(`${value}T00:00:00Z`);
  const days = Math.round((expires.getTime() - today.getTime()) / 86_400_000);
  if (days < 0) return "Past use-by";
  if (days === 0) return "Use today";
  if (days === 1) return "1 day left";
  return `${days} days left`;
}

function PantryItemCard({ item }: { item: PantryItem }) {
  const queryClient = useQueryClient();
  const [displayName, setDisplayName] = useState(item.displayName);
  const [quantity, setQuantity] = useState(formatCookingInput(item.quantity));
  const [unit, setUnit] = useState(item.unit);
  const [expiresOn, setExpiresOn] = useState(item.expiresOn ?? "");
  const [referenceId, setReferenceId] = useState(item.foodReferenceId ?? "");
  useEffect(() => {
    setDisplayName(item.displayName);
    setQuantity(formatCookingInput(item.quantity));
    setUnit(item.unit);
    setExpiresOn(item.expiresOn ?? "");
    setReferenceId(item.foodReferenceId ?? "");
  }, [item]);
  const refresh = () => queryClient.invalidateQueries({ queryKey: ["pantry-items"] });
  const update = useMutation({
    mutationFn: (value: PantryItemWrite) => pantryApi.update(item.id, item.version, value),
    onMutate: async (value) => {
      await queryClient.cancelQueries({ queryKey: ["pantry-items"] });
      const previous = queryClient.getQueryData<PantryItem[]>(["pantry-items"]);
      queryClient.setQueryData<PantryItem[]>(["pantry-items"], (current) => current?.map((candidate) => candidate.id === item.id
        ? { ...candidate, ...value, displayName: value.displayName ?? candidate.displayName, quantity: value.quantity ?? candidate.quantity, unit: value.unit ?? candidate.unit, expiresOn: value.expiresOn ?? candidate.expiresOn, foodReferenceId: value.foodReferenceId ?? candidate.foodReferenceId }
        : candidate));
      return { previous };
    },
    onError: (_error, _value, context) => {
      if (context?.previous) queryClient.setQueryData(["pantry-items"], context.previous);
    },
    onSuccess: (saved) => {
      queryClient.setQueryData<PantryItem[]>(["pantry-items"], (current) => current?.map((candidate) => candidate.id === saved.id ? saved : candidate));
      void refresh();
    },
  });
  const remove = useMutation({
    mutationFn: () => pantryApi.remove(item.id, item.version),
    onMutate: async () => {
      await queryClient.cancelQueries({ queryKey: ["pantry-items"] });
      const previous = queryClient.getQueryData<PantryItem[]>(["pantry-items"]);
      queryClient.setQueryData<PantryItem[]>(["pantry-items"], (current) => current?.filter((candidate) => candidate.id !== item.id));
      return { previous };
    },
    onError: (_error, _value, context) => {
      if (context?.previous) queryClient.setQueryData(["pantry-items"], context.previous);
    },
    onSuccess: () => void refresh(),
  });
  const error = update.error ?? remove.error;
  const conflict = error instanceof ApiProblem && error.status === 409;
  const matchLabel = item.matchStatus === "matched" || item.matchStatus === "manual"
    ? "Ready to use"
    : item.matchStatus === "proposed" ? "Review match" : "Needs a match";

  function save(event: FormEvent) {
    event.preventDefault();
    update.mutate({
      displayName: displayName.trim(),
      quantity,
      unit,
      expiresOn: expiresOn || null,
      foodReferenceId: referenceId.trim() || null,
    });
  }

  return (
    <article className="pantry-card" aria-label={item.displayName}>
      <div className="pantry-card__heading">
        <div>
          <h3>{item.displayName}</h3>
          <p className="data-value">{formatCookingNumber(item.quantity)} {item.unit}{item.expiresOn ? ` · Use by ${formatUseBy(item.expiresOn)}` : ""}</p>
        </div>
        <span className={`match-badge match-badge--${item.matchStatus}`}>
          {matchLabel}
          {item.matchConfidence ? ` · ${Math.round(Number(item.matchConfidence) * 100)}%` : ""}
        </span>
      </div>
      {item.matchStatus === "proposed" ? (
        <p className="notice">Confirm this food match before Cookfully uses it for recipe ideas or pantry deductions.</p>
      ) : item.matchStatus === "unmatched" ? (
        <p className="muted">This stays on your inventory, but Cookfully will not subtract or match it automatically yet.</p>
      ) : null}
      <details className="disclosure"><summary>Edit {item.displayName}</summary><form className="pantry-edit" onSubmit={save}>
        <Field label={`${item.displayName} food name`}>
          <input className="input" value={displayName} onChange={(event) => setDisplayName(event.currentTarget.value)} />
        </Field>
        <Field label={`${item.displayName} quantity`}>
          <DecimalInput value={quantity} onValueChange={setQuantity} />
        </Field>
        <Field label={`${item.displayName} unit`}>
          <Select value={unit} onChange={(event) => setUnit(event.currentTarget.value)}>
            {UNITS.map((value) => <option key={value}>{value}</option>)}
          </Select>
        </Field>
        <Field label={`${item.displayName} use-by date`} hint="Optional. Used only to surface food that deserves attention soon.">
          <input className="input" type="date" value={expiresOn} onChange={(event) => setExpiresOn(event.currentTarget.value)} />
        </Field>
        <Field label={`${item.displayName} food reference ID`} hint="Optional advanced correction. Clear it to rematch by name.">
          <input className="input" value={referenceId} onChange={(event) => setReferenceId(event.currentTarget.value)} placeholder="UUID" />
        </Field>
        <Button variant="secondary" type="submit" disabled={!displayName.trim() || update.isPending || remove.isPending}>Save {item.displayName}</Button>
      </form></details>
      {error instanceof Error ? <p className="error-text" role="alert">{conflict ? "This pantry item changed. Reload before trying again." : error.message}</p> : null}
      <div className="actions">
        {conflict ? <Button onClick={() => void refresh()}>Reload</Button> : null}
        <ConfirmDialog
          trigger={<Button variant="ghost" disabled={update.isPending || remove.isPending}>Remove {item.displayName}</Button>}
          title={`Remove ${item.displayName}?`}
          description="Applied grocery deductions must be reversed first. Removing an item cannot be undone."
          confirmLabel="Remove pantry item"
          onConfirm={() => remove.mutate()}
        />
      </div>
    </article>
  );
}

function AddPantryDialog({ trigger, prefillName = "" }: { trigger: ReactNode; prefillName?: string }) {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState<PantryItemWrite>({
    displayName: prefillName,
    quantity: "",
    unit: "g",
    expiresOn: null,
    foodReferenceId: null,
  });
  const create = useMutation({
    mutationFn: () => pantryApi.create(draft),
    onSuccess: () => {
      setOpen(false);
      setDraft({ displayName: prefillName, quantity: "", unit: "g", expiresOn: null, foodReferenceId: null });
      void queryClient.invalidateQueries({ queryKey: ["pantry-items"] });
    },
  });

  return (
    <Dialog.Root open={open} onOpenChange={(value) => {
      setOpen(value);
      if (!value) setDraft({ displayName: prefillName, quantity: "", unit: "g", expiresOn: null, foodReferenceId: null });
    }}>
      <Dialog.Trigger asChild>{trigger}</Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Overlay className="dialog-overlay" />
        <Dialog.Content className="dialog pantry-dialog" aria-describedby="add-pantry-description">
          <header className="pantry-dialog__header">
            <div>
              <p className="eyebrow">Keep the shelf current</p>
              <Dialog.Title>Add something on hand</Dialog.Title>
              <Dialog.Description id="add-pantry-description" className="pantry-dialog__description">A useful name and rough quantity are enough. You can refine the match later.</Dialog.Description>
            </div>
            <DialogCloseButton label="Close add pantry item dialog" />
          </header>
          <form className="pantry-dialog__form" onSubmit={(event) => { event.preventDefault(); create.mutate(); }}>
            <Field label="Food name" hint="Use the name you would put on a shopping list.">
              <input className="input" value={draft.displayName} onChange={(event) => { const displayName = event.currentTarget.value; setDraft((value) => ({ ...value, displayName })); }} placeholder="Brown rice" autoFocus />
            </Field>
            <div className="pantry-dialog__quantity">
              <Field label="Quantity"><DecimalInput value={draft.quantity} onValueChange={(quantity) => setDraft((value) => ({ ...value, quantity }))} placeholder="500" /></Field>
              <Field label="Unit"><Select value={draft.unit} onChange={(event) => { const unit = event.currentTarget.value; setDraft((value) => ({ ...value, unit })); }}>{UNITS.map((value) => <option key={value}>{value}</option>)}</Select></Field>
            </div>
            <Field label="Use-by date (optional)" hint="Add one when timing matters; shelf-stable food can stay undated.">
              <input className="input" type="date" value={draft.expiresOn ?? ""} onChange={(event) => { const expiresOn = event.currentTarget.value || null; setDraft((value) => ({ ...value, expiresOn })); }} />
            </Field>
            {create.error instanceof Error ? <p className="error-text pantry-dialog__error" role="alert">{create.error.message}</p> : null}
            <div className="pantry-dialog__actions">
              <Dialog.Close asChild><Button type="button" variant="secondary">Cancel</Button></Dialog.Close>
              <Button type="submit" disabled={!draft.displayName.trim() || !draft.quantity || create.isPending}>{create.isPending ? "Adding…" : "Add to pantry"}</Button>
            </div>
          </form>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

export function PantryPage() {
  const preferences = useQuery({ queryKey: ["owner-preferences"], queryFn: planningApi.preferences });
  const items = useQuery({ queryKey: ["pantry-items"], queryFn: pantryApi.list });
  const [recipeQuery, setRecipeQuery] = useState("");
  const [searchEnabled, setSearchEnabled] = useState(false);
  const matches = useQuery({
    queryKey: ["pantry-recipe-matches", recipeQuery],
    queryFn: () => pantryApi.search(recipeQuery),
    enabled: searchEnabled,
  });
  const recipes = useQuery({ queryKey: ["planning-recipes"], queryFn: ({ signal }) => planningApi.recipes("", signal), enabled: searchEnabled });
  if (items.isPending || preferences.isPending) return <PageState><Skeleton label="Loading pantry" lines={8} /></PageState>;
  if (preferences.isError) return <PageState><ErrorRecovery title="Calendar preferences could not be loaded" onRetry={() => void preferences.refetch()} /></PageState>;
  if (items.isError) return <PageState><ErrorRecovery title="Pantry could not be loaded" onRetry={() => void items.refetch()} /></PageState>;
  const today = todayInTimezone(preferences.data.timezone);
  const datedItems = items.data
    .filter((item) => item.expiresOn)
    .sort((a, b) => a.expiresOn!.localeCompare(b.expiresOn!));
  const expiredItems = datedItems.filter((item) => item.expiresOn! < today);
  const useSoonItems = datedItems.filter((item) => item.expiresOn! >= today);
  const recipesById = new Map((recipes.data?.items ?? []).map((recipe) => [recipe.id, recipe]));

  return (
    <main className="page-shell pantry-page">
      <PageHeader eyebrow="Your kitchen" title="What’s already at home?" description="Keep a lightweight inventory of staples and ingredients so weekly prep starts with what you already have." actions={<><AddPantryDialog trigger={<Button><PackagePlus aria-hidden="true" />Add item</Button>} /><Button asChild variant="secondary"><Link to="/app/grocery">Open grocery list</Link></Button></>} />

      <section className="pantry-attention" aria-labelledby="pantry-use-soon-title">
        <SectionHeading
          eyebrow="Use soon"
          title={useSoonItems.length ? "Cook these before they’re forgotten" : "Nothing needs attention yet"}
          description={useSoonItems.length ? "The nearest use-by dates lead the shelf, so dinner can solve waste before it starts." : "Add dates only to fresh food that benefits from a reminder. Shelf-stable staples can stay undated."}
          id="pantry-use-soon-title"
          action={<Button asChild variant="ghost"><a href="#pantry-shelf">Review the shelf</a></Button>}
        />
        {useSoonItems.length ? <div className="pantry-attention__items">{useSoonItems.slice(0, 4).map((item) => <article key={item.id} className="pantry-attention__item"><span className="pantry-attention__icon" aria-hidden="true"><CalendarClock /></span><div><strong>{item.displayName}</strong><small>{formatCookingNumber(item.quantity)} {item.unit} · Use by {formatUseBy(item.expiresOn!)}</small></div><span className="pantry-attention__urgency">{formatUseByUrgency(item.expiresOn!, today)}</span></article>)}</div> : null}
      </section>

      {expiredItems.length ? <section className="pantry-attention pantry-attention--expired" aria-labelledby="pantry-expired-title">
        <SectionHeading
          eyebrow="Expired"
          title={`${expiredItems.length} item${expiredItems.length === 1 ? "" : "s"} past use-by`}
          description="These items are no longer in the use-soon window. Check them before planning with them."
          id="pantry-expired-title"
        />
        <div className="pantry-attention__items">{expiredItems.slice(0, 4).map((item) => <article key={item.id} className="pantry-attention__item pantry-attention__item--expired"><span className="pantry-attention__icon" aria-hidden="true"><CalendarClock /></span><div><strong>{item.displayName}</strong><small>{formatCookingNumber(item.quantity)} {item.unit} · Use by {formatUseBy(item.expiresOn!)}</small></div><span className="pantry-attention__urgency">Past use-by</span></article>)}</div>
      </section> : null}

      <section className="pantry-section pantry-section--inventory" id="pantry-shelf">
        <SectionHeading eyebrow="Your shelf" title="On hand" meta={`${items.data.length} item${items.data.length === 1 ? "" : "s"}`} />
        {items.data.length ? <div className="pantry-grid">{items.data.map((item) => <PantryItemCard item={item} key={item.id} />)}</div> : <div className="pantry-empty">
          <div className="pantry-empty__intro"><KitchenCompanion moment="empty" size="md" /><div><h3>Start with what you reach for</h3><p>Rough quantities are completely fine. A small, current shelf is more useful than a perfect inventory.</p><AddPantryDialog trigger={<Button>Add your first item</Button>} /></div></div>
          <div className="pantry-empty__starters"><p className="eyebrow">Good first items</p><h3>Pick a staple</h3><p>Choose one to start with its name already filled in.</p><div>{["Rice", "Eggs", "Oats", "Frozen vegetables"].map((name) => <AddPantryDialog key={name} prefillName={name} trigger={<Button variant="secondary">{name}</Button>} />)}</div></div>
        </div>}
      </section>

      {items.data.length ? <section className="pantry-section pantry-section--matches">
        <div className="pantry-discovery__intro"><span className="pantry-discovery__mark" aria-hidden="true"><Search /></span><div><p className="eyebrow">Use what you have</p><h2>Find a meal from your shelf</h2><p className="muted">Compare your recipes with what is on hand. Ingredients awaiting a match stay out until you review them.</p></div></div>
        <div className="pantry-search"><SearchField label="Recipe name (optional)" value={recipeQuery} onChange={(event) => { setRecipeQuery(event.currentTarget.value); setSearchEnabled(false); }} onClear={() => { setRecipeQuery(""); setSearchEnabled(false); }} placeholder="Leave empty to check every recipe" /><Button onClick={() => setSearchEnabled(true)}>Find recipes</Button></div>
        {matches.isFetching ? <p role="status">Comparing recipes with your pantry…</p> : null}
        {matches.isError ? <ErrorRecovery title="Recipe availability could not be checked" onRetry={() => void matches.refetch()} /> : null}
        {matches.data?.length ? <div className="pantry-results">{matches.data.map((match) => { const recipe = recipesById.get(match.recipeId); return <article className="pantry-result" aria-label={match.recipeTitle} key={match.recipeId}><div className="pantry-card__heading"><h3><Link to={`/app/recipes/${match.recipeId}`}>{match.recipeTitle}</Link></h3><span className={`match-badge match-badge--${match.availability}`}>{match.availability === "full" ? "Fully makeable" : match.availability === "partial" ? "Partially makeable" : "Not makeable"}</span></div>{recipe ? <RecipeMetadata recipe={recipe} compact /> : null}<p className="data-value">{Math.round(Number(match.coverageRatio) * 100)}% of required ingredients covered</p>{match.missingIngredients.length ? <div><strong>Still needed</strong><ul>{match.missingIngredients.map((value) => <li key={value}>{value}</li>)}</ul></div> : <p className="success-text">No required ingredients missing.</p>}</article>; })}</div> : searchEnabled && matches.data ? <EmptyState title="No recipes found" description="Try a different title filter or add recipes first." /> : null}
      </section> : null}
    </main>
  );
}
