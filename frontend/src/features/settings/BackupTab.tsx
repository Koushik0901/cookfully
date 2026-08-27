import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Archive, Database, HardDrive, RefreshCw, ShieldCheck } from "lucide-react";

import { Button, SectionHeading } from "../../components";
import { ApiProblem } from "../recipes/api";
import { databaseBackupsApi } from "./api";

function formatBytes(bytes: number): string {
  if (bytes < 1_024) return `${bytes} B`;
  const units = ["KB", "MB", "GB", "TB"];
  let value = bytes;
  let unit = -1;
  while (value >= 1_024 && unit < units.length - 1) {
    value /= 1_024;
    unit += 1;
  }
  return `${value.toLocaleString(undefined, { maximumFractionDigits: 1 })} ${units[unit]}`;
}

function formatTime(value: string | null | undefined): string {
  if (!value) return "No successful backup yet";
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
}

function failureMessage(error: unknown): string | null {
  if (error instanceof ApiProblem || error instanceof Error) return error.message;
  return error ? "Cookfully could not queue a database backup. Try again." : null;
}

export function BackupTab() {
  const queryClient = useQueryClient();
  const backups = useQuery({
    queryKey: ["database-backups"],
    queryFn: databaseBackupsApi.status,
    refetchInterval: 30_000,
  });
  const request = useMutation({
    mutationFn: databaseBackupsApi.request,
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["database-backups"] }),
  });
  const data = backups.data;
  const error = failureMessage(request.error) ?? failureMessage(backups.error);

  return (
    <section className="settings-section backup-section" aria-labelledby="backup-title">
      <SectionHeading
        id="backup-title"
        eyebrow="Kitchen safety"
        title="Backups"
        description="Your kitchen lives in a folder on this computer, not in a Docker volume. Cookfully keeps a full database restore point on a regular schedule."
      />

      <div className="backup-section__promise" role="note">
        <HardDrive aria-hidden="true" />
        <div>
          <strong>Host-owned storage is active</strong>
          <p>Recipes, nutrition data, photos, exports, and the erasure ledger stay on the host disk even if a container is replaced.</p>
        </div>
      </div>

      <article className="backup-card">
        <div className="backup-card__heading">
          <span className="backup-card__icon"><Database aria-hidden="true" /></span>
          <div>
            <h3>Database restore points</h3>
            <p>Full PostgreSQL dumps include your recipes, nutrition information, account, sessions, and background work.</p>
          </div>
        </div>
        <dl className="backup-card__facts">
          <div><dt>Schedule</dt><dd>{data ? `${data.schedule} every day` : "Checking…"}</dd></div>
          <div><dt>Keep</dt><dd>{data ? `${data.retentionCount} recent dumps` : "Checking…"}</dd></div>
          <div><dt>Latest</dt><dd>{formatTime(data?.latest?.createdAt)}</dd></div>
        </dl>
        {data?.lastFailure ? <p className="error-text" role="alert">Last attempt: {data.lastFailure.message} ({formatTime(data.lastFailure.occurredAt)}).</p> : null}
        {error ? <p className="error-text" role="alert">{error}</p> : null}
        <div className="backup-card__actions">
          <Button onClick={() => request.mutate()} disabled={request.isPending || data?.pendingManualRequest}>
            <RefreshCw aria-hidden="true" />
            {data?.pendingManualRequest ? "Backup queued" : request.isPending ? "Queuing backup…" : "Create backup now"}
          </Button>
          {request.isSuccess ? <span className="settings-status" role="status">Queued safely</span> : null}
        </div>
      </article>

      <article className="backup-card backup-card--secondary">
        <div className="backup-card__heading">
          <span className="backup-card__icon"><Archive aria-hidden="true" /></span>
          <div>
            <h3>Recent restore points</h3>
            <p>Each entry is checksum-verified before it appears here.</p>
          </div>
        </div>
        {data?.backups.length ? (
          <ol className="backup-card__list">
            {data.backups.map((backup) => (
              <li key={backup.filename}>
                <span><strong>{formatTime(backup.createdAt)}</strong><small>{backup.reason === "manual" ? "Manual backup" : backup.reason === "host-copy" ? "Host copy" : "Scheduled backup"}</small></span>
                <small>{formatBytes(backup.bytes)}</small>
              </li>
            ))}
          </ol>
        ) : <p className="muted">The first scheduled backup will appear here after it finishes. You can create one now instead.</p>}
      </article>

      <div className="backup-section__note">
        <ShieldCheck aria-hidden="true" />
        <p><strong>One more copy still matters.</strong> Database dumps protect the database; use the included host-backup task to copy those dumps, recipe photos, and the independent erasure ledger to another local disk. Restore stays a staged operator workflow so an older backup cannot resurrect erased data.</p>
      </div>
    </section>
  );
}
