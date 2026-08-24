import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import * as Dialog from "@radix-ui/react-dialog";
import { ArrowRight, CalendarClock, PackagePlus, Search, Sparkles } from "lucide-react";
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
import { FoodCategoryIcon } from "../../components/FoodCategoryIcon";
import { RecipeFallbackArt } from "../../components/cookfully/RecipeFallbackArt";
import { RecipeMedia, type RecipeMediaSource } from "../../components/cookfully/RecipeMedia";
import { ApiProblem } from "../recipes/api";
import { formatCookingInput, formatCookingNumber } from "../recipes/formatCooking";
import { RecipeMetadata } from "../recipes/RecipeMetadata";
import { planningApi } from "../plans/api";
import { todayInTimezone } from "../plans/dates";
import { pantryApi } from "./api";
import { expiryBadge } from "./expiry";
import type { PantryItem, PantryItemWrite, PantryRecipeMatch } from "./types";

const UNITS = ["g", "kg", "mg", "ml", "l", "count"] as const;

function weekdayLabel(value: string) {
  return new Intl.DateTimeFormat("en-CA", { weekday: "long", timeZone: "UTC" }).format(new Date(`${value}T00:00:00Z`));
}

function formatUseBy(value: string) {
  return new Intl.DateTimeFormat("en-CA", { month: "short", day: "numeric", timeZone: "UTC" }).format(new Date(`${value}T00:00:00Z`));
}

const MATCH_ORDER = new Map([["proposed", 0], ["unmatched", 1], ["matched", 2], ["manual", 2]]);

function matchLabel(item: PantryItem) {
  if (item.matchStatus === "matched" || item.matchStatus === "manual") return "Ready to use";
  if (item.matchStatus === "proposed") return `Review match${item.matchConfidence ? ` · ${Math.round(Number(item.matchConfidence) * 100)}%` : ""}`;
  return "Needs a match";
}

function PantryItemCard({ item, today }: { item: PantryItem; today: string }) {
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

  const expiry = item.expiresOn ? expiryBadge(item.expiresOn, today) : null;
  const usebyTone = expiry ? (expiry.tone === "mint" ? "later" : expiry.tone === "amber" ? "soon" : "critical") : "none";
  return (
    <article className={`pantry-staple${item.matchStatus === "proposed" ? " pantry-staple--review" : ""}`} aria-label={item.displayName}>
      <span className="pantry-staple__stamp pantry-staple__stamp--icon" aria-hidden="true"><FoodCategoryIcon name={item.displayName} size="tile" /></span>
      <div className="pantry-staple__body">
        <header className="pantry-staple__heading">
          <h3>{item.displayName}</h3>
          <span className={`match-badge match-badge--${item.matchStatus}`}>{matchLabel(item)}</span>
        </header>
        <p className="pantry-staple__facts">
          <span className="pantry-staple__quantity">{formatCookingNumber(item.quantity)} {item.unit}</span>
          {expiry ? (
            <span className={`pantry-staple__useby pantry-staple__useby--${usebyTone} expiry-chip expiry-chip--${expiry.tone}`} aria-label={`Expires ${item.expiresOn}`}>
              <CalendarClock aria-hidden="true" />
              Use by {formatUseBy(item.expiresOn!)} · {expiry.label}
            </span>
          ) : (
            <span className="pantry-staple__useby pantry-staple__useby--none">No date</span>
          )}
        </p>
        {item.matchStatus === "proposed" ? (
          <p className="pantry-staple__note">Confirm this food match before Cookfully uses it for recipe ideas or pantry deductions.</p>
        ) : item.matchStatus === "unmatched" ? (
          <p className="pantry-staple__note pantry-staple__note--quiet">This stays on your inventory, but Cookfully will not subtract or match it automatically yet.</p>
        ) : null}
        {error instanceof Error ? <p className="error-text" role="alert">{conflict ? "This pantry item changed. Reload before trying again." : error.message}</p> : null}
        <details className="disclosure pantry-staple__edit"><summary>Edit {item.displayName}</summary><form className="pantry-edit" onSubmit={save}>
          <Field label={`${item.displayName} food name`}>
            <input className="input" value={displayName} onChange={(event) => setDisplayName(event.currentTarget.value)} />
          </Field>
          <div className="pantry-edit__row">
            <Field label={`${item.displayName} quantity`}>
              <DecimalInput value={quantity} onValueChange={setQuantity} />
            </Field>
            <Field label={`${item.displayName} unit`}>
              <Select value={unit} onChange={(event) => setUnit(event.currentTarget.value)}>
                {UNITS.map((value) => <option key={value}>{value}</option>)}
              </Select>
            </Field>
          </div>
          <div className="pantry-edit__row">
            <Field label={`${item.displayName} use-by date`} hint="Optional. Only fresh food benefits from a reminder.">
              <input className="input" type="date" value={expiresOn} onChange={(event) => setExpiresOn(event.currentTarget.value)} />
            </Field>
            <Field label={`${item.displayName} food reference ID`} hint="Optional advanced correction. Clear it to rematch by name.">
              <input className="input" value={referenceId} onChange={(event) => setReferenceId(event.currentTarget.value)} placeholder="UUID" />
            </Field>
          </div>
          <Button variant="secondary" type="submit" disabled={!displayName.trim() || update.isPending || remove.isPending}>Save {item.displayName}</Button>
        </form></details>
        <div className="actions pantry-staple__actions">
          {conflict ? <Button onClick={() => void refresh()}>Reload</Button> : null}
          <ConfirmDialog
            trigger={<Button variant="ghost" disabled={update.isPending || remove.isPending}>Remove {item.displayName}</Button>}
            title={`Remove ${item.displayName}?`}
            description="Applied grocery deductions must be reversed first. Removing an item cannot be undone."
            confirmLabel="Remove pantry item"
            onConfirm={() => remove.mutate()}
          />
        </div>
      </div>
    </article>
  );
}

