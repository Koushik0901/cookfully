import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it } from "vitest";

import { SearchField, TabList } from "../index";

function SearchHarness() {
  const [value, setValue] = useState("");
  return (
    <SearchField
      label="Search recipes"
      placeholder="Search by recipe name"
      value={value}
      onChange={(event) => setValue(event.target.value)}
      onClear={() => setValue("")}
    />
  );
}

describe("SearchField", () => {
  it("provides one consistent searchbox and a keyboard-sized clear action", async () => {
    const user = userEvent.setup();
    render(<SearchHarness />);

    const search = screen.getByRole("searchbox", { name: "Search recipes" });
    await user.type(search, "tofu");
    expect(search).toHaveValue("tofu");

    await user.click(screen.getByRole("button", { name: "Clear search recipes" }));
    expect(search).toHaveValue("");
    expect(screen.queryByRole("button", { name: "Clear search recipes" })).not.toBeInTheDocument();
  });

  it("gives segmented tabs one roving keyboard interaction", async () => {
    const user = userEvent.setup();
    function Tabs() {
      const [selected, setSelected] = useState("week");
      return (
        <TabList label="Planning views">
          {(["week", "day", "prep"] as const).map((value) => (
            <button key={value} role="tab" aria-selected={selected === value} tabIndex={selected === value ? 0 : -1} onClick={() => setSelected(value)}>{value}</button>
          ))}
        </TabList>
      );
    }

    render(<Tabs />);
    const week = screen.getByRole("tab", { name: "week" });
    week.focus();
    await user.keyboard("{ArrowRight}");
    expect(screen.getByRole("tab", { name: "day" })).toHaveFocus();
    expect(screen.getByRole("tab", { name: "day" })).toHaveAttribute("aria-selected", "true");
    await user.keyboard("{End}");
    expect(screen.getByRole("tab", { name: "prep" })).toHaveFocus();
  });
});
