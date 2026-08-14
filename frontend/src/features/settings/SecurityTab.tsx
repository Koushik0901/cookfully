import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useState } from "react";

import { Button, ConfirmDialog, EmptyState, ErrorRecovery, Field, Skeleton } from "../../components";
import { accountApi } from "./api";
import { useSignOut } from "./useSignOut";

function dateLabel(value: string): string {
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(
    new Date(value),
  );
}

export function SecurityTab() {
  const queryClient = useQueryClient();
  const sessions = useQuery({ queryKey: ["auth-sessions"], queryFn: accountApi.sessions });
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [passwordError, setPasswordError] = useState("");
  const [passwordSaved, setPasswordSaved] = useState(false);
  const [notice, setNotice] = useState("");

  const changePassword = useMutation({
    mutationFn: accountApi.changePassword,
    onSuccess: async () => {
      setCurrentPassword("");
      setNewPassword("");
      setPasswordError("");
      setPasswordSaved(true);
      await queryClient.invalidateQueries({ queryKey: ["auth-sessions"] });
    },
    onError: () =>
      setPasswordError("The password could not be changed. Check the current password and try again."),
  });

  const revokeSession = useMutation({
    mutationFn: accountApi.revokeSession,
    onSuccess: async () => {
      setNotice("Session signed out. It can no longer access your account.");
      await queryClient.invalidateQueries({ queryKey: ["auth-sessions"] });
    },
    onError: () => setNotice("The session could not be signed out. Reload and try again."),
  });

  const signOut = useSignOut();

  function submitPassword(event: FormEvent) {
    event.preventDefault();
    setPasswordError("");
    setPasswordSaved(false);
    if (newPassword.length < 12) {
      setPasswordError("Use at least 12 characters for the new password.");
      return;
    }
    changePassword.mutate({ currentPassword, newPassword });
  }

  if (sessions.isPending) return <Skeleton label="Loading sessions" lines={4} />;
  if (sessions.isError) {
    return (
      <ErrorRecovery
        title="Sessions could not be loaded"
        onRetry={() => void sessions.refetch()}
      />
    );
  }
  const sessionList = sessions.data?.sessions ?? [];

  return (
    <div className="stack">
      <form className="settings-section" onSubmit={submitPassword}>
        <div className="section-heading">
          <div>
            <h2>Change password</h2>
            <p className="muted">Rotate your sign-in credential. Every other session is signed out.</p>
          </div>
        </div>
        <div className="form-grid">
          <Field label="Current password">
            <input
              className="input"
              type="password"
              autoComplete="current-password"
              value={currentPassword}
              onChange={(event) => setCurrentPassword(event.target.value)}
            />
          </Field>
          <Field label="New password" hint="At least 12 characters." error={passwordError}>
            <input
              className="input"
              type="password"
              autoComplete="new-password"
              value={newPassword}
              onChange={(event) => setNewPassword(event.target.value)}
            />
          </Field>
        </div>
        {passwordSaved ? (
          <p className="success-text" role="status">
            Password changed. Other sessions were signed out.
          </p>
        ) : null}
        <div className="actions">
          <Button type="submit" disabled={changePassword.isPending}>
            {changePassword.isPending ? "Changing…" : "Change password"}
          </Button>
        </div>
      </form>

      <section className="settings-section" aria-labelledby="sessions-heading">
        <div className="section-heading">
          <div>
            <h2 id="sessions-heading">Active sessions</h2>
            <p className="muted">Devices currently signed in to your account.</p>
          </div>
        </div>
        {notice ? (
          <p className="notice" role="status">
            {notice}
          </p>
        ) : null}
        {sessionList.length === 0 ? (
          <EmptyState title="No sessions" description="Sign in from a device to see it here." />
        ) : (
          <div className="token-list">
            {sessionList.map((session) => (
              <article key={session.id} className="token-card" aria-label={session.clientLabel ?? "Session"}>
                <div className="section-heading">
                  <div>
                    <h3>{session.clientLabel ?? "Unknown device"}</h3>
                    <p className="muted">
                      {session.isCurrent ? "This device · " : ""}signed in {dateLabel(session.createdAt)} ·
                      last seen {dateLabel(session.lastSeenAt)}
                    </p>
                  </div>
                  {session.isCurrent ? null : (
                    <ConfirmDialog
                      trigger={<Button type="button" variant="destructive">Sign out</Button>}
                      title="Sign out this device?"
                      description="This session will stop working immediately. This cannot be undone."
                      confirmLabel="Sign out device"
                      onConfirm={() => revokeSession.mutate(session.id)}
                    />
                  )}
                </div>
              </article>
            ))}
          </div>
        )}
      </section>

      <section className="settings-section" aria-labelledby="signout-heading">
        <div className="section-heading">
          <div>
            <h2 id="signout-heading">Sign out</h2>
            <p className="muted">End your current session on this device.</p>
          </div>
        </div>
        <div className="actions">
          <Button
            type="button"
            variant="secondary"
            onClick={() => signOut.mutate()}
            disabled={signOut.isPending}
          >
            Sign out
          </Button>
        </div>
        {signOut.isError ? <p className="error-text" role="alert">Couldn’t sign out. Try again.</p> : null}
      </section>
    </div>
  );
}