function AttentionRow({ item, tone, urgency }: { item: PantryItem; tone: string; urgency: string }) {
  return (
    <article className={`pantry-attention__item${tone === "critical" ? " pantry-attention__item--critical" : ""}`}>
      <span className="pantry-attention__icon pantry-attention__icon--has-icon" aria-hidden="true"><FoodCategoryIcon name={item.displayName} size="row" /></span>
      <div>
        <strong>{item.displayName}</strong>
        <small>{formatCookingNumber(item.quantity)} {item.unit} · Use by {formatUseBy(item.expiresOn!)}</small>
      </div>
      <span className={`pantry-attention__urgency pantry-attention__urgency--${tone}`}>{urgency}</span>
    </article>
  );
}

function MatchResultCard({ match, recipe }: { match: PantryRecipeMatch; recipe?: RecipeMediaSource }) {
  const coverage = Math.round(Number(match.coverageRatio) * 100);
  const availabilityLabel = match.availability === "full" ? "Fully makeable" : match.availability === "partial" ? "Partially makeable" : "Not makeable";
  return (
    <article className="pantry-match" aria-label={match.recipeTitle}>
      <Link className="pantry-match__media" to={`/app/recipes/${match.recipeId}`} tabIndex={-1} aria-hidden="true">
        {recipe ? <RecipeMedia recipe={recipe} loading="eager" /> : <RecipeFallbackArt title={match.recipeTitle} />}
      </Link>
      <div className="pantry-match__body">
        <header className="pantry-match__heading">
          <h3><Link to={`/app/recipes/${match.recipeId}`}>{match.recipeTitle}</Link></h3>
          <span className={`match-badge match-badge--${match.availability}`}>{availabilityLabel}</span>
        </header>
        {recipe ? <RecipeMetadata recipe={recipe} compact /> : null}
        <p className="pantry-match__coverage">
          <strong>{coverage}%</strong> of required ingredients are already on your shelf.
        </p>
        {match.missingIngredients.length ? (
          <div className="pantry-match__gaps">
            <span className="eyebrow">Still needed</span>
            <ul>
              {match.missingIngredients.slice(0, 4).map((value) => <li key={value}>{value}</li>)}
              {match.missingIngredients.length > 4 ? <li className="pantry-match__more">+{match.missingIngredients.length - 4} more</li> : null}
            </ul>
          </div>
        ) : (
          <p className="success-text pantry-match__done">Nothing missing — this one is ready when you are.</p>
        )}
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
  const datedItems = items.data.filter((item) => item.expiresOn);
  const expiredItems = datedItems.filter((item) => item.expiresOn! < today).sort((a, b) => a.expiresOn!.localeCompare(b.expiresOn!));
  const useSoonItems = datedItems.filter((item) => item.expiresOn! >= today).sort((a, b) => a.expiresOn!.localeCompare(b.expiresOn!));
  const readyCount = items.data.filter((item) => item.matchStatus === "matched" || item.matchStatus === "manual").length;
  const reviewCount = items.data.length - readyCount;
  const shelf = [...items.data].sort((a, b) => (a.expiresOn ? 0 : 1) - (b.expiresOn ? 0 : 1) || (a.expiresOn || "").localeCompare(b.expiresOn || "") || (MATCH_ORDER.get(a.matchStatus) ?? 3) - (MATCH_ORDER.get(b.matchStatus) ?? 3));
  const recipesById = new Map((recipes.data?.items ?? []).map((recipe) => [recipe.id, recipe]));

  const pulse = [
    { label: "On hand", value: items.data.length },
    { label: "Ready to cook with", value: readyCount },
    { label: reviewCount ? "Need your review" : "Nothing to review", value: reviewCount, href: reviewCount ? "#pantry-shelf" : undefined, attention: reviewCount > 0 },
    { label: "Use soon", value: useSoonItems.length, href: useSoonItems.length ? "#pantry-use-soon" : undefined },
  ];

  return (
    <main className="page-shell pantry-page">
      <PageHeader
        eyebrow={`Your kitchen · ${weekdayLabel(today)}`}
        title="What’s already at home?"
        description="Keep a lightweight inventory of staples and ingredients so weekly prep starts with what you already have."
        actions={<><AddPantryDialog trigger={<Button><PackagePlus aria-hidden="true" />Add item</Button>} /><Button asChild variant="secondary"><Link to="/app/grocery">Open grocery list</Link></Button></>}
      />

      <nav className="pantry-pulse" aria-label="Shelf at a glance">
        {pulse.map((stat) => {
          const content = <>
            <strong>{stat.value}</strong>
            <span>{stat.label}</span>
          </>;
          return stat.href ? (
            <a key={stat.label} className={`pantry-pulse__stat${stat.attention ? " pantry-pulse__stat--attention" : ""}`} href={stat.href}>
              {content}
              <ArrowRight aria-hidden="true" />
            </a>
          ) : (
            <div key={stat.label} className="pantry-pulse__stat">{content}</div>
          );
        })}
      </nav>

      <section className={`pantry-attention${useSoonItems.length || expiredItems.length ? "" : " pantry-attention--calm"}`} id="pantry-use-soon" aria-labelledby="pantry-use-soon-title">
        <SectionHeading
          eyebrow="Use soon"
          title={expiredItems.length ? `${expiredItems.length} item${expiredItems.length === 1 ? "" : "s"} past their best` : useSoonItems.length ? "Cook these before they’re forgotten" : "Nothing needs attention yet"}
          description={
            expiredItems.length ? "These passed their use-by date. Check them before cooking or planning with them."
            : useSoonItems.length ? "The nearest dates lead the list, so dinner can solve waste before it starts."
            : "Add dates only to fresh food that benefits from a reminder. Shelf-stable staples can stay undated."
          }
          id="pantry-use-soon-title"
          action={useSoonItems.length || expiredItems.length ? <Button asChild variant="ghost"><a href="#pantry-shelf">Review the shelf</a></Button> : undefined}
        />
        {expiredItems.length || useSoonItems.length ? (
          <div className="pantry-attention__items">
            {expiredItems.slice(0, 4).map((item) => {
              const badge = expiryBadge(item.expiresOn!, today);
              return <AttentionRow key={item.id} item={item} tone={badge.tone === "danger" ? "critical" : badge.tone} urgency={badge.label} />;
            })}
            {useSoonItems.slice(0, expiredItems.length ? 2 : 4).map((item) => {
              const badge = expiryBadge(item.expiresOn!, today);
              const tone = badge.tone === "mint" ? "later" : badge.tone === "amber" ? "soon" : "critical";
              return <AttentionRow key={item.id} item={item} tone={tone} urgency={badge.label} />;
            })}
          </div>
        ) : (
          <span className="pantry-attention__companion" aria-hidden="true"><KitchenCompanion moment="empty" size="sm" /></span>
        )}
      </section>

      <section className="pantry-section pantry-section--inventory" id="pantry-shelf">
        <SectionHeading eyebrow="Your shelf" title="On hand" meta={`${items.data.length} item${items.data.length === 1 ? "" : "s"}`} />
        {shelf.length ? (
          <div className="pantry-grid">
            {shelf.map((item) => <PantryItemCard item={item} today={today} key={item.id} />)}
          </div>
        ) : (
          <div className="pantry-empty">
            <div className="pantry-empty__intro"><KitchenCompanion moment="empty" size="md" /><div><h3>Start with what you reach for</h3><p>Rough quantities are completely fine. A small, current shelf is more useful than a perfect inventory.</p><AddPantryDialog trigger={<Button>Add your first item</Button>} /></div></div>
            <div className="pantry-empty__starters"><p className="eyebrow">Good first items</p><h3>Pick a staple</h3><p>Choose one to start with its name already filled in.</p><div>{["Rice", "Eggs", "Oats", "Frozen vegetables"].map((name) => <AddPantryDialog key={name} prefillName={name} trigger={<Button variant="secondary">{name}</Button>} />)}</div></div>
          </div>
        )}
      </section>

      {items.data.length ? (
        <section className="pantry-section pantry-cook" id="pantry-cook">
          <SectionHeading
            eyebrow="Use what you have"
            title="Cook from your shelf"
            description="Compare your recipes with what is on hand. Ingredients awaiting a match stay out until you review them."
            action={<span className="pantry-cook__hint" aria-hidden="true"><Sparkles /> Shelf-aware ideas</span>}
          />
          <div className="pantry-search">
            <SearchField
              label="Recipe name (optional)"
              value={recipeQuery}
              onChange={(event) => { setRecipeQuery(event.currentTarget.value); setSearchEnabled(false); }}
              onClear={() => { setRecipeQuery(""); setSearchEnabled(false); }}
              placeholder="Leave empty to check every recipe"
            />
            <Button onClick={() => setSearchEnabled(true)}><Search aria-hidden="true" />Find recipes</Button>
          </div>
          {matches.isFetching ? <p className="muted" role="status">Comparing recipes with your pantry…</p> : null}
          {matches.isError ? <ErrorRecovery title="Recipe availability could not be checked" onRetry={() => void matches.refetch()} /> : null}
          {matches.data?.length ? (
            <div className="pantry-results">
              {matches.data.map((match) => <MatchResultCard key={match.recipeId} match={match} recipe={recipesById.get(match.recipeId)} />)}
            </div>
          ) : searchEnabled && matches.data ? (
            <EmptyState title="No recipes found" description="Try a different title filter or add recipes first." />
          ) : null}
          <p className="pantry-cook__more muted">
            <ArrowRight aria-hidden="true" />
            Matches improve as you confirm foods in <Link to="/app/foods">your food library</Link>.
          </p>
        </section>
      ) : null}
    </main>
  );
}
