import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Heart, Plus, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";

import { Button, Field } from "../../components";
import { Checkbox } from "@/components/ui/checkbox";
import { recipesApi } from "./api";
import { RecipeCollectionManager } from "./RecipeCollectionManager";
import type { RecipeDetail } from "./types";

const roles = ["breakfast", "lunch", "dinner", "snack"] as const;

export function RecipeOrganizationPanel({ recipe, onSaved }: { recipe: RecipeDetail; onSaved: (value: RecipeDetail) => void }) {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const collections = useQuery({ queryKey: ["recipe-collections"], queryFn: recipesApi.collections, enabled: open });
  const [favorite, setFavorite] = useState(recipe.favorite ?? false);
  const [selected, setSelected] = useState<string[]>(recipe.collections?.map((item) => item.id) ?? []);
  const [mealRoles, setMealRoles] = useState<string[]>(recipe.mealRoles ?? []);
  const [newCollection, setNewCollection] = useState("");
  useEffect(() => { setFavorite(recipe.favorite ?? false); setSelected(recipe.collections?.map((item) => item.id) ?? []); setMealRoles(recipe.mealRoles ?? []); }, [recipe]);
  const save = useMutation({ mutationFn: () => recipesApi.organize(recipe.id, recipe.version, { favorite, collectionIds: selected, mealRoles: mealRoles as (typeof roles)[number][] }), onSuccess: (value) => { onSaved(value); void queryClient.invalidateQueries({ queryKey: ["recipes"] }); } });
  const create = useMutation({ mutationFn: () => recipesApi.createCollection(newCollection), onSuccess: () => { setNewCollection(""); void collections.refetch(); } });
  const remove = useMutation({ mutationFn: ({ id, version }: { id: string; version: number }) => recipesApi.removeCollection(id, version), onSuccess: (_, removed) => { setSelected((current) => current.filter((id) => id !== removed.id)); void collections.refetch(); } });
  const availableCollections = Array.isArray(collections.data) ? collections.data : [];
  return <details className="recipe-organization" onToggle={(event) => setOpen(event.currentTarget.open)}><summary><Heart aria-hidden="true" /><span><strong>Keep this easy to find</strong><small>Optional favorites, collections, and meal moments.</small></span></summary><div className="recipe-organization__body">
    <label className="check-label"><Checkbox checked={favorite} onCheckedChange={(checked) => setFavorite(checked === true)} />Favorite this recipe</label>
    <fieldset><legend>Collections</legend><div className="organization-chips">{availableCollections.map((collection) => <span key={collection.id}><label><Checkbox checked={selected.includes(collection.id)} onCheckedChange={(checked) => setSelected(checked === true ? [...selected, collection.id] : selected.filter((id) => id !== collection.id))} />{collection.name}</label><button type="button" aria-label={`Remove collection ${collection.name}`} className="organization-chip-delete" onClick={() => remove.mutate(collection)}><Trash2 aria-hidden="true" /></button></span>)}</div></fieldset>
    <fieldset><legend>Good for</legend><div className="organization-chips">{roles.map((role) => <label key={role}><Checkbox checked={mealRoles.includes(role)} onCheckedChange={(checked) => setMealRoles(checked === true ? [...mealRoles, role] : mealRoles.filter((value) => value !== role))} />{role}</label>)}</div></fieldset>
    <div className="organization-new"><Field label="New collection"><input className="input" value={newCollection} placeholder="e.g. Weeknight favourites" onChange={(event) => setNewCollection(event.currentTarget.value)} /></Field><Button variant="secondary" onClick={() => create.mutate()} disabled={!newCollection.trim() || create.isPending}><Plus aria-hidden="true" />Add</Button></div>
    <RecipeCollectionManager collections={availableCollections} />
    <Button onClick={() => save.mutate()} disabled={save.isPending}>{save.isPending ? "Saving…" : "Save organization"}</Button>
    {save.error instanceof Error || create.error instanceof Error ? <p className="error-text" role="alert">{(save.error ?? create.error as Error).message}</p> : null}
  </div></details>;
}
