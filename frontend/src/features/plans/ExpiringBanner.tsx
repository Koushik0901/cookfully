import { Link } from "react-router-dom";

import { daysLeft } from "../pantry/expiry";

type PantryLike = {
  displayName?: string;
  normalizedFoodName: string;
  expiresOn?: string | null;
};

type Props = {
  pantry: PantryLike[];
  plan: { entries: Array<{ recipeTitle?: string; localDate?: string; date?: string; ingredients?: Array<{ normalized?: string; normalizedFoodName?: string; food?: string }> }> };
  today: string;
};

function normalize(value: string | undefined | null): string {
  return (value ?? "").trim().toLowerCase();
}

export function ExpiringBanner({ pantry, plan, today }: Props) {
  const expiring = (pantry ?? []).filter(
    (p) => p.expiresOn && daysLeft(p.expiresOn, today) >= 0 && daysLeft(p.expiresOn, today) <= 3,
  );
  const matched = expiring.filter((e) =>
    (plan.entries ?? []).some((en) =>
      (en.ingredients ?? []).some((ing) => {
        const a = normalize((ing as { normalized?: string }).normalized ?? (ing as { normalizedFoodName?: string }).normalizedFoodName ?? (ing as { food?: string }).food);
        const b = normalize(e.normalizedFoodName);
        if (!a || !b) return false;
        return a.includes(b) || b.includes(a);
      }),
    ),
  );

  if (!expiring.length) return null;

  // Find first matched entry for display, if any
  let matchedLabel = "";
  if (matched.length) {
    const firstMatchedPantry = matched[0];
    const b = normalize(firstMatchedPantry.normalizedFoodName);
    const matchedEntry = (plan.entries ?? []).find((en) =>
      (en.ingredients ?? []).some((ing) => {
        const a = normalize((ing as { normalized?: string }).normalized ?? (ing as { normalizedFoodName?: string }).normalizedFoodName ?? (ing as { food?: string }).food);
        return a.includes(b) || b.includes(a);
      }),
    ) as { recipeTitle?: string; localDate?: string; date?: string } | undefined;
    if (matchedEntry) {
      const date = matchedEntry.localDate ?? matchedEntry.date ?? "";
      const title = matchedEntry.recipeTitle ?? firstMatchedPantry.displayName ?? firstMatchedPantry.normalizedFoodName;
      matchedLabel = ` — also in ${title}${date ? ` on ${date}` : ""}`;
    } else {
      matchedLabel = ` — also in ${firstMatchedPantry.displayName ?? firstMatchedPantry.normalizedFoodName}`;
    }
  }

  return (
    <section className="notice expiring-banner" role="status">
      Use soon: {expiring.map((e) => `${e.displayName ?? e.normalizedFoodName} (${daysLeft(e.expiresOn!, today)}d)`).join(", ")}
      {matchedLabel} <Link to="/app/pantry">View in Pantry</Link>
    </section>
  );
}
