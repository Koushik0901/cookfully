import { AISLE_LABELS } from "./aisles";
import type { GroceryItem } from "./types";


interface GroceryTidyLineProps {
  item: GroceryItem;
  title: string;
  readOnly: boolean;
  busy: boolean;
  onStaple: (likelyStaple: boolean) => void;
  onKeepSeparate: () => void;
}

/** Aisle, "probably have" mark and synonym merges from grocery tidy; all owner-overridable. */
export function GroceryTidyLine({ item, title, readOnly, busy, onStaple, onKeepSeparate }: GroceryTidyLineProps) {
  const aisle = item.aisle ? AISLE_LABELS[item.aisle] ?? item.aisle : null;
  const merged = item.mergedFrom ?? [];
  if (!aisle && !item.likelyStaple && !merged.length) return null;
  return (
    <p className="grocery-tidy">
      {aisle ? <span className="grocery-tidy__aisle">{aisle}</span> : null}
      {item.likelyStaple ? (
        readOnly ? <span className="grocery-tidy__staple">Probably have</span> : (
          <button type="button" className="grocery-tidy__staple" aria-pressed="true" disabled={busy} onClick={() => onStaple(false)} title="Tap if you need to buy it">
            Probably have
          </button>
        )
      ) : null}
      {merged.length ? (
        <span className="grocery-tidy__merged">
          Includes {merged.join(", ")}
          {readOnly ? null : (
            <button type="button" disabled={busy} onClick={onKeepSeparate} aria-label={`Keep ${merged.join(", ")} separate from ${title}`}>
              Keep separate
            </button>
          )}
        </span>
      ) : null}
    </p>
  );
}
