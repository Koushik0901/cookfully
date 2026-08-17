import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ThumbnailCropEditor } from "../ThumbnailCropEditor";

describe("ThumbnailCropEditor", () => {
  it("reveals accessible framing controls and emits focal metadata", () => {
    const onChange = vi.fn();
    render(<ThumbnailCropEditor imageUrl="/cover.jpg" onChange={onChange} />);

    fireEvent.click(screen.getByRole("button", { name: "Adjust framing" }));
    fireEvent.change(screen.getByLabelText("Horizontal focus"), { target: { value: "0.25" } });

    expect(onChange).toHaveBeenCalledWith({ focalX: "0.25", focalY: "0.5", zoom: "1" });
    expect(screen.getByRole("button", { name: "Hide framing controls" })).toBeVisible();
  });
});
