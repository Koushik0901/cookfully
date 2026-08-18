import { Archive, X } from "lucide-react";

import { Button } from "../../components";

export function BulkRecipeActions({
  selectedCount,
  pending,
  onArchive,
  onClear,
}: {
  selectedCount: number;
  pending: boolean;
  onArchive: () => void;
  onClear: () => void;
}) {
  const noun = selectedCount === 1 ? "recipe" : "recipes";
  return (
    <div className="bulk-recipe-actions" role="region" aria-label="Selected recipe actions">
      <strong>{selectedCount} {noun} selected</strong>
      <div className="bulk-recipe-actions__buttons">
        <Button onClick={onArchive} disabled={pending || selectedCount === 0}>
          <Archive aria-hidden="true" />
          {pending ? "Archiving…" : `Archive ${selectedCount} selected ${noun}`}
        </Button>
        <Button variant="ghost" onClick={onClear} disabled={pending}>
          <X aria-hidden="true" />
          Clear selection
        </Button>
      </div>
    </div>
  );
}
