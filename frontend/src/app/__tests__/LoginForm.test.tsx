import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { LoginForm } from "../LoginForm";

function json(body: unknown, status = 200) {
  return Promise.resolve(
    new Response(status === 204 ? null : JSON.stringify(body), {
      status,
      headers: { "content-type": "application/json" },
    }),
  );
}

function renderForm() {
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false, staleTime: 0 },
      mutations: { retry: false },
    },
  });
  return render(
    <QueryClientProvider client={client}>
      <LoginForm />
    </QueryClientProvider>,
  );
}

describe("owner login", () => {
  beforeEach(() => {
    vi.stubGlobal("crypto", {
      randomUUID: vi.fn(() => "00000000-0000-4000-8000-000000000999"),
    });
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("submits owner credentials to create a session", async () => {
    const fetchMock = vi.fn((input, init) => {
      if (String(input).endsWith("/auth/session") && init?.method === "POST") return json(null, 204);
      return json({}, 404);
    });
    vi.stubGlobal("fetch", fetchMock);

    renderForm();
    const user = userEvent.setup();
    await user.type(screen.getByLabelText("Email"), "owner@example.com");
    await user.type(screen.getByLabelText("Password"), "u5wwGRSEF04X9Tccn2C0k9tx");
    await user.click(screen.getByRole("button", { name: "Sign in" }));

    await vi.waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/v1/auth/session",
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({ email: "owner@example.com", password: "u5wwGRSEF04X9Tccn2C0k9tx" }),
        }),
      );
    });
  });

  it("lets someone reveal their password without changing the submitted value", async () => {
    vi.stubGlobal("fetch", vi.fn(() => json(null, 204)));
    renderForm();
    const user = userEvent.setup();
    const password = screen.getByLabelText("Password");

    expect(password).toHaveAttribute("type", "password");
    await user.click(screen.getByRole("button", { name: "Show password" }));
    expect(password).toHaveAttribute("type", "text");
    expect(screen.getByRole("button", { name: "Hide password" })).toHaveAttribute("aria-pressed", "true");
  });

  it("surfaces an invalid-credentials message without signing in", async () => {
    const problem = { detail: "Email or password is incorrect.", code: "invalid_credentials" };
    vi.stubGlobal(
      "fetch",
      vi.fn((input, init) => {
        if (String(input).endsWith("/auth/session") && init?.method === "POST") return json(problem, 401);
        return json({}, 404);
      }),
    );

    renderForm();
    const user = userEvent.setup();
    await user.type(screen.getByLabelText("Email"), "owner@example.com");
    await user.type(screen.getByLabelText("Password"), "a-too-short-password");
    await user.click(screen.getByRole("button", { name: "Sign in" }));

    expect(await screen.findByText("Email or password is incorrect.")).toBeVisible();
  });
});
