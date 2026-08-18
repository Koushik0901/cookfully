import * as Dialog from "@radix-ui/react-dialog";
import {
  type ComponentProps,
  type InputHTMLAttributes,
  type ReactElement,
  type ReactNode,
  cloneElement,
  useId,
  useState,
} from "react";

import { decimal6 } from "../app/api/generated/decimal";
import { KitchenCompanion } from "./cookfully/KitchenCompanion";
import { Button as ShadcnButton } from "./ui/button";
import { Select } from "./ui/select";
import { MacroPreview, MacroRing } from "./MacroPreview";

export function Button(props: ComponentProps<typeof ShadcnButton>) {
  return <ShadcnButton {...props} />;
}

export function BrandMark({ className = "" }: { className?: string }) {
  return <img className={`brand-mark ${className}`} src="/brand/cookfully-mark-512.png" alt="" aria-hidden="true" />;
}

export function Field({ label, error, hint, endAdornment, children }: { label: string; error?: string; hint?: string; endAdornment?: ReactNode; children: ReactElement<{ "aria-labelledby"?: string; "aria-describedby"?: string }> }) {
  const fieldId = useId();
  const labelId = `${fieldId}-label`;
  const message = error ?? hint;
  const descriptionId = message ? `${fieldId}-description` : undefined;
  return (
    <div className="field">
      <span id={labelId} className="field__label">{label}</span>
      {endAdornment ? <span className="field__control">{cloneElement(children, { "aria-labelledby": labelId, "aria-describedby": descriptionId })}{endAdornment}</span> : cloneElement(children, { "aria-labelledby": labelId, "aria-describedby": descriptionId })}
      <span id={descriptionId} className={`field__message${error ? " field__error" : " field__hint"}`} aria-hidden={message ? undefined : true}>{message || "\u00a0"}</span>
    </div>
  );
}

export function DecimalInput({ onValueChange, ...props }: Omit<InputHTMLAttributes<HTMLInputElement>, "onChange"> & { onValueChange?: (value: string) => void }) {
  const [error, setError] = useState("");
  const errorId = useId();
  return (
    <>
      <input
        {...props}
        className={`input data-value ${props.className ?? ""}`}
        inputMode="decimal"
        aria-invalid={Boolean(error)}
        aria-describedby={error ? errorId : props["aria-describedby"]}
        onChange={(event) => {
          const result = decimal6.safeParse(event.currentTarget.value);
          setError(result.success || event.currentTarget.value === "" ? "" : "Use up to six decimal places without an exponent.");
          if (result.success) onValueChange?.(result.data);
        }}
      />
      {error ? <span id={errorId} className="field__error">{error}</span> : null}
    </>
  );
}

export function ConfirmDialog({ trigger, open, onOpenChange, title, description, confirmLabel, onConfirm }: { trigger?: ReactNode; open?: boolean; onOpenChange?: (open: boolean) => void; title: string; description: string; confirmLabel: string; onConfirm: () => void }) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      {trigger ? <Dialog.Trigger asChild>{trigger}</Dialog.Trigger> : null}
      <Dialog.Portal>
        <Dialog.Overlay className="dialog-overlay" />
        <Dialog.Content className="dialog" aria-describedby="confirm-description">
          <Dialog.Title>{title}</Dialog.Title>
          <Dialog.Description id="confirm-description">{description}</Dialog.Description>
          <div className="actions">
            <Dialog.Close asChild><Button variant="secondary">Cancel</Button></Dialog.Close>
            <Dialog.Close asChild><Button variant="destructive" onClick={onConfirm}>{confirmLabel}</Button></Dialog.Close>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

const STATUS_LABELS: Record<string, string> = {
  queued: "Queued",
  running: "Working…",
  retry_wait: "Retrying",
  succeeded: "Done",
  failed: "Failed",
  cancelled: "Cancelled",
  superseded: "Updated",
};

export function PollingStatusBadge({ status }: { status: string }) {
  const active = ["queued", "running", "retry_wait"].includes(status);
  return <span className={`status status--${status}`} role="status" aria-live={active ? "polite" : "off"}>{STATUS_LABELS[status] ?? status}</span>;
}

export function PageHeader({ eyebrow, title, description, actions }: { eyebrow: string; title: string; description?: string; actions?: ReactNode }) {
  return (
    <header className="page-header">
      <div className="page-header__copy">
        <p className="eyebrow">{eyebrow}</p>
        <h1>{title}</h1>
        {description ? <p className="lede">{description}</p> : null}
      </div>
      {actions ? <div className="actions">{actions}</div> : null}
    </header>
  );
}

export function Skeleton({ label, lines = 2 }: { label: string; lines?: number }) {
  return (
    <div className="skeleton" role="status" aria-label={label}>
      <KitchenCompanion moment="loading" size="sm" className="skeleton__companion" />
      <span className="skeleton__title" />
      {Array.from({ length: lines }, (_, index) => <span key={index} />)}
    </div>
  );
}

export function EmptyState({ title, description, action, motif = true, headingLevel = "h2" }: { title: string; description: string; action?: ReactNode; motif?: boolean; headingLevel?: "h1" | "h2" }) {
  const Heading = headingLevel;
  return (
    <section className="empty-state">
      {motif ? <KitchenCompanion moment="empty" size="md" className="empty-state__companion" /> : null}
      <Heading>{title}</Heading>
      <p>{description}</p>
      {action ? <div className="empty-state__action">{action}</div> : null}
    </section>
  );
}

export function ErrorRecovery({ title, description = "Try again. If it keeps happening, your recipes are safe.", actionLabel = "Try again", onRetry }: { title: string; description?: string; actionLabel?: string; onRetry: () => void }) {
  return <section className="error-recovery" role="alert"><KitchenCompanion moment="error" size="sm" className="error-recovery__companion" /><div className="error-recovery__copy"><h2>{title}</h2><p>{description}</p></div><Button onClick={onRetry}>{actionLabel}</Button></section>;
}

export { MacroPreview, MacroRing };
export { KitchenCompanion } from "./cookfully/KitchenCompanion";
export { Select };
