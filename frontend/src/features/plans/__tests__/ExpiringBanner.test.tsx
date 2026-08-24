import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, test } from "vitest";

import { ExpiringBanner } from "../ExpiringBanner";

function renderBanner(props: Parameters<typeof ExpiringBanner>[0]) {
  return render(
    <MemoryRouter>
      <ExpiringBanner {...props} />
    </MemoryRouter>,
  );
}

describe("ExpiringBanner", () => {
  afterEach(() => cleanup());
  test("shows banner when expiring tomato matches Tue pasta", () => {
    renderBanner({
      pantry: [{ normalizedFoodName: "tomato", expiresOn: "2026-08-26", displayName: "Tomato" } as never],
      plan: { entries: [{ recipeTitle: "Pasta", localDate: "2026-08-26", ingredients: [{ normalized: "tomato" }] }] } as never,
      today: "2026-08-24",
    });
    expect(screen.getByText(/Use soon/)).toBeInTheDocument();
  });

  test("no banner when no expiring items", () => {
    renderBanner({
      pantry: [] as never,
      plan: { entries: [] } as never,
      today: "2026-08-24",
    });
    expect(screen.queryByText(/Use soon/)).not.toBeInTheDocument();
  });
});
