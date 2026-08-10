import * as Dialog from "@radix-ui/react-dialog";
import { Slot } from "@radix-ui/react-slot";
import {
  type ButtonHTMLAttributes,
  type InputHTMLAttributes,
  type ReactElement,
  type ReactNode,
  cloneElement,
  useId,
  useState,
} from "react";

import { decimal6 } from "../app/api/generated/decimal";
import "./shared.css";

export function Button({ asChild, className = "", ...props }: ButtonHTMLAttributes<HTMLButtonElement> & { asChild?: boolean }) {
  const Component = asChild ? Slot : "button";
  return <Component className={`button ${className}`} {...props} />;
}

export function Field({ label, error, hint, children }: { label: string; error?: string; hint?: string; children: ReactElement<{ "aria-labelledby"?: string; "aria-describedby"?: string }> }) {
  const fieldId = useId();
  const labelId = `${fieldId}-label`;
  const descriptionId = hint || error ? `${fieldId}-description` : undefined;
  return (
    <div className="field">
      <span id={labelId} className="field__label">{label}</span>
      {cloneElement(children, { "aria-labelledby": labelId, "aria-describedby": descriptionId })}
      {hint && !error ? <span id={descriptionId} className="field__hint">{hint}</span> : null}
      {error ? <span id={descriptionId} className="field__error">{error}</span> : null}
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

export function ConfirmDialog({ trigger, title, description, confirmLabel, onConfirm }: { trigger: ReactNode; title: string; description: string; confirmLabel: string; onConfirm: () => void }) {
  return (
    <Dialog.Root>
      <Dialog.Trigger asChild>{trigger}</Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Overlay className="dialog-overlay" />
        <Dialog.Content className="dialog" aria-describedby="confirm-description">
          <Dialog.Title>{title}</Dialog.Title>
          <Dialog.Description id="confirm-description">{description}</Dialog.Description>
          <div className="actions">
            <Dialog.Close asChild><Button>Cancel</Button></Dialog.Close>
            <Dialog.Close asChild><Button className="button--danger" onClick={onConfirm}>{confirmLabel}</Button></Dialog.Close>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

export function PollingStatusBadge({ status }: { status: "queued" | "running" | "retry_wait" | "succeeded" | "failed" | "cancelled" | "superseded" }) {
  const active = ["queued", "running", "retry_wait"].includes(status);
  return <span className={`status status--${status}`} role="status" aria-live={active ? "polite" : "off"}>{status.replace("_", " ")}</span>;
}

export function Skeleton({ label, lines = 2 }: { label: string; lines?: number }) {
  return <div className="skeleton" role="status" aria-label={label}>{Array.from({ length: lines }, (_, index) => <span key={index} />)}</div>;
}

export function EmptyState({ title, description, action }: { title: string; description: string; action?: ReactNode }) {
  return <section className="empty-state"><h2>{title}</h2><p>{description}</p>{action}</section>;
}

export function ErrorRecovery({ title, description = "Try again. If the problem continues, check service health.", actionLabel = "Try again", onRetry }: { title: string; description?: string; actionLabel?: string; onRetry: () => void }) {
  return <section className="error-recovery" role="alert"><h2>{title}</h2><p>{description}</p><Button onClick={onRetry}>{actionLabel}</Button></section>;
}
