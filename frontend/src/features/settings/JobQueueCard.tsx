import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";
import { Button } from "../../components";

export interface JobQueueCardProps {
  icon: LucideIcon;
  title: string;
  description: string;
  active: number;
  waiting: number;
  missing?: number;
  running?: boolean;
  error?: string;
  supportsMissing?: boolean;
  allLabel?: string;
  missingLabel?: string;
  onRunAll: () => void;
  onRunMissing?: () => void;
  allPending?: boolean;
  missingPending?: boolean;
  children?: ReactNode;
}

export function JobQueueCard({
  icon: Icon,
  title,
  description,
  active,
  waiting,
  missing = 0,
  running = false,
  error,
  supportsMissing = false,
  allLabel = "Run all",
  missingLabel = "Run missing only",
  onRunAll,
  onRunMissing,
  allPending = false,
  missingPending = false,
  children,
}: JobQueueCardProps) {
  const busy = allPending || missingPending || running;

  return (
    <article className="job-queue-card">
      <div className="job-queue-card__main">
        <div className="job-queue-card__heading">
          <span className="job-queue-card__icon"><Icon aria-hidden="true" /></span>
          <div>
            <h3>{title}</h3>
            <p>{description}</p>
          </div>
          {running ? <span className="settings-status settings-status--working">Working</span> : null}
        </div>

        <div className="job-queue-card__counts" aria-label={`${title} queue counts`}>
          <div><strong>{active}</strong><span>Active</span></div>
          <div><strong>{waiting}</strong><span>Waiting</span></div>
          {supportsMissing ? <div><strong>{missing}</strong><span>Missing</span></div> : null}
        </div>
        {children}
        {error ? <p className="error-text" role="alert">{error}</p> : null}
      </div>

      <div className="job-queue-card__actions">
        <Button type="button" onClick={onRunAll} disabled={busy}>
          {allPending ? "Queueing…" : allLabel}
        </Button>
        {supportsMissing && onRunMissing ? (
          <Button type="button" variant="secondary" onClick={onRunMissing} disabled={busy || missing === 0}>
            {missingPending ? "Queueing…" : missingLabel}
          </Button>
        ) : null}
      </div>
    </article>
  );
}
