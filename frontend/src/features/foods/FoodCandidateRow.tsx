import type { FoodCandidate } from "./types";

export function FoodRow({ candidate }: { candidate: FoodCandidate }) {
  const brand = candidate.brandOwner;
  const source = candidate.source === "owner"
    ? "Yours"
    : candidate.remembered
      ? "Previously chosen · USDA"
      : "USDA";
  const serving = candidate.servingSizeG
    ? `${candidate.servingSizeG}g${candidate.servingUnit ? ` (${candidate.servingUnit})` : ""}`
    : null;

  return (
    <span className="food-candidate-row">
      <span className="food-candidate-name">
        <strong>{candidate.description}</strong>
        {brand && <span className="muted"> &mdash; {brand}</span>}
      </span>
      <span className="food-candidate-meta">
        <span className="food-candidate-source">{source}</span>
        {serving && <span className="muted">{serving}</span>}
        {candidate.compatibility === "review" && <span className="muted">Review required</span>}
      </span>
    </span>
  );
}
