import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";
import { useEffect, useMemo, useRef, useState } from "react";
import { ChevronDown, FileDown, Plus, SlidersHorizontal } from "lucide-react";

import { Button, EmptyState, ErrorRecovery, Field, PageHeader, SearchField, SectionHeading, Select, Skeleton, TabList } from "../../components";
import { recipesApi } from "./api";
import { RecipeCard } from "./RecipeCard";
import { BulkRecipeActions } from "./BulkRecipeActions";
import { RecipeCollectionManager } from "./RecipeCollectionManager";
import { RecipeImportDialog } from "./RecipeImportDialog";
import type { RecipePage } from "./types";
import { FirstRunJourney } from "../onboarding/FirstRunJourney";
import { onboardingApi } from "../onboarding/api";
import { Checkbox } from "@/components/ui/checkbox";
import { isRecipeReadyToPlan } from "./recipeEligibility";

export function RecipeLibraryPage() {
  const queryClient = useQueryClient();
  const [searchParams, setSearchParams] = useSearchParams();
  const addMenuRef = useRef<HTMLDetailsElement>(null);
  const [importOpen, setImportOpen] = useState(searchParams.get("import") === "1");
  const [query, setQuery] = useState("");
  const [libraryView, setLibraryView] = useState<"all" | "ready" | "attention" | "archived">("all");
  const [sortBy, setSortBy] = useState<"updated" | "title-asc" | "title-desc" | "protein" | "calories">("updated");
  const [groupBy, setGroupBy] = useState<"none" | "readiness">("none");
  const [favoriteOnly, setFavoriteOnly] = useState(false);
  const [collectionId, setCollectionId] = useState("");
  const [mealRole, setMealRole] = useState("");
  const [selectionMode, setSelectionMode] = useState(false);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [bulkMessage, setBulkMessage] = useState("");
  const [extraPages, setExtraPages] = useState<RecipePage[]>([]);
  useEffect(() => {
    if (searchParams.get("import") === "1") setImportOpen(true);
  }, [searchParams]);
  const unfiled = collectionId === "__unfiled__";
  const collections = useQuery({ queryKey: ["recipe-collections"], queryFn: recipesApi.collections, retry: 1 });
  const onboarding = useQuery({ queryKey: ["owner-onboarding"], queryFn: onboardingApi.get, retry: 1 });
  const collectionName = (Array.isArray(collections.data) ? collections.data : []).find((collection) => collection.id === collectionId)?.name;
  const activeFilters = [
    favoriteOnly ? { label: "Favorites", clear: () => setFavoriteOnly(false) } : null,
    libraryView !== "all" ? { label: libraryView === "ready" ? "Ready to plan" : libraryView === "attention" ? "Needs attention" : "Archived", clear: () => setLibraryView("all") } : null,
    collectionId ? { label: unfiled ? "Unfiled recipes" : `Collection: ${collectionName ?? "Selected"}`, clear: () => setCollectionId("") } : null,
    mealRole ? { label: `Meal: ${mealRole}`, clear: () => setMealRole("") } : null,
  ].filter((filter): filter is { label: string; clear: () => void } => filter !== null);
  const filters = { query, includeArchived: true, favorite: favoriteOnly || undefined, collectionId: unfiled ? undefined : collectionId || undefined, mealRole: mealRole || undefined };
  const recipes = useQuery({
    queryKey: ["recipes", filters],
    queryFn: () => recipesApi.list(filters),
    retry: 1,
  });
  const filterKey = JSON.stringify(filters);
  useEffect(() => setExtraPages([]), [filterKey]);
  const loadedItems = useMemo(() => [...(recipes.data?.items ?? []), ...extraPages.flatMap((page) => page.items)], [extraPages, recipes.data?.items]);
  const nextCursor = extraPages.at(-1)?.nextCursor ?? recipes.data?.nextCursor;
  const loadMore = useMutation({
    mutationFn: (cursor: string) => recipesApi.list(filters, cursor),
    onSuccess: (page) => setExtraPages((current) => [...current, page]),
  });
  const lifecycle = useMutation({
    mutationFn: async ({ id, version, action }: { id: string; version: number; action: "archive" | "restore" }) => {
      if (action === "archive") await recipesApi.archive(id, version);
      else await recipesApi.restore(id, version);
    },
    onMutate: async ({ id, action }) => {
      setExtraPages((pages) => pages.map((page) => ({ ...page, items: page.items.map((item) => item.id === id ? { ...item, status: action === "archive" ? "archived" : (item.archivedFromStatus ?? "ready") } : item) })));
      await queryClient.cancelQueries({ queryKey: ["recipes"] });
      const snapshots = queryClient.getQueriesData<RecipePage>({ queryKey: ["recipes"] });
      snapshots.forEach(([key, value]) => {
        if (value) queryClient.setQueryData<RecipePage>(key, { ...value, items: value.items.map((item) => item.id === id ? { ...item, status: action === "archive" ? "archived" : (item.archivedFromStatus ?? "ready") } : item) });
      });
      return { snapshots };
    },
    onError: (_error, _variables, context) => context?.snapshots.forEach(([key, value]) => queryClient.setQueryData(key, value)),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["recipes"] }),
  });
  const remove = useMutation({
    mutationFn: async ({ id, version }: { id: string; version: number }) => {
      await recipesApi.archive(id, version);
      const archived = await recipesApi.get(id);
      await recipesApi.permanentDelete(id, archived.version);
    },
    onMutate: async ({ id }) => {
      setExtraPages((pages) => pages.map((page) => ({ ...page, items: page.items.filter((item) => item.id !== id) })));
      await queryClient.cancelQueries({ queryKey: ["recipes"] });
      const snapshots = queryClient.getQueriesData<RecipePage>({ queryKey: ["recipes"] });
      snapshots.forEach(([key, value]) => {
        if (value) queryClient.setQueryData<RecipePage>(key, { ...value, items: value.items.filter((item) => item.id !== id) });
      });
      return { snapshots };
    },
    onError: (_error, _variables, context) => context?.snapshots.forEach(([key, value]) => queryClient.setQueryData(key, value)),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["recipes"] }),
  });
  const bulkArchive = useMutation({
    mutationFn: (items: Array<{ id: string; version: number }>) => recipesApi.bulkArchive(items),
    onMutate: async (items) => {
      const selected = new Set(items.map((item) => item.id));
      setExtraPages((pages) => pages.map((page) => ({ ...page, items: page.items.filter((item) => !selected.has(item.id)) })));
      await queryClient.cancelQueries({ queryKey: ["recipes"] });
      const snapshots = queryClient.getQueriesData<RecipePage>({ queryKey: ["recipes"] });
      snapshots.forEach(([key, value]) => {
        if (value) queryClient.setQueryData<RecipePage>(key, { ...value, items: value.items.filter((item) => !selected.has(item.id)) });
      });
      return { snapshots };
    },
    onError: (_error, _items, context) => {
      context?.snapshots.forEach(([key, value]) => queryClient.setQueryData(key, value));
      setBulkMessage("Archiving failed. Your recipes are still available.");
    },
    onSuccess: (result, _items, context) => {
      const failed = result.results.filter((item) => item.status === "failed");
      const successful = new Set(result.results.filter((item) => item.status !== "failed").map((item) => item.id));
      if (failed.length && context) {
        context.snapshots.forEach(([key, value]) => {
          if (value) queryClient.setQueryData<RecipePage>(key, { ...value, items: value.items.filter((item) => !successful.has(item.id)) });
        });
      }
      const archivedCount = result.results.length - failed.length;
      const archivedMessage = `${archivedCount} ${archivedCount === 1 ? "recipe" : "recipes"} archived.`;
      setBulkMessage(failed.length ? `${archivedMessage} ${failed.length} could not be archived; review the selected recipes and try again.` : archivedMessage);
      setSelectedIds(failed.map((item) => item.id));
      if (!failed.length) setSelectionMode(false);
      void queryClient.invalidateQueries({ queryKey: ["recipes"] });
    },
  });
  const displayedRecipes = useMemo(() => {
    const items = loadedItems.filter((recipe) => {
      if (unfiled && (recipe.collections ?? []).length > 0) return false;
      const ready = isRecipeReadyToPlan(recipe);
      if (libraryView === "ready") return ready;
      if (libraryView === "attention") return recipe.status !== "archived" && !ready;
      if (libraryView === "archived") return recipe.status === "archived";
      return recipe.status !== "archived";
    }) ?? [];
    return [...items].sort((a, b) => {
      if (sortBy === "title-asc") return a.title.localeCompare(b.title);
      if (sortBy === "title-desc") return b.title.localeCompare(a.title);
      if (sortBy === "protein") return Number(b.nutrition?.proteinG ?? -1) - Number(a.nutrition?.proteinG ?? -1);
      if (sortBy === "calories") return Number(a.nutrition?.caloriesKcal ?? Number.POSITIVE_INFINITY) - Number(b.nutrition?.caloriesKcal ?? Number.POSITIVE_INFINITY);
      return new Date(b.updatedAt ?? 0).getTime() - new Date(a.updatedAt ?? 0).getTime();
    });
  }, [libraryView, loadedItems, sortBy, unfiled]);
  const groupedRecipes = groupBy === "readiness"
    ? [
        { title: "Ready to plan", items: displayedRecipes.filter(isRecipeReadyToPlan) },
        { title: "Needs a nutrition check", items: displayedRecipes.filter((recipe) => recipe.status !== "archived" && ["pending", "failed", "stale"].includes(recipe.nutritionState)) },
        { title: "Archived", items: displayedRecipes.filter((recipe) => recipe.status === "archived") },
      ].filter((group) => group.items.length)
    : [{ title: "", items: displayedRecipes }];
  const hasDiscoveryFilter = Boolean(query || favoriteOnly || collectionId || mealRole || libraryView !== "all");
  const isGenuinelyEmpty = Boolean(recipes.data && loadedItems.length === 0 && !hasDiscoveryFilter && !bulkMessage);
  const hasArchivedRecipes = Boolean(loadedItems.some((recipe) => recipe.status === "archived"));
  const clearDiscovery = () => {
    setQuery("");
    setLibraryView("all");
    setFavoriteOnly(false);
    setCollectionId("");
    setMealRole("");
  };
  const selectedItems = displayedRecipes.filter((recipe) => selectedIds.includes(recipe.id));
  const toggleSelected = (recipeId: string, selected: boolean) => {
    setSelectedIds((current) => selected ? [...new Set([...current, recipeId])] : current.filter((id) => id !== recipeId));
  };
  const archiveSelected = () => {
    setBulkMessage("");
    bulkArchive.mutate(selectedItems.map((recipe) => ({ id: recipe.id, version: recipe.version })));
  };

  const closeImport = (open: boolean) => {
    setImportOpen(open);
    if (!open && searchParams.has("import")) {
      const next = new URLSearchParams(searchParams);
      next.delete("import");
      setSearchParams(next, { replace: true });
    }
  };

  if (isGenuinelyEmpty && onboarding.data?.state === "pending") {
    return <main className="page-shell first-kitchen-page"><FirstRunJourney onboarding={onboarding.data} /></main>;
  }

  if (isGenuinelyEmpty && onboarding.isPending) {
    return <main className="page-shell recipe-library-page"><Skeleton label="Loading recipe library" lines={6} /></main>;
  }

  if (isGenuinelyEmpty) {
    return (
      <main className="page-shell recipe-library-page">
        <EmptyState
          headingLevel="h1"
          title="No recipes yet"
          description="Write one from memory or bring in a public recipe you already trust."
          action={<><Button asChild><Link to="/app/recipes/new">Create recipe</Link></Button><RecipeImportDialog trigger={<Button variant="secondary">Import recipe</Button>} /></>}
        />
      </main>
    );
  }

  return (
    <main className="page-shell recipe-library-page">
      <PageHeader
        eyebrow="Your recipes"
        title="What would you like to cook?"
        description="Search the dishes you know, then narrow the shelf only when you need to."
        actions={
          <details className="recipe-add-menu" ref={addMenuRef}>
            <summary className="cf-button cf-button--primary cf-button--md"><Plus aria-hidden="true" />Add recipe<ChevronDown aria-hidden="true" /></summary>
            <div className="recipe-add-menu__content">
              <Link to="/app/recipes/new" onClick={() => addMenuRef.current?.removeAttribute("open")}><Plus aria-hidden="true" /><span><strong>Write a recipe</strong><small>Build it ingredient by ingredient</small></span></Link>
              <button type="button" onClick={() => { addMenuRef.current?.removeAttribute("open"); setImportOpen(true); }}><FileDown aria-hidden="true" /><span><strong>Import a recipe</strong><small>From a public page or cookbook</small></span></button>
            </div>
          </details>
        }
      />
      <RecipeImportDialog open={importOpen} onOpenChange={closeImport} />

      <section className="recipe-discovery" aria-label="Find recipes">
        <SearchField className="recipe-search" label="Search recipes" placeholder="Search by recipe name" value={query} onChange={(event) => setQuery(event.target.value)} onClear={() => setQuery("")} />
        <TabList className="recipe-view-tabs" label="Recipe views">
          <button type="button" id="recipe-view-tab-all" role="tab" aria-controls="recipe-view-panel" aria-selected={!favoriteOnly} tabIndex={!favoriteOnly ? 0 : -1} onClick={() => setFavoriteOnly(false)}>All recipes</button>
          <button type="button" id="recipe-view-tab-favorites" role="tab" aria-controls="recipe-view-panel" aria-selected={favoriteOnly} tabIndex={favoriteOnly ? 0 : -1} onClick={() => setFavoriteOnly(true)}>Favorites</button>
        </TabList>
        <details className="recipe-filter-disclosure">
          <summary><SlidersHorizontal aria-hidden="true" /><span>Refine recipes</span>{activeFilters.length ? <b>{activeFilters.length}</b> : null}{sortBy !== "updated" || favoriteOnly ? <b>{([sortBy !== "updated", favoriteOnly].filter(Boolean).length)}</b> : null}<ChevronDown aria-hidden="true" /></summary>
          <div className="recipe-filter-disclosure__content">
            <div className="recipe-filter-fields">
              <Field label="Recipe status"><Select value={libraryView} onChange={(event) => setLibraryView(event.target.value as typeof libraryView)}><option value="all">Active recipes</option><option value="ready">Ready to plan</option><option value="attention">Needs attention</option><option value="archived">Archived</option></Select></Field>
              <Field label="Sort recipes"><Select value={sortBy} onChange={(event) => setSortBy(event.target.value as typeof sortBy)}><option value="updated">Recently updated</option><option value="title-asc">Name A–Z</option><option value="title-desc">Name Z–A</option><option value="protein">Highest protein</option><option value="calories">Lowest calories</option></Select></Field>
              <Field label="Collection"><Select value={collectionId} onChange={(event) => setCollectionId(event.target.value)}><option value="">Any collection</option>{(Array.isArray(collections.data) ? collections.data : []).map((collection) => <option key={collection.id} value={collection.id}>{collection.name}</option>)}</Select></Field>
              <Field label="Meal moment"><Select value={mealRole} onChange={(event) => setMealRole(event.target.value)}><option value="">Any meal</option><option value="breakfast">Breakfast</option><option value="lunch">Lunch</option><option value="dinner">Dinner</option><option value="snack">Snack</option></Select></Field>
              <Field label="Group results"><Select value={groupBy} onChange={(event) => setGroupBy(event.target.value as typeof groupBy)}><option value="none">No grouping</option><option value="readiness">Planning readiness</option></Select></Field>
            </div>
            <label className="recipe-favorite-filter"><Checkbox checked={favoriteOnly} onCheckedChange={(checked) => setFavoriteOnly(checked === true)} />Favorites only</label>
            <Button variant="ghost" onClick={() => { setSelectionMode((current) => !current); setSelectedIds([]); setBulkMessage(""); }}>{selectionMode ? "Done selecting" : "Select recipes"}</Button>
            <RecipeCollectionManager collections={Array.isArray(collections.data) ? collections.data : []} />
          </div>
         </details>
        {activeFilters.length ? <div className="active-library-filters" aria-label="Active recipe filters" aria-live="polite"><span>Showing a focused view</span>{activeFilters.map((filter) => <button type="button" key={filter.label} onClick={filter.clear}>{filter.label} <span aria-hidden="true">×</span><span className="sr-only">Remove filter</span></button>)}<button type="button" className="active-library-filters__clear" onClick={() => { setFavoriteOnly(false); setCollectionId(""); setMealRole(""); }}>Clear filters</button></div> : null}
      </section>

       {lifecycle.error instanceof Error ? <p className="error-text" role="alert">{lifecycle.error.message}</p> : null}
       {remove.error instanceof Error ? <p className="error-text" role="alert">{remove.error.message} The recipe is still available in Archived.</p> : null}
       {remove.isSuccess ? <p className="success-text" role="status">Recipe removed from your active library.</p> : null}
       {bulkMessage ? <p className={bulkArchive.isError || bulkMessage.includes("could not") ? "error-text" : "success-text"} role={bulkArchive.isError || bulkMessage.includes("could not") ? "alert" : "status"}>{bulkMessage}</p> : null}
       {recipes.isPending ? <Skeleton label="Loading recipe library" lines={6} /> : null}
       {recipes.isError ? <ErrorRecovery title="Recipes could not be loaded" onRetry={() => void recipes.refetch()} /> : null}
       {recipes.data && displayedRecipes.length === 0 ? <EmptyState title={hasDiscoveryFilter ? "No matching recipes" : "No active recipes"} description={hasDiscoveryFilter ? "Try another search or recipe view." : "Your saved recipes are archived. Restore one when you want it back in planning."} action={hasDiscoveryFilter ? <><Button variant="secondary" onClick={clearDiscovery}>Clear recipe filters</Button><Button variant="ghost" asChild><Link to="/app/suggestions">Get ideas</Link></Button></> : hasArchivedRecipes ? <Button variant="secondary" onClick={() => setLibraryView("archived")}>View archived recipes</Button> : null} /> : null}
       {selectionMode && selectedIds.length ? <BulkRecipeActions selectedCount={selectedIds.length} pending={bulkArchive.isPending} onArchive={archiveSelected} onClear={() => setSelectedIds([])} /> : null}
       {recipes.data && displayedRecipes.length ? <SectionHeading className="recipe-results-heading" eyebrow="Recipe box" title={hasDiscoveryFilter ? "Matching recipes" : "Saved recipes"} meta={`${displayedRecipes.length} ${displayedRecipes.length === 1 ? "recipe" : "recipes"}`} /> : null}
       <div id="recipe-view-panel" role="tabpanel" aria-labelledby={favoriteOnly ? "recipe-view-tab-favorites" : "recipe-view-tab-all"}>
         {groupedRecipes.map((group) => group.items.length ? <section className="recipe-group" aria-label={group.title || "Recipes"} key={group.title || "all"}>{group.title ? <div className="recipe-group__heading"><h2>{group.title}</h2><span>{group.items.length}</span></div> : null}<div className="recipe-grid">{group.items.map((recipe) => <RecipeCard key={recipe.id} recipe={recipe} selectionMode={selectionMode && recipe.status !== "archived"} selected={selectedIds.includes(recipe.id)} onSelectedChange={(selected) => toggleSelected(recipe.id, selected)} actionPending={lifecycle.isPending || remove.isPending || bulkArchive.isPending} onArchive={(id, version) => lifecycle.mutate({ id, version, action: "archive" })} onRestore={(id, version) => lifecycle.mutate({ id, version, action: "restore" })} onDelete={(id, version) => remove.mutate({ id, version })} />)}</div></section> : null)}
         {nextCursor ? <div className="recipe-library__load-more"><Button variant="secondary" onClick={() => loadMore.mutate(nextCursor)} disabled={loadMore.isPending}>{loadMore.isPending ? "Loading more recipes…" : "Load more recipes"}</Button>{loadMore.error instanceof Error ? <p className="error-text" role="alert">{loadMore.error.message} <button type="button" className="text-link" onClick={() => loadMore.reset()}>Dismiss</button></p> : null}</div> : null}
       </div>
     </main>
  );
}
