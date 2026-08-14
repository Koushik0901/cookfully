import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowDown, ArrowUp, Check, Trash2 } from "lucide-react";
import { useState } from "react";

import { Button } from "../../components";
import { recipesApi } from "./api";
import type { RecipeCollection } from "./types";

function CollectionRow({ collection, first, last }: { collection: RecipeCollection; first: boolean; last: boolean }) {
  const queryClient = useQueryClient();
  const [name, setName] = useState(collection.name);
  const refresh = () => queryClient.invalidateQueries({ queryKey: ["recipe-collections"] });
  const update = useMutation({ mutationFn: (value: { name?: string; position?: number }) => recipesApi.updateCollection(collection.id, collection.version, value), onSuccess: refresh });
  const remove = useMutation({ mutationFn: () => recipesApi.removeCollection(collection.id, collection.version), onSuccess: refresh });
  return <li className="collection-manager__row"><input className="input" aria-label={`${collection.name} collection name`} value={name} onChange={(event) => setName(event.currentTarget.value)} /><Button variant="ghost" size="icon" aria-label={`Save name for collection ${collection.name}`} disabled={!name.trim() || name === collection.name || update.isPending} onClick={() => update.mutate({ name })}><Check aria-hidden="true" /></Button><Button variant="ghost" size="icon" aria-label={`Move ${collection.name} earlier`} disabled={first || update.isPending} onClick={() => update.mutate({ position: collection.position - 1 })}><ArrowUp aria-hidden="true" /></Button><Button variant="ghost" size="icon" aria-label={`Move ${collection.name} later`} disabled={last || update.isPending} onClick={() => update.mutate({ position: collection.position + 1 })}><ArrowDown aria-hidden="true" /></Button><Button variant="ghost" size="icon" aria-label={`Delete ${collection.name} collection`} disabled={remove.isPending} onClick={() => remove.mutate()}><Trash2 aria-hidden="true" /></Button>{update.error instanceof Error || remove.error instanceof Error ? <p className="error-text" role="alert">{(update.error ?? remove.error as Error).message}</p> : null}</li>;
}

export function RecipeCollectionManager({ collections }: { collections: RecipeCollection[] }) {
  if (!collections.length) return null;
  return <details className="collection-manager"><summary>Manage collections</summary><ol>{collections.map((collection, index) => <CollectionRow key={collection.id} collection={collection} first={index === 0} last={index === collections.length - 1} />)}</ol></details>;
}
