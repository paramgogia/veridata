"use client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  Boxes, Cpu, FlaskConical, Gauge, LayoutGrid, LogOut, Menu, Radar, ShieldCheck, Upload, User, Wallet, X, Zap,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import { WagmiProvider } from "wagmi";
import { eth, short } from "@/lib/format";
import { SessionProvider, useSession } from "@/lib/session";
import { wagmiConfig } from "@/lib/wagmi";
import { Badge, Button, cx, ErrorNote, Modal } from "./ui";

const qc = new QueryClient();

export function Providers({ children }: { children: React.ReactNode }) {
  return (
    <WagmiProvider config={wagmiConfig}>
      <QueryClientProvider client={qc}>
        <SessionProvider>{children}</SessionProvider>
      </QueryClientProvider>
    </WagmiProvider>
  );
}

const NAV = [
  { href: "/", label: "Demand Board", icon: Radar },
  { href: "/marketplace", label: "Marketplace", icon: LayoutGrid },
  { href: "/requests", label: "Requests", icon: Boxes },
  { href: "/upload", label: "Capture & Upload", icon: Upload },
  { href: "/devices", label: "Devices", icon: Cpu },
  { href: "/workspace", label: "Training Room", icon: FlaskConical },
  { href: "/dashboard", label: "Dashboard", icon: Gauge },
  { href: "/payments", label: "USDT Payments", icon: Zap },
  { href: "/demo/insurance", label: "Tamper demo", icon: ShieldCheck },
];

function NavLinks({ onNav }: { onNav?: () => void }) {
  const path = usePathname();
  return (
    <nav className="flex flex-col gap-0.5">
      {NAV.map(({ href, label, icon: Icon }) => {
        const active = href === "/" ? path === "/" : path.startsWith(href);
        return (
          <Link
            key={href}
            href={href}
            onClick={onNav}
            className={cx(
              "flex items-center gap-2.5 rounded-lg px-2.5 py-1.5 text-[13px] transition-colors",
              active ? "bg-raised text-fg" : "text-muted hover:bg-raised/60 hover:text-fg",
            )}
          >
            <Icon className="h-4 w-4" strokeWidth={1.8} />
            {label}
          </Link>
        );
      })}
    </nav>
  );
}

function Logo() {
  return (
    <Link href="/" className="flex items-center gap-2 px-1">
      <svg width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden>
        <rect x="1" y="1" width="22" height="22" rx="6" stroke="rgb(var(--accent))" strokeWidth="1.5" />
        <path d="M6.5 8l5.5 9 5.5-9" stroke="rgb(var(--fg))" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
        <circle cx="12" cy="7" r="1.4" fill="rgb(var(--ok))" />
      </svg>
      <span className="text-[15px] font-semibold tracking-tight">Veridata</span>
    </Link>
  );
}

function ChainPill() {
  const { chain } = useSession();
  if (!chain) return <Badge>API offline</Badge>;
  if (!chain.enabled) return <Badge tone="warn">Chain not configured · demo ledger</Badge>;
  return (
    <Badge tone={chain.reachable ? "chain" : "warn"} dot>
      Sepolia {chain.reachable ? "" : "(unreachable)"}
    </Badge>
  );
}

export function SignInModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { loginWallet, loginDemo } = useSession();
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const run = async (k: string, f: () => Promise<void>) => {
    setBusy(k);
    setErr(null);
    try {
      await f();
      onClose();
    } catch (e: any) {
      setErr(e?.shortMessage || e?.message || "sign-in failed");
    } finally {
      setBusy(null);
    }
  };
  return (
    <Modal open={open} onClose={onClose} title="Sign in to Veridata">
      <div className="space-y-4">
        <button
          onClick={() => run("wallet", loginWallet)}
          className="flex w-full items-center gap-3 rounded-xl border border-line bg-raised p-3.5 text-left hover:border-accent/50"
        >
          <Wallet className="h-5 w-5 text-accent" />
          <div className="flex-1">
            <div className="text-sm font-medium">Connect wallet</div>
            <div className="text-xs text-muted">Sign a one-time message (no gas). Required for on-chain Sepolia settlement.</div>
          </div>
          {busy === "wallet" && <span className="text-xs text-muted">waiting…</span>}
        </button>
        <div className="label">or explore with a demo persona</div>
        <div className="grid grid-cols-2 gap-2">
          {(["contributor", "buyer"] as const).map((p) => (
            <button
              key={p}
              onClick={() => run(p, () => loginDemo(p))}
              className="rounded-xl border border-line bg-panel p-3 text-left hover:border-faint/60"
            >
              <div className="text-sm font-medium">{p === "contributor" ? "Asha Farms" : "Northwind Robotics"}</div>
              <div className="text-xs text-muted">{p === "contributor" ? "Contributor · owns a simulated rig" : "Buyer / model builder"}</div>
            </button>
          ))}
        </div>
        <p className="text-[11px] leading-relaxed text-faint">
          Demo personas transact on an off-chain demo ledger with no real value. Every record shows whether it settled on-chain or on the demo ledger.
        </p>
        <ErrorNote>{err}</ErrorNote>
      </div>
    </Modal>
  );
}

