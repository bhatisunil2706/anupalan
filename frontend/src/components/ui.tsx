"use client";

import { X } from "lucide-react";
import Link from "next/link";
import {
  createContext,
  forwardRef,
  useCallback,
  useContext,
  useEffect,
  useId,
  useRef,
  useState,
  type ButtonHTMLAttributes,
  type InputHTMLAttributes,
  type ReactNode,
  type SelectHTMLAttributes,
  type TextareaHTMLAttributes,
} from "react";

import type { Health } from "@/lib/types";

const cx = (...c: (string | false | null | undefined)[]) => c.filter(Boolean).join(" ");
export { cx };

// ------------------------------------------------------------------ buttons

type Variant = "primary" | "secondary" | "danger" | "ghost";
const VARIANTS: Record<Variant, string> = {
  primary: "bg-ink text-white hover:bg-ink-700 disabled:bg-ink/50",
  secondary: "bg-surface text-text border border-line hover:border-ink/40 disabled:text-muted",
  danger: "bg-surface text-fail border border-fail/30 hover:bg-fail-50",
  ghost: "text-muted hover:text-text hover:bg-ink-50",
};

export const Button = forwardRef<
  HTMLButtonElement,
  ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; size?: "sm" | "md"; busy?: boolean }
>(function Button({ variant = "primary", size = "md", busy, className, children, disabled, ...rest }, ref) {
  return (
    <button
      ref={ref}
      disabled={disabled || busy}
      className={cx(
        "inline-flex items-center justify-center gap-1.5 whitespace-nowrap rounded-md font-medium transition-colors disabled:cursor-not-allowed",
        size === "sm" ? "h-8 px-3 text-[13px]" : "h-9 px-4 text-sm",
        VARIANTS[variant],
        className,
      )}
      {...rest}
    >
      {busy ? "Working…" : children}
    </button>
  );
});

export function ButtonLink({ href, children, variant = "secondary" }: { href: string; children: ReactNode; variant?: Variant }) {
  return (
    <Link
      href={href}
      className={cx("inline-flex h-9 items-center gap-1.5 rounded-md px-4 text-sm font-medium transition-colors", VARIANTS[variant])}
    >
      {children}
    </Link>
  );
}

// ------------------------------------------------------------------ form fields

/** Fields fill their container unless the caller sets an explicit width. */
const widthFor = (className?: string) => (className && /(^|\s)w-/.test(className) ? "" : "w-full");

const inputBase =
  "rounded-md border border-line bg-surface px-3 text-sm text-text placeholder:text-muted/70 focus:border-ink focus:outline-none focus:ring-2 focus:ring-ink/15 disabled:bg-paper";

export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(function Input(
  { className, ...rest },
  ref,
) {
  return <input ref={ref} className={cx(inputBase, widthFor(className), "h-9", className)} {...rest} />;
});

export function Textarea({ className, ...rest }: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea className={cx(inputBase, widthFor(className), "min-h-[88px] py-2 leading-relaxed", className)} {...rest} />;
}

export function Select({ className, children, ...rest }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select className={cx(inputBase, widthFor(className), "h-9 pr-8", className)} {...rest}>
      {children}
    </select>
  );
}

export function Field({
  label,
  hint,
  children,
  className,
}: {
  label: string;
  hint?: ReactNode;
  children: (id: string) => ReactNode;
  className?: string;
}) {
  const id = useId();
  return (
    <div className={cx("space-y-1.5", className)}>
      <label htmlFor={id} className="block text-[13px] font-medium text-text">
        {label}
      </label>
      {children(id)}
      {hint && <p className="text-xs text-muted">{hint}</p>}
    </div>
  );
}

export function Checkbox({
  label,
  checked,
  onChange,
  hint,
}: {
  label: string;
  checked: boolean;
  onChange: (v: boolean) => void;
  hint?: string;
}) {
  const id = useId();
  return (
    <div className="flex items-start gap-2.5">
      <input
        id={id}
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        className="mt-0.5 h-4 w-4 rounded border-line accent-ink"
      />
      <label htmlFor={id} className="text-sm leading-snug">
        {label}
        {hint && <span className="mt-0.5 block text-xs text-muted">{hint}</span>}
      </label>
    </div>
  );
}

