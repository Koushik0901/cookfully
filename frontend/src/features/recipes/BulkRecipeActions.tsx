import { Archive, X } from "lucide-react";

import { Button, ConfirmDialog } from "../../components";

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
        <ConfirmDialog trigger={<Button disabled={pending || selectedCount === 0}>
          <Archive aria-hidden="true" />
          {pending ? "Archiving…" : `Archive ${selectedCount} selected ${noun}`}
        </Button>} title={`Archive ${selectedCount} selected ${noun}?`} description="They will leave active planning but remain available in Archived recipes. You can restore them later." confirmLabel={`Archive ${selectedCount} ${noun}`} onConfirm={onArchive} />
        <Button variant="ghost" onClick={onClear} disabled={pending}>
          <X aria-hidden="true" />
          Clear selection
        </Button>
      </div>
    </div>
  );
}
