import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { Button, Field } from "../components";
import { apiRequest } from "../features/recipes/api";

export function LoginForm() {
  const queryClient = useQueryClient();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const login = useMutation({
    mutationFn: () =>
      apiRequest<void>("/auth/session", {
        method: "POST",
        body: JSON.stringify({ email, password }),
      }),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["owner-session"] }),
  });

  return (
    <form
      className="login-form"
      onSubmit={(event) => {
        event.preventDefault();
        login.mutate();
      }}
    >
      <Field label="Email">
        <input
          className="input"
          type="email"
          autoComplete="username"
          required
          value={email}
          onChange={(event) => setEmail(event.target.value)}
        />
      </Field>
      <Field label="Password">
        <input
          className="input"
          type="password"
          autoComplete="current-password"
          required
          value={password}
          onChange={(event) => setPassword(event.target.value)}
        />
      </Field>
      {login.isError ? (
        <p className="error-text" role="alert">
          {login.error instanceof Error ? login.error.message : "Sign in failed. Try again."}
        </p>
      ) : null}
      <div className="actions">
        <Button type="submit" disabled={login.isPending}>
          {login.isPending ? "Signing in…" : "Sign in"}
        </Button>
      </div>
    </form>
  );
}