export function FormError({ error }: { error: string | null }) {
  if (!error) return null;
  return (
    <p role="alert" className="rounded-md border border-fail/25 bg-fail-50 px-3 py-2 text-sm text-fail">
      {error}
    </p>
  );
}

// ------------------------------------------------------------------ status

type Tone = "pass" | "fail" | "warn" | "prog" | "idle" | "ink";
const TONES: Record<Tone, string> = {
  pass: "bg-pass-50 text-pass",
  fail: "bg-fail-50 text-fail",
  warn: "bg-warn-50 text-warn",
  prog: "bg-prog-50 text-prog",
  idle: "bg-idle-50 text-idle",
  ink: "bg-ink-50 text-ink",
};

export function Badge({ tone = "idle", children, className }: { tone?: Tone; children: ReactNode; className?: string }) {
  return (
    <span className={cx("inline-flex items-center gap-1 whitespace-nowrap rounded px-1.5 py-0.5 text-xs font-medium", TONES[tone], className)}>
      {children}
    </span>
  );
}

export const HEALTH: Record<Health, { label: string; tone: Tone }> = {
  passing: { label: "Passing", tone: "pass" },
  failing: { label: "Failing check", tone: "fail" },
  needs_evidence: { label: "Needs evidence", tone: "warn" },
  in_progress: { label: "In progress", tone: "prog" },
  not_started: { label: "Not started", tone: "idle" },
  not_applicable: { label: "Not applicable", tone: "idle" },
};

export function HealthBadge({ health }: { health: Health }) {
  const h = HEALTH[health];
  return (
    <Badge tone={h.tone}>
      <span className="h-1.5 w-1.5 rounded-full bg-current" aria-hidden />
      {h.label}
    </Badge>
  );
}

// ------------------------------------------------------------------ layout

