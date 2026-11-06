"use client";
import clsx from "clsx";
import { AlertTriangle, CheckCircle2, Circle, Loader2, XCircle } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { api } from "@/lib/api";

export const cx = clsx;

// ---------- data hook ----------
export function useApi<T = any>(path: string | null, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(!!path);
  const alive = useRef(true);
  const load = useCallback(async () => {
    if (!path) return;
    setLoading(true);
    try {
      const d = await api<T>(path);
      if (alive.current) {
        setData(d);
        setError(null);
      }
    } catch (e: any) {
      if (alive.current) setError(e.message || "failed to load");
    } finally {
      if (alive.current) setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path, ...deps]);
  useEffect(() => {
    alive.current = true;
    load();
    return () => {
      alive.current = false;
    };
  }, [load]);
  return { data, error, loading, reload: load, setData };
}

// ---------- primitives ----------
type BtnProps = React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "ghost" | "danger" | "chain";
  size?: "sm" | "md";
  loading?: boolean;
  href?: string;
};
export function Button({ variant = "secondary", size = "md", loading, className, children, href, disabled, ...rest }: BtnProps) {
  const cls = cx(
    "inline-flex items-center justify-center gap-1.5 rounded-lg font-medium transition-colors disabled:opacity-50 disabled:pointer-events-none whitespace-nowrap select-none",
    size === "sm" ? "h-7 px-2.5 text-xs" : "h-9 px-3.5 text-sm",
    variant === "primary" && "bg-fg text-bg hover:bg-fg/90",
    variant === "secondary" && "border border-line bg-raised text-fg hover:border-faint/60 hover:bg-line/40",
    variant === "ghost" && "text-muted hover:text-fg hover:bg-raised",
    variant === "danger" && "border border-bad/30 bg-bad/10 text-bad hover:bg-bad/15",
    variant === "chain" && "border border-chain/30 bg-chain/10 text-chain hover:bg-chain/15",
    className,
  );
  const inner = (
    <>
      {loading && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
      {children}
    </>
  );
  if (href) return <Link href={href} className={cls}>{inner}</Link>;
  return (
    <button className={cls} disabled={disabled || loading} {...rest}>
      {inner}
    </button>
  );
}

export function Card({ className, children, ...rest }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div className={cx("card", className)} {...rest}>
      {children}
    </div>
  );
}

export function CardHeader({ title, sub, right, icon }: { title: React.ReactNode; sub?: React.ReactNode; right?: React.ReactNode; icon?: React.ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-3 border-b border-line px-5 py-3.5">
      <div className="flex min-w-0 items-center gap-2.5">
        {icon && <span className="text-muted">{icon}</span>}
        <div className="min-w-0">
          <div className="text-sm font-semibold">{title}</div>
          {sub && <div className="mt-0.5 text-xs text-muted">{sub}</div>}
        </div>
      </div>
      {right}
    </div>
  );
}

type Tone = "neutral" | "ok" | "warn" | "bad" | "accent" | "chain";
export function Badge({ tone = "neutral", children, className, dot }: { tone?: Tone; children: React.ReactNode; className?: string; dot?: boolean }) {
  return (
    <span
      className={cx(
        "inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5 text-[11px] font-medium leading-4 whitespace-nowrap",
        tone === "neutral" && "border-line bg-raised text-muted",
        tone === "ok" && "border-ok/25 bg-ok/10 text-ok",
        tone === "warn" && "border-warn/25 bg-warn/10 text-warn",
        tone === "bad" && "border-bad/25 bg-bad/10 text-bad",
        tone === "accent" && "border-accent/25 bg-accent/10 text-accent",
        tone === "chain" && "border-chain/25 bg-chain/10 text-chain",
        className,
      )}
    >
      {dot && <span className="h-1.5 w-1.5 rounded-full bg-current" />}
      {children}
    </span>
  );
}

/** Distinguishes real on-chain settlement from demo data. */
export function ModeBadge({ mode }: { mode: string }) {
  if (mode === "onchain") return <Badge tone="chain" dot>On-chain · Sepolia</Badge>;
  if (mode === "demo-seed") return <Badge tone="warn">Demo data</Badge>;
  return <Badge>Demo ledger</Badge>;
}

export function Stat({ label, value, sub, icon }: { label: string; value: React.ReactNode; sub?: React.ReactNode; icon?: React.ReactNode }) {
  return (
    <div className="card px-4 py-3.5">
      <div className="flex items-center justify-between">
        <span className="label">{label}</span>
        <span className="text-faint">{icon}</span>
      </div>
      <div className="mt-1.5 text-xl font-semibold tabular-nums tracking-tight">{value}</div>
      {sub && <div className="mt-0.5 text-xs text-muted">{sub}</div>}
    </div>
  );
}

export function Progress({ value, className, tone = "accent" }: { value: number; className?: string; tone?: "accent" | "ok" }) {
  return (
    <div className={cx("h-1.5 w-full overflow-hidden rounded-full bg-line", className)}>
      <div className={cx("h-full rounded-full transition-all duration-500", tone === "ok" ? "bg-ok" : "bg-accent")} style={{ width: `${Math.min(100, Math.max(0, value * 100))}%` }} />
    </div>
  );
}

