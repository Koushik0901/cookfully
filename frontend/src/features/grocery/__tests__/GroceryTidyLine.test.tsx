import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { GroceryTidyLine } from "../GroceryTidyLine";
import type { GroceryItem } from "../types";

afterEach(cleanup);

const base = { id: "g1", displayName: "green onions", origin: "generated", needsReview: false, sources: [], version: 1 } as unknown as GroceryItem;

describe("GroceryTidyLine", () => {
  it("shows aisle, staple and merged names, with owner controls", async () => {
    const onStaple = vi.fn();
    const onKeepSeparate = vi.fn();
    const user = userEvent.setup();
    render(<GroceryTidyLine item={{ ...base, aisle: "produce", likelyStaple: true, mergedFrom: ["scallions"] }} title="green onions" readOnly={false} busy={false} onStaple={onStaple} onKeepSeparate={onKeepSeparate} />);
    expect(screen.getByText("Produce")).toBeInTheDocument();
    expect(screen.getByText(/Includes scallions/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Probably have" }));
    expect(onStaple).toHaveBeenCalledWith(false);
    await user.click(screen.getByRole("button", { name: "Keep scallions separate from green onions" }));
    expect(onKeepSeparate).toHaveBeenCalled();
  });

  it("renders nothing without tidy data and no buttons when read-only", () => {
    const { container, rerender } = render(<GroceryTidyLine item={base} title="x" readOnly={false} busy={false} onStaple={vi.fn()} onKeepSeparate={vi.fn()} />);
    expect(container).toBeEmptyDOMElement();
    rerender(<GroceryTidyLine item={{ ...base, likelyStaple: true, mergedFrom: ["a"] }} title="x" readOnly busy={false} onStaple={vi.fn()} onKeepSeparate={vi.fn()} />);
    expect(screen.queryAllByRole("button")).toHaveLength(0);
  });
});
