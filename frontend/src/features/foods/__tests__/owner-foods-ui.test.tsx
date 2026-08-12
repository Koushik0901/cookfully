import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, expect, it, vi } from "vitest";

import { OwnerFoodsPage } from "../OwnerFoodsPage";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

it("renders exact-decimal API food values without crashing", async () => {
  vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(new Response(JSON.stringify([{
    id: "00000000-0000-4000-8000-000000000001",
    displayName: "Vanilla whey",
    normalizedName: "vanilla whey",
    brand: "Kitchen label",
    caloriesKcal: "121.000000",
    proteinG: "24.500000",
    carbohydrateG: "3.000000",
    fatG: "1.250000",
    basisGrams: "31.000000",
    typicalServingG: "31.000000",
    typicalServingUnit: "scoop",
    version: 1,
  }]), { headers: { "content-type": "application/json" } }))));
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}><MemoryRouter><OwnerFoodsPage /></MemoryRouter></QueryClientProvider>);

  expect(await screen.findByRole("heading", { name: "Vanilla whey" })).toBeVisible();
  expect(screen.getByText("121 kcal")).toBeVisible();
  expect(screen.getByText("24.5 g")).toBeVisible();
  expect(screen.getByText("3 g")).toBeVisible();
  expect(screen.getByText("1.3 g")).toBeVisible();
  expect(screen.getByText("per 31g · 31g (1 scoop)")).toBeVisible();
});

it("turns a product label into a reusable food without exposing a form wall", async () => {
  const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    if (init?.method === "POST") {
      return Promise.resolve(new Response(JSON.stringify({
        id: "00000000-0000-4000-8000-000000000002",
        displayName: "Oat milk",
        normalizedName: "oat milk",
        brand: "Kitchen label",
        caloriesKcal: "120",
        proteinG: "3",
        carbohydrateG: "16",
        fatG: "5",
        basisGrams: "240",
        typicalServingG: "240",
        typicalServingUnit: "cup",
        version: 1,
      }), { status: 201, headers: { "content-type": "application/json" } }));
    }
    return Promise.resolve(new Response("[]", { headers: { "content-type": "application/json" } }));
  });
  vi.stubGlobal("fetch", fetchMock);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}><MemoryRouter><OwnerFoodsPage /></MemoryRouter></QueryClientProvider>);
  const user = userEvent.setup();

  await user.click(await screen.findByRole("button", { name: "New food" }));
  expect(screen.getByRole("dialog", { name: "Add a food you know" })).toBeVisible();
  expect(screen.getByText("Identify the food")).toBeVisible();
  expect(screen.getByText("Copy one label serving")).toBeVisible();

  await user.type(screen.getByLabelText("Food name"), "Oat milk");
  await user.type(screen.getByLabelText("Brand (optional)"), "Kitchen label");
  await user.type(screen.getByLabelText("Calories"), "120");
  await user.type(screen.getByLabelText("Protein (g)"), "3");
  await user.type(screen.getByLabelText("Carbohydrate (g)"), "16");
  await user.type(screen.getByLabelText("Fat (g)"), "5");
  await user.clear(screen.getByLabelText("Label serving weight"));
  await user.type(screen.getByLabelText("Label serving weight"), "240");
  await user.type(screen.getByLabelText("Serving name (optional)"), "cup");
  await user.click(screen.getByRole("button", { name: "Create food" }));

  await waitFor(() => expect(fetchMock.mock.calls.some(([, init]) => init?.method === "POST")).toBe(true));
  const post = fetchMock.mock.calls.find(([, init]) => init?.method === "POST");
  expect(JSON.parse(String(post?.[1]?.body))).toMatchObject({
    displayName: "Oat milk",
    basisGrams: 240,
    typicalServingG: 240,
    typicalServingUnit: "cup",
  });
});
