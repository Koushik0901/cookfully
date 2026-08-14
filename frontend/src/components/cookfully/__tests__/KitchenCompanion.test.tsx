import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { KitchenCompanion } from "../KitchenCompanion";

describe("KitchenCompanion", () => {
  afterEach(cleanup);

  it("renders every purposeful moment as decorative inline vector art", () => {
    const moments = ["loading", "empty", "success", "milestone", "error"] as const;
    const { container } = render(<>{moments.map((moment) => <KitchenCompanion key={moment} moment={moment} />)}</>);

    for (const moment of moments) {
      const companion = container.querySelector(`[data-companion-moment="${moment}"]`);
      expect(companion).toHaveAttribute("aria-hidden", "true");
      expect(companion?.querySelector("svg")).toHaveAttribute("focusable", "false");
    }
  });

  it("keeps celebration marks exclusive to genuine milestones", () => {
    const { container, rerender } = render(<KitchenCompanion moment="success" />);
    expect(container.querySelector(".kitchen-companion__check")).toBeInTheDocument();
    expect(container.querySelector(".kitchen-companion__celebration")).not.toBeInTheDocument();

    rerender(<KitchenCompanion moment="milestone" />);
    expect(container.querySelector(".kitchen-companion__celebration")).toBeInTheDocument();
  });
});
