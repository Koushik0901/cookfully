import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";

import { FoodPicker } from "../FoodPicker";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

it("creates a custom food from the matcher and applies it to the ingredient", async () => {
  const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const path = String(input);
    if (path.includes("/candidates")) {
      return Promise.resolve(new Response(JSON.stringify({ query: "tofu", candidates: [] }), { headers: { "content-type": "application/json" } }));
    }
    if (path.endsWith("/foods/user") && init?.method === "POST") {
      return Promise.resolve(new Response(JSON.stringify({ id: "custom-food-1" }), { status: 201, headers: { "content-type": "application/json" } }));
    }
    if (path.includes("/owner-food/") && init?.method === "POST") {
      return Promise.resolve(new Response(null, { status: 204 }));
    }
    if (path.includes("/nutrition/recalculate") && init?.method === "POST") {
      return Promise.resolve(new Response(JSON.stringify({ jobId: "job-1", resourceId: "recipe-1", status: "queued" }), { status: 202, headers: { "content-type": "application/json" } }));
    }
    return Promise.resolve(new Response("Not found", { status: 404 }));
  });
  vi.stubGlobal("fetch", fetchMock);

  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <FoodPicker
        recipeId="recipe-1"
        ingredientId="ingredient-1"
        ingredientName="16 oz tofu"
        trigger={<button type="button">Choose food</button>}
        onSelected={vi.fn()}
      />
    </QueryClientProvider>,
  );
  const user = userEvent.setup();

  await user.click(screen.getByRole("button", { name: "Choose food" }));
  await user.click(screen.getByRole("button", { name: "Create custom food" }));
  await user.clear(screen.getByLabelText("Food name"));
  await user.type(screen.getByLabelText("Food name"), "House tofu");
  await user.type(screen.getByLabelText("Calories"), "120");
  await user.type(screen.getByLabelText("Protein (g)"), "12");
  await user.type(screen.getByLabelText("Carbohydrate (g)"), "4");
  await user.type(screen.getByLabelText("Fat (g)"), "6");
  await user.click(screen.getByRole("button", { name: "Create food" }));

  await waitFor(() => expect(fetchMock.mock.calls.some(([input, init]) => String(input).includes("/owner-food/") && init?.method === "POST")).toBe(true));
  expect(fetchMock.mock.calls.some(([input, init]) => String(input).includes("/nutrition/recalculate") && init?.method === "POST")).toBe(true);
});

it("closes the matcher after selecting a reference food", async () => {
  const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const path = String(input);
    if (path.includes("/candidates")) {
      return Promise.resolve(new Response(JSON.stringify({
        query: "cashew nuts",
        candidates: [{
          source: "usda",
          id: "food-cashew-1",
          description: "Nuts, cashew nuts, raw",
          brandOwner: null,
          servingSizeG: "28.000000",
          servingUnit: "oz",
          compatibility: "compatible",
        }],
      }), { headers: { "content-type": "application/json" } }));
    }
    if (path.includes("/nutrition/corrections") && init?.method === "POST") {
      return Promise.resolve(new Response(JSON.stringify({}), { status: 201, headers: { "content-type": "application/json" } }));
    }
    if (path.includes("/nutrition/recalculate") && init?.method === "POST") {
      return Promise.resolve(new Response(JSON.stringify({ jobId: "job-1", resourceId: "recipe-1", status: "queued" }), { status: 202, headers: { "content-type": "application/json" } }));
    }
    return Promise.resolve(new Response("Not found", { status: 404 }));
  });
  vi.stubGlobal("fetch", fetchMock);

  const onSelected = vi.fn();
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <FoodPicker
        recipeId="recipe-1"
        ingredientId="ingredient-1"
        ingredientName="whole cashew nuts"
        trigger={<button type="button">Choose food</button>}
        onSelected={onSelected}
      />
    </QueryClientProvider>,
  );
  const user = userEvent.setup();

  await user.click(screen.getByRole("button", { name: "Choose food" }));
  await user.click(screen.getByRole("button", { name: /Nuts, cashew nuts, raw USDA/ }));

  await waitFor(() => expect(onSelected).toHaveBeenCalledTimes(1));
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  expect(fetchMock.mock.calls.some(([input, init]) => String(input).includes("/nutrition/corrections") && init?.method === "POST")).toBe(true);
});
