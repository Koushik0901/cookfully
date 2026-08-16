import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { useMemo, useState } from "react";
import { ChevronDown, Search, SlidersHorizontal, Sparkles } from "lucide-react";

import { Button, EmptyState, ErrorRecovery, Field, PageHeader, Select, Skeleton } from "../../components";
import { recipesApi } from "./api";
import { RecipeCard } from "./RecipeCard";
import { RecipeCollectionManager } from "./RecipeCollectionManager";
import { RecipeImportDialog } from "./RecipeImportDialog";
import { FirstRunJourney } from "../onboarding/FirstRunJourney";
import { onboardingApi } from "../onboarding/api";
import { Checkbox } from "@/components/ui/checkbox";

export function RecipeLibraryPage() {
  const queryClient = useQueryClient();
  const [query, setQuery] = useState("");
  const [libraryView, setLibraryView] = useState<"all" | "ready" | "attention" | "archived">("all");
  const [sortBy, setSortBy] = useState<"updated" | "title-asc" | "title-desc" | "protein" | "calories">("updated");
  const [groupBy, setGroupBy] = useState<"none" | "readiness">("none");
  const [favoriteOnly, setFavoriteOnly] = useState(false);
  const [collectionId, setCollectionId] = useState("");
  const [mealRole, setMealRole] = useState("");
  const collections = useQuery({ queryKey: ["recipe-collections"], queryFn: recipesApi.collections, retry: 1 });
  const onboarding = useQuery({ queryKey: ["owner-onboarding"], queryFn: onboardingApi.get, retry: 1 });
  const collectionName = (Array.isArray(collections.data) ? collections.data : []).find((collection) => collection.id === collectionId)?.name;
  const activeFilters = [
    favoriteOnly ? { label: "Favorites", clear: () => setFavoriteOnly(false) } : null,
    collectionId ? { label: `Collection: ${collectionName ?? "Selected"}`, clear: () => setCollectionId("") } : null,
    mealRole ? { label: `Meal: ${mealRole}`, clear: () => setMealRole("") } : null,
  ].filter((filter): filter is { label: string; clear: () => void } => filter !== null);
  const filters = { query, includeArchived: true, favorite: favoriteOnly || undefined, collectionId: collectionId || undefined, mealRole: mealRole || undefined };
  const recipes = useQuery({
    queryKey: ["recipes", filters],
    queryFn: () => recipesApi.list(filters),
    retry: 1,
  });
  const lifecycle = useMutation({
    mutationFn: async ({ id, version, action }: { id: string; version: number; action: "archive" | "restore" }) => {
      if (action === "archive") await recipesApi.archive(id, version);
      else await recipesApi.restore(id, version);
    },
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["recipes"] }),
  });
  const remove = useMutation({
    mutationFn: ({ id, version }: { id: string; version: number }) => recipesApi.permanentDelete(id, version),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["recipes"] }),
  });
  const displayedRecipes = useMemo(() => {
    const items = recipes.data?.items.filter((recipe) => {
      const ready = recipe.status !== "archived" && !["pending", "failed", "stale"].includes(recipe.nutritionState);
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
  }, [libraryView, recipes.data?.items, sortBy]);
  const groupedRecipes = groupBy === "readiness"
    ? [
        { title: "Ready to plan", items: displayedRecipes.filter((recipe) => recipe.status !== "archived" && !["pending", "failed", "stale"].includes(recipe.nutritionState)) },
        { title: "Needs a nutrition check", items: displayedRecipes.filter((recipe) => recipe.status !== "archived" && ["pending", "failed", "stale"].includes(recipe.nutritionState)) },
        { title: "Archived", items: displayedRecipes.filter((recipe) => recipe.status === "archived") },
      ].filter((group) => group.items.length)
    : [{ title: "", items: displayedRecipes }];
  const hasDiscoveryFilter = Boolean(query || favoriteOnly || collectionId || mealRole || libraryView !== "all");
  const isGenuinelyEmpty = Boolean(recipes.data && recipes.data.items.length === 0 && !hasDiscoveryFilter);
  const hasArchivedRecipes = Boolean(recipes.data?.items.some((recipe) => recipe.status === "archived"));
  const clearDiscovery = () => {
    setQuery("");
    setLibraryView("all");
    setFavoriteOnly(false);
    setCollectionId("");
    setMealRole("");
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
        description="Browse what you know, or let Cookfully help you find a good fit for the week."
        actions={<><Button asChild><Link to="/app/suggestions"><Sparkles aria-hidden="true" />Give me ideas</Link></Button><RecipeImportDialog trigger={<Button variant="secondary">Import recipe</Button>} /><Button variant="secondary" asChild><Link to="/app/recipes/new">Create recipe</Link></Button></>}
      />

      <section className="recipe-discovery" aria-label="Find recipes">
        <div className="recipe-search"><Search aria-hidden="true" /><input className="input" aria-label="Search recipes" type="search" placeholder="Search by recipe name" value={query} onChange={(event) => setQuery(event.target.value)} /></div>
        <div className="recipe-view-tabs" role="tablist" aria-label="Recipe views">
          {([['all', 'All recipes'], ['ready', 'Ready to plan'], ['attention', 'Needs attention'], ['archived', 'Archived']] as const).map(([value, label]) => <button type="button" key={value} role="tab" aria-selected={libraryView === value} onClick={() => setLibraryView(value)}>{label}</button>)}
        </div>
        <details className="recipe-filter-disclosure">
          <summary><SlidersHorizontal aria-hidden="true" /><span>Refine recipes</span>{activeFilters.length ? <b>{activeFilters.length}</b> : null}{sortBy !== "updated" || favoriteOnly ? <b>{([sortBy !== "updated", favoriteOnly].filter(Boolean).length)}</b> : null}<ChevronDown aria-hidden="true" /></summary>
          <div className="recipe-filter-disclosure__content">
            <div className="recipe-filter-fields">
              <Field label="Sort recipes"><Select value={sortBy} onChange={(event) => setSortBy(event.target.value as typeof sortBy)}><option value="updated">Recently updated</option><option value="title-asc">Name A–Z</option><option value="title-desc">Name Z–A</option><option value="protein">Highest protein</option><option value="calories">Lowest calories</option></Select></Field>
              <Field label="Collection"><Select value={collectionId} onChange={(event) => setCollectionId(event.target.value)}><option value="">Any collection</option>{(Array.isArray(collections.data) ? collections.data : []).map((collection) => <option key={collection.id} value={collection.id}>{collection.name}</option>)}</Select></Field>
              <Field label="Meal moment"><Select value={mealRole} onChange={(event) => setMealRole(event.target.value)}><option value="">Any meal</option><option value="breakfast">Breakfast</option><option value="lunch">Lunch</option><option value="dinner">Dinner</option><option value="snack">Snack</option></Select></Field>
              <Field label="Group results"><Select value={groupBy} onChange={(event) => setGroupBy(event.target.value as typeof groupBy)}><option value="none">No grouping</option><option value="readiness">Planning readiness</option></Select></Field>
            </div>
            <label className="recipe-favorite-filter"><Checkbox checked={favoriteOnly} onCheckedChange={(checked) => setFavoriteOnly(checked === true)} />Favorites only</label>
            <RecipeCollectionManager collections={Array.isArray(collections.data) ? collections.data : []} />
          </div>
        </details>
        {activeFilters.length ? <div className="active-library-filters" aria-label="Active recipe filters" aria-live="polite"><span>Showing a focused view</span>{activeFilters.map((filter) => <button type="button" key={filter.label} onClick={filter.clear}>{filter.label} <span aria-hidden="true">×</span><span className="sr-only">Remove filter</span></button>)}<button type="button" className="active-library-filters__clear" onClick={() => { setFavoriteOnly(false); setCollectionId(""); setMealRole(""); }}>Clear filters</button></div> : null}
      </section>

      {lifecycle.error instanceof Error ? <p className="error-text" role="alert">{lifecycle.error.message}</p> : null}
      {recipes.isPending ? <Skeleton label="Loading recipe library" lines={6} /> : null}
      {recipes.isError ? <ErrorRecovery title="Recipes could not be loaded" onRetry={() => void recipes.refetch()} /> : null}
      {recipes.data && displayedRecipes.length === 0 ? <EmptyState title={hasDiscoveryFilter ? "No matching recipes" : "No active recipes"} description={hasDiscoveryFilter ? "Try another search or recipe view." : "Your saved recipes are archived. Restore one when you want it back in planning."} action={hasDiscoveryFilter ? <Button variant="secondary" onClick={clearDiscovery}>Clear recipe filters</Button> : hasArchivedRecipes ? <Button variant="secondary" onClick={() => setLibraryView("archived")}>View archived recipes</Button> : null} /> : null}
      {groupedRecipes.map((group) => group.items.length ? <section className="recipe-group" aria-label={group.title || "Recipes"} key={group.title || "all"}>{group.title ? <div className="recipe-group__heading"><h2>{group.title}</h2><span>{group.items.length}</span></div> : null}<div className="recipe-grid">{group.items.map((recipe) => <RecipeCard key={recipe.id} recipe={recipe} onArchive={(id, version) => lifecycle.mutate({ id, version, action: "archive" })} onRestore={(id, version) => lifecycle.mutate({ id, version, action: "restore" })} onDelete={(id, version) => remove.mutate({ id, version })} />)}</div></section> : null)}
    </main>
  );
}