function Account() {
  const { me, logout } = useSession();
  const [open, setOpen] = useState(false);
  if (!me)
    return (
      <>
        <Button variant="primary" size="sm" onClick={() => setOpen(true)}>
          Sign in
        </Button>
        <SignInModal open={open} onClose={() => setOpen(false)} />
      </>
    );
  return (
    <div className="flex items-center gap-2">
      <Link href="/profile" className="flex items-center gap-2 rounded-lg border border-line bg-panel px-2 py-1 hover:border-faint/60">
        <span className="grid h-5 w-5 place-items-center rounded-md bg-accent/15 text-[10px] font-semibold text-accent">{me.name.slice(0, 1)}</span>
        <span className="hidden text-xs sm:inline">{me.name.length > 22 ? short(me.address, 4) : me.name}</span>
        {me.demo && <Badge tone="warn">demo · {eth(me.balances.demo_balance, 2)}</Badge>}
      </Link>
      <button onClick={logout} className="text-faint hover:text-fg" title="Sign out">
        <LogOut className="h-4 w-4" />
      </button>
    </div>
  );
}

export function Shell({ children }: { children: React.ReactNode }) {
  const [mobile, setMobile] = useState(false);
  return (
    <div className="min-h-screen">
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-56 flex-col border-r border-line bg-bg px-3 py-4 lg:flex">
        <Logo />
        <div className="mt-6 flex-1">
          <NavLinks />
        </div>
        <Link href="/profile" className="flex items-center gap-2 rounded-lg px-2.5 py-1.5 text-[13px] text-muted hover:bg-raised/60 hover:text-fg">
          <User className="h-4 w-4" /> Profile
        </Link>
        <div className="mt-3 px-2.5 text-[10px] leading-relaxed text-faint">Capture → Verify → Monetize → Train → Export</div>
      </aside>
      {mobile && (
        <div className="fixed inset-0 z-40 bg-black/60 lg:hidden" onClick={() => setMobile(false)}>
          <div className="h-full w-64 border-r border-line bg-bg p-4" onClick={(e) => e.stopPropagation()}>
            <div className="mb-6 flex items-center justify-between">
              <Logo />
              <button onClick={() => setMobile(false)}>
                <X className="h-4 w-4" />
              </button>
            </div>
            <NavLinks onNav={() => setMobile(false)} />
          </div>
        </div>
      )}
      <div className="lg:pl-56">
        <header className="sticky top-0 z-20 flex h-12 items-center justify-between gap-3 border-b border-line bg-bg/85 px-4 backdrop-blur md:px-6">
          <div className="flex items-center gap-3">
            <button className="lg:hidden" onClick={() => setMobile(true)}>
              <Menu className="h-4 w-4" />
            </button>
            <ChainPill />
          </div>
          <Account />
        </header>
        <main className="mx-auto max-w-[1280px] px-4 py-6 md:px-6 md:py-8">{children}</main>
      </div>
    </div>
  );
}

export function RequireAuth({ children, what = "this page" }: { children: React.ReactNode; what?: string }) {
  const { me, loading } = useSession();
  const [open, setOpen] = useState(false);
  if (loading) return null;
  if (!me)
    return (
      <div className="mx-auto mt-16 max-w-md text-center">
        <div className="text-lg font-semibold">Sign in to use {what}</div>
        <p className="mt-1 text-sm text-muted">Connect a wallet or pick a demo persona.</p>
        <Button variant="primary" className="mt-5" onClick={() => setOpen(true)}>
          Sign in
        </Button>
        <SignInModal open={open} onClose={() => setOpen(false)} />
      </div>
    );
  return <>{children}</>;
}
