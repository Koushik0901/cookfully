import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, type ReactNode, useState } from "react";

import { Button, ConfirmDialog, EmptyState, ErrorRecovery, Field, PageHeader, Skeleton } from "../../components";
import { Checkbox } from "@/components/ui/checkbox";
import { agentAccessApi } from "./api";
import type { AccessTokenCreated, AccessTokenScope } from "./types";

const SCOPES: Array<{ scope: AccessTokenScope; label: string; description: string }> = [
  { scope: "recipes:read", label: "Read recipes", description: "Search recipe metadata and nutrition." },
  { scope: "goals:read", label: "Read goals", description: "Read current calorie and macro targets." },
  { scope: "plans:read", label: "Read meal plans", description: "Read entries, snapshots, and period totals." },
  { scope: "plans:write", label: "Write meal plans", description: "Add, update, and remove planned recipes." },
  { scope: "grocery:read", label: "Read grocery lists", description: "Read generated and manual grocery items." },
  { scope: "grocery:write", label: "Write grocery lists", description: "Regenerate grocery lists." },
];

const DEFAULT_SCOPES = new Set<AccessTokenScope>(["goals:read", "plans:read"]);

function dateLabel(value: string | null | undefined): string {
  if (!value) return "Never";
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(
    new Date(value),
  );
}

