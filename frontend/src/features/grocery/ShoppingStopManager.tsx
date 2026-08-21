import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowDown, ArrowUp, Check, MapPin, Plus, Trash2 } from "lucide-react";
import { useState } from "react";

import { Button, ConfirmDialog, Field } from "../../components";
import { groceryApi } from "./api";
import type { GroceryShoppingStop } from "./types";

function StopRow({ stop, first, last }: { stop: GroceryShoppingStop; first: boolean; last: boolean }) {
  const queryClient = useQueryClient();
  const [name, setName] = useState(stop.name);
  const refresh = () => queryClient.invalidateQueries({ queryKey: ["grocery-shopping-stops"] });
  const update = useMutation({
    mutationFn: (value: { name?: string; position?: number }) => groceryApi.updateStop(stop.id, stop.version, value),
    onSuccess: refresh,
  });
  const remove = useMutation({ mutationFn: () => groceryApi.removeStop(stop.id, stop.version), onSuccess: refresh });
  const error = update.error ?? remove.error;
  return <li className="shopping-stops__row"><input className="input" aria-label={`${stop.name} stop name`} value={name} onChange={(event) => setName(event.currentTarget.value)} /><Button variant="ghost" size="icon" aria-label={`Save name for stop ${stop.name}`} disabled={!name.trim() || name === stop.name || update.isPending} onClick={() => update.mutate({ name })}><Check aria-hidden="true" /></Button><Button variant="ghost" size="icon" aria-label={`Move ${stop.name} earlier`} disabled={first || update.isPending} onClick={() => update.mutate({ position: stop.position - 1 })}><ArrowUp aria-hidden="true" /></Button><Button variant="ghost" size="icon" aria-label={`Move ${stop.name} later`} disabled={last || update.isPending} onClick={() => update.mutate({ position: stop.position + 1 })}><ArrowDown aria-hidden="true" /></Button><ConfirmDialog trigger={<Button variant="ghost" size="icon" aria-label={`Remove ${stop.name}`} disabled={remove.isPending}><Trash2 aria-hidden="true" /></Button>} title={`Remove ${stop.name}?`} description="Items assigned here will become unassigned and stay on your grocery list." confirmLabel="Remove stop" onConfirm={() => remove.mutate()} />{error instanceof Error ? <p className="error-text" role="alert">{error.message}</p> : null}</li>;
}

export function ShoppingStopManager() {
  const queryClient = useQueryClient();
  const stops = useQuery({ queryKey: ["grocery-shopping-stops"], queryFn: groceryApi.stops });
  const [name, setName] = useState("");
  const refresh = () => queryClient.invalidateQueries({ queryKey: ["grocery-shopping-stops"] });
  const create = useMutation({
    mutationFn: (submittedName: string) => groceryApi.createStop({ name: submittedName }),
    onMutate: (submittedName) => {
      setName("");
      return { submittedName };
    },
    onSuccess: () => void refresh(),
    onError: (_error, _variables, context) => setName(context?.submittedName ?? ""),
  });
  const values = Array.isArray(stops.data) ? stops.data : [];
  return <details className="shopping-stops">
    <summary><MapPin aria-hidden="true" /><span><strong>Shop by stop</strong><small>Group this week around the places you actually visit.</small></span></summary>
    <div className="shopping-stops__body">
      {values.length ? <ol className="shopping-stops__list">{values.map((stop, index) => <StopRow key={stop.id} stop={stop} first={index === 0} last={index === values.length - 1} />)}</ol> : <p className="muted">Add a stop when it helps. Unassigned items always stay visible.</p>}
      {stops.isPending ? <p className="muted" role="status">Loading your shopping stops…</p> : null}
      {stops.isError ? <div className="notice" role="alert">Shopping stops could not be loaded. <button className="text-link" type="button" onClick={() => void stops.refetch()}>Try again</button></div> : null}
      <div className="shopping-stops__add"><Field label="New stop"><input className="input" value={name} placeholder="e.g. Neighbourhood market" disabled={create.isPending} onChange={(event) => setName(event.currentTarget.value)} /></Field><Button variant="secondary" onClick={() => create.mutate(name.trim())} disabled={!name.trim() || create.isPending}><Plus aria-hidden="true" />Add stop</Button></div>
      {create.error instanceof Error ? <p className="error-text" role="alert">{create.error.message}</p> : null}
    </div>
  </details>;
}
