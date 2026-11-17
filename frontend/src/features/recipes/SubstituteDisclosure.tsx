import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { recipesApi } from "./api";

/** "Swap" disclosure for one ingredient; asks for substitutes only when opened. */
export function SubstituteDisclosure({ recipeId, ingredientId }: { recipeId: string; ingredientId: string }) {
  const [open, setOpen] = useState(false);
  const substitutes = useQuery({
    queryKey: ["substitutes", recipeId, ingredientId],
    queryFn: () => recipesApi.substitutes(recipeId, ingredientId),
    enabled: open,
    staleTime: Infinity,
    retry: 1,
  });
  return (
    <details className="substitutes" onToggle={(event) => setOpen(event.currentTarget.open)}>
      <summary>Swap</summary>
      <div className="substitutes__body" aria-live="polite">
        {substitutes.isPending && open ? <p className="muted">Finding swaps…</p> : null}
        {substitutes.isError ? (
          <p className="error-text">
            Swaps could not be loaded. <button type="button" onClick={() => void substitutes.refetch()}>Try again</button>
          </p>
        ) : null}
        {substitutes.data && !substitutes.data.substitutes.length ? <p className="muted">No good swaps for this recipe.</p> : null}
        {substitutes.data?.substitutes.length ? (
          <ul>
            {substitutes.data.substitutes.map((item) => (
              <li key={item.name}>
                <strong>{item.name}</strong>
                <span>{item.amount}</span>
                {item.note ? <small>{item.note}</small> : null}
                {item.probability != null ? <small className="substitutes__fit">{Math.round(Number(item.probability) * 100)}% fit for this recipe</small> : null}
              </li>
            ))}
          </ul>
        ) : null}
        {substitutes.data && !substitutes.data.ranked && substitutes.data.substitutes.length ? (
          <p className="muted">Not ranked for this recipe; common swaps shown.</p>
        ) : null}
      </div>
    </details>
  );
}
