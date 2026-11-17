import { facetKnown, facetLabel, type RecipeFacet } from "./facets";

/** Tags decision models gave the recipe. Hidden entirely when there are none. */
export function FacetChips({ facets, keys }: { facets: readonly RecipeFacet[] | undefined; keys?: readonly string[] }) {
  const shown = (facets ?? []).filter((facet) => facetKnown(facet) && (!keys || keys.includes(facet.key)));
  if (!shown.length) return null;
  return (
    <ul className="facet-chips" aria-label="Recipe tags">
      {shown.map((facet) => (
        <li key={facet.key} title={`Suggested by decision models (${Math.round(Number(facet.probability) * 100)}%)`}>
          {facetLabel(facet)}
        </li>
      ))}
    </ul>
  );
}