export function PageHeader({ title, description, actions }: { title: string; description?: ReactNode; actions?: ReactNode }) {
  return (
    <header className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div className="min-w-0">
        <h1 className="text-[22px] font-bold tracking-[-0.01em] text-text">{title}</h1>
        {description && <p className="mt-1 max-w-[70ch] text-sm text-muted">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </header>
  );
}

export function Panel({
  title,
  actions,
  children,
  className,
  flush,
}: {
  title?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  flush?: boolean;
}) {
  return (
    <section className={cx("rounded-lg border border-line bg-surface", className)}>
      {title && (
        <div className="flex items-center justify-between gap-3 border-b border-line px-4 py-3">
          <h2 className="text-sm font-semibold">{title}</h2>
          {actions}
        </div>
      )}
      <div className={flush ? "" : "p-4"}>{children}</div>
    </section>
  );
}

export function Empty({ title, children, action }: { title: string; children?: ReactNode; action?: ReactNode }) {
  return (
    <div className="px-6 py-12 text-center">
      <p className="font-semibold">{title}</p>
      {children && <p className="mx-auto mt-1 max-w-md text-sm text-muted">{children}</p>}
      {action && <div className="mt-4 flex justify-center">{action}</div>}
    </div>
  );
}

export function Loading({ label = "Loading" }: { label?: string }) {
  return (
    <div className="flex items-center gap-2 px-4 py-10 text-sm text-muted" role="status">
      <span className="h-4 w-4 animate-spin rounded-full border-2 border-line border-t-ink" aria-hidden />
      {label}…
    </div>
  );
}

export function LoadError({ error, retry }: { error: string; retry?: () => void }) {
  return (
    <div className="rounded-lg border border-fail/25 bg-fail-50 px-4 py-3 text-sm text-fail">
      {error}
      {retry && (
        <button onClick={retry} className="ml-3 font-medium underline">
          Try again
        </button>
      )}
    </div>
  );
}

/** Table styles kept as class strings so tables stay plain semantic HTML. */
export const tbl = {
  wrap: "overflow-x-auto",
  table: "w-full border-collapse text-sm",
  th: "border-b border-line bg-paper/60 px-4 py-2.5 text-left text-xs font-semibold text-muted",
  td: "border-b border-line px-4 py-3 align-top",
  row: "hover:bg-ink-50/40",
};

export function Tabs<T extends string>({
  tabs,
  value,
  onChange,
}: {
  tabs: { value: T; label: ReactNode }[];
  value: T;
  onChange: (v: T) => void;
}) {
  return (
    <div role="tablist" className="mb-4 flex gap-1 border-b border-line">
      {tabs.map((t) => (
        <button
          key={t.value}
          role="tab"
          aria-selected={value === t.value}
          onClick={() => onChange(t.value)}
          className={cx(
            "-mb-px border-b-2 px-3 py-2 text-sm font-medium",
            value === t.value ? "border-ink text-ink" : "border-transparent text-muted hover:text-text",
          )}
        >
          {t.label}
        </button>
      ))}
    </div>
  );
}

// ------------------------------------------------------------------ drawer

export function Drawer({
  open,
  onClose,
  title,
  children,
  footer,
  wide,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
  footer?: ReactNode;
  wide?: boolean;
}) {
  const panel = useRef<HTMLDivElement>(null);
  // Keep the latest onClose without re-running the focus effect: callers often pass a new function on every
  // render, which would otherwise move focus back to the first field while someone is typing.
  const closeRef = useRef(onClose);
  useEffect(() => {
    closeRef.current = onClose;
  }, [onClose]);
  useEffect(() => {
    if (!open) return;
    const prev = document.activeElement as HTMLElement | null;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && closeRef.current();
    document.addEventListener("keydown", onKey);
    panel.current?.querySelector<HTMLElement>("input, textarea, select, button")?.focus();
    return () => {
      document.removeEventListener("keydown", onKey);
      prev?.focus();
    };
  }, [open]);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <div className="absolute inset-0 bg-text/30" onClick={onClose} aria-hidden />
      <div
        ref={panel}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className={cx("relative flex h-full w-full flex-col bg-surface shadow-xl", wide ? "max-w-2xl" : "max-w-lg")}
      >
        <div className="flex items-center justify-between border-b border-line px-5 py-4">
          <h2 className="text-base font-semibold">{title}</h2>
          <button onClick={onClose} className="rounded p-1 text-muted hover:bg-ink-50 hover:text-text" aria-label="Close">
            <X size={18} />
          </button>
        </div>
        <div className="flex-1 space-y-4 overflow-y-auto px-5 py-5">{children}</div>
        {footer && <div className="flex justify-end gap-2 border-t border-line px-5 py-3">{footer}</div>}
      </div>
    </div>
  );
}

// ------------------------------------------------------------------ toast

const ToastCtx = createContext<(msg: string, tone?: "ok" | "error") => void>(() => {});

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toast, setToast] = useState<{ msg: string; tone: "ok" | "error"; id: number } | null>(null);
  const show = useCallback((msg: string, tone: "ok" | "error" = "ok") => {
    const id = Date.now();
    setToast({ msg, tone, id });
    setTimeout(() => setToast((t) => (t?.id === id ? null : t)), 3500);
  }, []);
  return (
    <ToastCtx.Provider value={show}>
      {children}
      <div aria-live="polite" className="pointer-events-none fixed bottom-5 left-1/2 z-[60] -translate-x-1/2">
        {toast && (
          <div
            className={cx(
              "rounded-md px-4 py-2.5 text-sm font-medium text-white shadow-lg",
              toast.tone === "ok" ? "bg-text" : "bg-fail",
            )}
          >
            {toast.msg}
          </div>
        )}
      </div>
    </ToastCtx.Provider>
  );
}

export const useToast = () => useContext(ToastCtx);