export function Spinner({ label }: { label?: string }) {
  return (
    <div className="flex items-center gap-2 text-sm text-muted">
      <Loader2 className="h-4 w-4 animate-spin" /> {label}
    </div>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={cx("animate-pulse rounded-lg bg-raised", className)} />;
}

export function Empty({ icon, title, sub, action }: { icon?: React.ReactNode; title: string; sub?: string; action?: React.ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 rounded-2xl border border-dashed border-line px-6 py-12 text-center">
      {icon && <div className="text-faint">{icon}</div>}
      <div className="text-sm font-medium">{title}</div>
      {sub && <div className="max-w-sm text-xs text-muted">{sub}</div>}
      {action && <div className="mt-2">{action}</div>}
    </div>
  );
}

export function ErrorNote({ children }: { children: React.ReactNode }) {
  if (!children) return null;
  return (
    <div className="flex items-start gap-2 rounded-lg border border-bad/25 bg-bad/5 px-3 py-2 text-xs text-bad">
      <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
      <span className="break-words">{children}</span>
    </div>
  );
}

export function Note({ children, tone = "neutral" }: { children: React.ReactNode; tone?: "neutral" | "warn" | "chain" }) {
  return (
    <div
      className={cx(
        "rounded-lg border px-3 py-2 text-xs leading-relaxed",
        tone === "neutral" && "border-line bg-raised/60 text-muted",
        tone === "warn" && "border-warn/25 bg-warn/5 text-warn/90",
        tone === "chain" && "border-chain/25 bg-chain/5 text-chain/90",
      )}
    >
      {children}
    </div>
  );
}

export function CheckRow({ ok, name, detail }: { ok: boolean | null; name: string; detail?: string }) {
  return (
    <div className="flex items-start gap-2.5 py-1.5">
      {ok === true && <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-ok" />}
      {ok === false && <XCircle className="mt-0.5 h-4 w-4 shrink-0 text-bad" />}
      {ok === null && <Circle className="mt-0.5 h-4 w-4 shrink-0 text-faint" />}
      <div className="min-w-0">
        <div className="text-[13px] font-medium capitalize">{name.replace(/_/g, " ")}</div>
        {detail && <div className="break-all font-mono text-[11px] leading-relaxed text-muted">{detail}</div>}
      </div>
    </div>
  );
}

export function Tabs<T extends string>({ value, onChange, items }: { value: T; onChange: (v: T) => void; items: { id: T; label: React.ReactNode }[] }) {
  return (
    <div className="inline-flex rounded-lg border border-line bg-panel p-0.5">
      {items.map((it) => (
        <button
          key={it.id}
          onClick={() => onChange(it.id)}
          className={cx("rounded-md px-3 py-1 text-xs font-medium transition-colors", value === it.id ? "bg-raised text-fg shadow-sm" : "text-muted hover:text-fg")}
        >
          {it.label}
        </button>
      ))}
    </div>
  );
}

export function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <div className="mb-1.5 flex items-baseline justify-between">
        <span className="text-xs font-medium text-muted">{label}</span>
        {hint && <span className="text-[11px] text-faint">{hint}</span>}
      </div>
      {children}
    </label>
  );
}

export function PageHeader({ title, sub, right, eyebrow }: { title: React.ReactNode; sub?: React.ReactNode; right?: React.ReactNode; eyebrow?: React.ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div className="min-w-0">
        {eyebrow && <div className="label mb-2">{eyebrow}</div>}
        <h1 className="text-[22px] font-semibold tracking-tight">{title}</h1>
        {sub && <p className="mt-1 max-w-2xl text-sm text-muted">{sub}</p>}
      </div>
      {right && <div className="flex items-center gap-2">{right}</div>}
    </div>
  );
}

export function Chips({ options, value, onChange }: { options: string[]; value: string[]; onChange: (v: string[]) => void }) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {options.map((o) => {
        const on = value.includes(o);
        return (
          <button
            type="button"
            key={o}
            onClick={() => onChange(on ? value.filter((x) => x !== o) : [...value, o])}
            className={cx(
              "rounded-md border px-2 py-0.5 text-xs transition-colors",
              on ? "border-accent/40 bg-accent/10 text-accent" : "border-line text-muted hover:border-faint/60 hover:text-fg",
            )}
          >
            {o}
          </button>
        );
      })}
    </div>
  );
}

export function KV({ k, v, mono }: { k: string; v: React.ReactNode; mono?: boolean }) {
  return (
    <div className="flex items-start justify-between gap-4 py-1.5 text-[13px]">
      <span className="shrink-0 text-muted">{k}</span>
      <span className={cx("min-w-0 break-all text-right", mono && "font-mono text-[12px]")}>{v}</span>
    </div>
  );
}

export function Modal({ open, onClose, title, children, wide }: { open: boolean; onClose: () => void; title: string; children: React.ReactNode; wide?: boolean }) {
  useEffect(() => {
    const h = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [onClose]);
  if (!open) return null;
  // Portaled to <body>: the modal is often mounted inside the sticky header, whose
  // backdrop-filter turns it into the containing block for `fixed` descendants.
  return createPortal(
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/60 p-4 pt-[8vh] backdrop-blur-[2px]" onMouseDown={onClose}>
      <div className={cx("card w-full animate-in shadow-2xl", wide ? "max-w-3xl" : "max-w-lg")} onMouseDown={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between border-b border-line px-5 py-3.5">
          <div className="text-sm font-semibold">{title}</div>
          <button onClick={onClose} className="text-muted hover:text-fg">
            ✕
          </button>
        </div>
        <div className="p-5">{children}</div>
      </div>
    </div>,
    document.body,
  );
}
