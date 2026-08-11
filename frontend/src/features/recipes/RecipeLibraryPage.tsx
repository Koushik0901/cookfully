import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { useState } from "react";

import { Button, EmptyState, ErrorRecovery, Field, PageHeader, Skeleton } from "../../components";
import { recipesApi } from "./api";
import { RecipeCard } from "./RecipeCard";
import { RecipeImportDialog } from "./RecipeImportDialog";

export function RecipeLibraryPage() {
  const queryClient = useQueryClient();
  const [query, setQuery] = useState("");
  const [nutritionState, setNutritionState] = useState("");
  const [includeArchived, setIncludeArchived] = useState(false);
  const filters = { query, nutritionState, includeArchived };
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

  return (
    <main className="page-shell">
      <PageHeader
        eyebrow="Recipe workspace"
        title="Recipe library"
        description="Search, inspect evidence, and keep every nutrition estimate correctable."
        actions={<><RecipeImportDialog trigger={<Button className="button--secondary">Import from URL</Button>} /><Button asChild><Link to="/app/recipes/new">Create recipe</Link></Button></>}
      />

      <section className="filter-bar" aria-label="Recipe filters">
        <Field label="Search recipes"><input className="input" type="search" value={query} onChange={(event) => setQuery(event.target.value)} /></Field>
        <Field label="Nutrition state"><select className="input" value={nutritionState} onChange={(event) => setNutritionState(event.target.value)}><option value="">All states</option><option value="pending">Pending</option><option value="source_provided">Source provided</option><option value="estimated">Estimated</option><option value="partial">Partial</option><option value="failed">Failed</option><option value="stale">Stale</option></select></Field>
        <label className="check-field"><input type="checkbox" checked={includeArchived} onChange={(event) => setIncludeArchived(event.target.checked)} /> Include archived recipes</label>
      </section>

      {lifecycle.error instanceof Error ? <p className="error-text" role="alert">{lifecycle.error.message}</p> : null}
      {recipes.isPending ? <Skeleton label="Loading recipe library" lines={6} /> : null}
      {recipes.isError ? <ErrorRecovery title="Recipes could not be loaded" onRetry={() => void recipes.refetch()} /> : null}
      {recipes.data && recipes.data.items.length === 0 ? <EmptyState title="No recipes yet" description={query || nutritionState || includeArchived ? "No recipes match these filters." : "Create one manually or import a public recipe URL."} action={<Button asChild><Link to="/app/recipes/new">Create recipe</Link></Button>} /> : null}
      {recipes.data?.items.length ? <section className="recipe-grid" aria-label="Recipes">{recipes.data.items.map((recipe) => <RecipeCard key={recipe.id} recipe={recipe} onArchive={(id, version) => lifecycle.mutate({ id, version, action: "archive" })} onRestore={(id, version) => lifecycle.mutate({ id, version, action: "restore" })} />)}</section> : null}
    </main>
  );
}