export function AgentAccessPage({ embedded = false }: { embedded?: boolean }) {
  const queryClient = useQueryClient();
  const tokens = useQuery({ queryKey: ["access-tokens"], queryFn: agentAccessApi.list });
  const [name, setName] = useState("");
  const [expiresAt, setExpiresAt] = useState("");
  const [selectedScopes, setSelectedScopes] = useState(DEFAULT_SCOPES);
  const [oneTimeToken, setOneTimeToken] = useState<AccessTokenCreated | null>(null);
  const [formError, setFormError] = useState("");
  const [notice, setNotice] = useState("");
  const [copyStatus, setCopyStatus] = useState("");

  const createToken = useMutation({
    mutationFn: agentAccessApi.create,
    onSuccess: async (created) => {
      setOneTimeToken(created);
      setName("");
      setExpiresAt("");
      setCopyStatus("");
      setNotice("Token created. Store the secret before dismissing it.");
      await queryClient.invalidateQueries({ queryKey: ["access-tokens"] });
    },
    onError: () => setFormError("The access token could not be created. Review the fields and try again."),
  });
  const revokeToken = useMutation({
    mutationFn: agentAccessApi.revoke,
    onSuccess: async () => {
      setNotice("Token revoked. Existing connections can no longer use it.");
      await queryClient.invalidateQueries({ queryKey: ["access-tokens"] });
    },
    onError: () => setNotice("The token could not be revoked. Reload and try again."),
  });

  function toggleScope(scope: AccessTokenScope) {
    setSelectedScopes((current) => {
      const next = new Set(current);
      if (next.has(scope)) next.delete(scope);
      else next.add(scope);
      return next;
    });
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFormError("");
    setNotice("");
    const normalizedName = name.trim();
    if (!normalizedName) {
      setFormError("Enter a name that identifies the assistant or connection.");
      return;
    }
    if (selectedScopes.size === 0) {
      setFormError("Select at least one scope.");
      return;
    }
    createToken.mutate({
      name: normalizedName,
      scopes: SCOPES.map(({ scope }) => scope).filter((scope) => selectedScopes.has(scope)),
      expiresAt: expiresAt ? new Date(expiresAt).toISOString() : null,
    });
  }

  async function copySecret() {
    if (!oneTimeToken) return;
    try {
      await navigator.clipboard.writeText(oneTimeToken.secret);
      setCopyStatus("Copied to clipboard.");
    } catch {
      setCopyStatus("Copy failed. Select the token and copy it manually.");
    }
  }

  const description = "Connect an external assistant with narrowly scoped tokens, then revoke access whenever you need to.";
  const frame = (content: ReactNode) => embedded
    ? <><div className="settings-system-intro"><p className="eyebrow">System connection</p><h2>Agent access</h2><p>{description}</p></div>{content}</>
    : <main className="page-shell"><PageHeader eyebrow="System access" title="Agent access" description={description} />{content}</main>;

  if (tokens.isPending) return frame(<Skeleton label="Loading agent access" lines={8} />);
  if (tokens.isError) {
    return frame(<ErrorRecovery title="Agent access could not be loaded" onRetry={() => void tokens.refetch()} />);
  }
  const activeTokens = tokens.data.filter((token) => !token.revokedAt);

  return frame(
    <>
      {notice ? <p className="notice" role="status">{notice}</p> : null}

      {oneTimeToken ? (
        <section className="one-time-secret" role="region" aria-label="One-time token secret">
          <div>
            <p className="eyebrow">Store this now</p>
            <h2>One-time token secret</h2>
          </div>
          <p>This secret is shown only once. It cannot be recovered after you dismiss it.</p>
          <code className="token-secret">{oneTimeToken.secret}</code>
          <div className="actions">
            <Button type="button" onClick={() => void copySecret()}>Copy token</Button>
            <Button type="button" variant="secondary" onClick={() => { setOneTimeToken(null); setCopyStatus(""); }}>I have stored it</Button>
          </div>
          {copyStatus ? <p role="status">{copyStatus}</p> : null}
        </section>
      ) : null}

      <form className="settings-section" onSubmit={submit}>
        <div className="section-heading">
          <div><h2>Create token</h2><p className="muted">Read-only defaults are selected. Add write scopes only when the client truly needs them.</p></div>
        </div>
        <div className="form-grid">
          <Field label="Token name" hint="For example, Home Assistant meal planner.">
            <input className="input" value={name} maxLength={120} onChange={(event) => setName(event.target.value)} />
          </Field>
          <Field label="Expires at (optional)" hint="Leave blank for no automatic expiry.">
            <input className="input" type="datetime-local" value={expiresAt} onChange={(event) => setExpiresAt(event.target.value)} />
          </Field>
        </div>
        <fieldset className="scope-picker">
          <legend>Allowed scopes</legend>
          {SCOPES.map(({ scope, label, description }) => (
            <label key={scope} className="scope-option">
              <Checkbox aria-label={label} checked={selectedScopes.has(scope)} onCheckedChange={() => toggleScope(scope)} />
              <span><strong>{label}</strong><small>{description}</small><code>{scope}</code></span>
            </label>
          ))}
        </fieldset>
        {formError ? <p className="field__error" role="alert">{formError}</p> : null}
        <div className="actions"><Button type="submit" disabled={createToken.isPending}>{createToken.isPending ? "Creating…" : "Create access token"}</Button></div>
      </form>

      <section className="stack" aria-labelledby="active-tokens-heading">
        <div className="section-heading"><div><h2 id="active-tokens-heading">Active tokens</h2><p className="muted">Secrets are never shown here.</p></div></div>
        {activeTokens.length === 0 ? (
          <EmptyState title="No active tokens" description="Create a token when an external client needs access." />
        ) : (
          <div className="token-list">
            {activeTokens.map((token) => (
              <article key={token.id} className="token-card" aria-label={token.name}>
                <div className="section-heading">
                  <div><h3>{token.name}</h3><p className="muted">Created {dateLabel(token.createdAt)}</p></div>
                  <ConfirmDialog
                    trigger={<Button type="button" variant="destructive">Revoke</Button>}
                    title="Revoke access token?"
                    description={`${token.name} will stop working immediately. This cannot be undone.`}
                    confirmLabel="Revoke token"
                    onConfirm={() => revokeToken.mutate(token.id)}
                  />
                </div>
                <dl className="token-metadata">
                  <div><dt>Scopes</dt><dd>{token.scopes.join(", ")}</dd></div>
                  <div><dt>Last used</dt><dd>{dateLabel(token.lastUsedAt)}</dd></div>
                  <div><dt>Expires</dt><dd>{dateLabel(token.expiresAt)}</dd></div>
                </dl>
              </article>
            ))}
          </div>
        )}
      </section>
    </>
  );
}
