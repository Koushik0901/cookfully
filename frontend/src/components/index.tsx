import * as Dialog from "@radix-ui/react-dialog";
import {
  type ComponentProps,
  type InputHTMLAttributes,
  type KeyboardEvent as ReactKeyboardEvent,
  type ReactElement,
  type ReactNode,
  cloneElement,
  useId,
  useState,
} from "react";
import { Search, X } from "lucide-react";

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

export function Field({ label, error, hint, endAdornment, accessibilityLabel, children }: { label: string; error?: string; hint?: string; endAdornment?: ReactNode; accessibilityLabel?: string; children: ReactElement<{ "aria-label"?: string; "aria-labelledby"?: string; "aria-describedby"?: string }> }) {
  const fieldId = useId();
  const labelId = `${fieldId}-label`;
  const message = error ?? hint;
  const descriptionId = message ? `${fieldId}-description` : undefined;
  const controlLabels = accessibilityLabel
    ? { "aria-label": accessibilityLabel, "aria-labelledby": undefined, "aria-describedby": descriptionId }
    : { "aria-labelledby": labelId, "aria-describedby": descriptionId };
  return (
    <div className="field">
      <span id={labelId} className="field__label">{label}</span>
      {endAdornment ? <span className="field__control">{cloneElement(children, controlLabels)}{endAdornment}</span> : cloneElement(children, controlLabels)}
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

export function PageState({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <main className={`page-shell page-state${className ? ` ${className}` : ""}`}>{children}</main>;
}

export function TabList({ label, className = "", children }: { label: string; className?: string; children: ReactNode }) {
  function moveFocus(event: ReactKeyboardEvent<HTMLDivElement>) {
    if (!(event.target instanceof HTMLElement) || event.target.getAttribute("role") !== "tab") return;
    const tabs = Array.from(event.currentTarget.querySelectorAll<HTMLElement>('[role="tab"]:not([disabled])'));
    const current = tabs.indexOf(event.target);
    if (current < 0) return;
    let next = current;
    if (event.key === "ArrowRight" || event.key === "ArrowDown") next = (current + 1) % tabs.length;
    else if (event.key === "ArrowLeft" || event.key === "ArrowUp") next = (current - 1 + tabs.length) % tabs.length;
    else if (event.key === "Home") next = 0;
    else if (event.key === "End") next = tabs.length - 1;
    else return;
    event.preventDefault();
    tabs[next]?.focus();
    tabs[next]?.click();
  }

  return <div className={className} role="tablist" aria-label={label} onKeyDown={moveFocus}>{children}</div>;
}

export function DialogCloseButton({ label, className = "" }: { label: string; className?: string }) {
  return <Dialog.Close className={`dialog-close-button${className ? ` ${className}` : ""}`} aria-label={label}><X aria-hidden="true" /></Dialog.Close>;
}

export function SearchField({
  label,
  className = "",
  inputClassName = "",
  onClear,
  ...props
}: Omit<InputHTMLAttributes<HTMLInputElement>, "type"> & {
  label: string;
  inputClassName?: string;
  onClear?: () => void;
}) {
  const hasValue = typeof props.value === "string" && props.value.length > 0;
  return (
    <label className={`search-field${className ? ` ${className}` : ""}`}>
      <span className="visually-hidden">{label}</span>
      <Search className="search-field__icon" aria-hidden="true" />
      <input {...props} className={`input search-field__input${inputClassName ? ` ${inputClassName}` : ""}`} type="search" />
      {onClear && hasValue && !props.disabled ? (
        <button
          className="search-field__clear"
          type="button"
          aria-label={`Clear ${label.toLocaleLowerCase()}`}
          onClick={onClear}
        >
          <X aria-hidden="true" />
        </button>
      ) : null}
    </label>
  );
}

export function SectionHeading({
  eyebrow,
  title,
  description,
  meta,
  action,
  id,
  headingLevel = "h2",
  className = "",
}: {
  eyebrow?: string;
  title: string;
  description?: string;
  meta?: ReactNode;
  action?: ReactNode;
  id?: string;
  headingLevel?: "h2" | "h3";
  className?: string;
}) {
  const Heading = headingLevel;
  return (
    <div className={`section-heading${description ? " section-heading--with-description" : ""}${className ? ` ${className}` : ""}`}>
      <div>
        {eyebrow ? <p className="eyebrow">{eyebrow}</p> : null}
        <Heading id={id}>{title}</Heading>
        {description ? <p className="section-heading__description">{description}</p> : null}
      </div>
      {action ? <div className="section-heading__action">{action}</div> : meta ? <span className="data-value">{meta}</span> : null}
    </div>
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
export { RecipeMedia, type RecipeMediaSource } from "./cookfully/RecipeMedia";
export { Select };
