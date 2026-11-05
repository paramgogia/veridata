"use client";
import { CalendarClock, Cpu, ExternalLink, Fingerprint, Lock, ShieldCheck, Sparkles } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { api, url } from "@/lib/api";
import { date, day, eth, num, short } from "@/lib/format";
import { useSession } from "@/lib/session";
import { Badge, Button, Card, CardHeader, CheckRow, cx, ErrorNote, KV, ModeBadge, Note, Progress } from "./ui";

export type Req = any;
export type DS = any;

export function DemandCard({ r, featured }: { r: Req; featured?: boolean }) {
  return (
    <Link href={`/requests/${r.id}`} className="group block animate-in">
      <Card className={cx("h-full p-4 transition-colors group-hover:border-faint/60", featured && "border-accent/25")}>
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="mb-1.5 flex flex-wrap items-center gap-1.5">
              <Badge tone="accent">{r.category}</Badge>
              <ModeBadge mode={r.mode} />
              {r.spec?.require_device_signature && (
                <Badge tone="ok">
                  <Fingerprint className="h-3 w-3" /> signed only
                </Badge>
              )}
            </div>
            <div className="text-[15px] font-semibold leading-snug">{r.title}</div>
            <div className="mt-0.5 text-xs text-muted">by {r.buyer?.name}</div>
          </div>
          <div className="text-right">
            <div className="text-[15px] font-semibold tabular-nums">{eth(r.price_per_sample)}</div>
            <div className="text-[11px] text-muted">per accepted sample</div>
          </div>
        </div>
        <div className="mt-4">
          <div className="mb-1.5 flex justify-between text-xs">
            <span className="text-muted">
              <span className="font-medium text-fg tabular-nums">{num(r.accepted)}</span> / {num(r.quantity)} fulfilled
            </span>
            <span className="text-muted tabular-nums">{num(r.remaining)} left</span>
          </div>
          <Progress value={r.progress} tone={r.progress >= 1 ? "ok" : "accent"} />
        </div>
        <div className="mt-4 grid grid-cols-3 gap-2 border-t border-line pt-3 text-xs">
          <div>
            <div className="text-faint">Reward pool</div>
            <div className="mt-0.5 font-medium tabular-nums">{eth(r.reward_pool)}</div>
          </div>
          <div>
            <div className="text-faint">Remaining escrow</div>
            <div className="mt-0.5 font-medium tabular-nums">{eth(r.remaining_escrow)}</div>
          </div>
          <div className="text-right">
            <div className="text-faint">Deadline</div>
            <div className={cx("mt-0.5 font-medium", r.days_left < 5 && "text-warn")}>{r.days_left} days</div>
          </div>
        </div>
      </Card>
    </Link>
  );
}

export function DatasetCard({ d }: { d: DS }) {
  return (
    <Link href={`/marketplace/${d.id}`} className="group block animate-in">
      <Card className="h-full overflow-hidden transition-colors group-hover:border-faint/60">
        <div className="relative aspect-[16/9] bg-raised">
          {d.cover_url && <img src={url(d.cover_url)} alt="" className="h-full w-full object-cover opacity-90" />}
          <div className="absolute left-2 top-2 flex gap-1">
            <ModeBadge mode={d.mode} />
          </div>
          <div className="absolute bottom-2 right-2 rounded-md bg-bg/80 px-1.5 py-0.5 text-[11px] tabular-nums text-fg backdrop-blur">
            Q {d.quality_score}
          </div>
        </div>
        <div className="p-3.5">
          <div className="line-clamp-2 text-sm font-semibold leading-snug">{d.title}</div>
          <div className="mt-1 text-xs text-muted">
            {d.owner?.name} · {num(d.sample_count)} samples
          </div>
          <div className="mt-2.5 flex flex-wrap gap-1">
            {d.categories.slice(0, 3).map((c: string) => (
              <Badge key={c}>{c}</Badge>
            ))}
          </div>
          <div className="mt-3 flex items-center justify-between border-t border-line pt-2.5">
            <span className="flex items-center gap-1 text-[11px] text-ok">
              <ShieldCheck className="h-3.5 w-3.5" /> signed manifests
            </span>
            <span className="text-sm font-semibold tabular-nums">{eth(d.price)}</span>
          </div>
        </div>
      </Card>
    </Link>
  );
}

export function TxLink({ hash, urlStr, mode }: { hash?: string; urlStr?: string; mode?: string }) {
  if (!hash) return <span className="text-faint">{mode === "onchain" ? "—" : "demo ledger (off-chain)"}</span>;
  return (
    <a href={urlStr} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 font-mono text-[12px] text-chain hover:underline">
      {short(hash, 8)} <ExternalLink className="h-3 w-3" />
    </a>
  );
}

export function ProofCard({ d }: { d: DS }) {
  const [res, setRes] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const dev = d.devices?.[0];
  const verify = async () => {
    setBusy(true);
    setErr(null);
    try {
      setRes(await api(`/api/datasets/${d.id}/verify`, { method: "POST" }));
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Card className="overflow-hidden">
      <CardHeader
        icon={<ShieldCheck className="h-4 w-4" />}
        title="Proof Card"
        sub="Cryptographic provenance for every sample in this dataset"
        right={
          <Button variant="primary" size="sm" onClick={verify} loading={busy}>
            Verify now
          </Button>
        }
      />
      <div className="divide-y divide-line px-5">
        <div className="py-2">
          <KV k="Capture device" v={dev ? <Link className="link" href={`/devices/${dev.id}`}>{dev.id}</Link> : "—"} />
          <KV
            k="Device registration"
            v={dev ? (dev.registration_mode === "onchain" ? <TxLink hash={dev.registration_tx} urlStr={dev.registration_tx_url} /> : <Badge>registry (off-chain)</Badge>) : "—"}
          />
          <KV k="Signing key" v={dev ? <span className="font-mono text-xs">P-256 · {dev.key_fp}</span> : "—"} />
          <KV
            k="Signature mode"
            v={(d.sig_modes || []).map((m: string) => (
              <Badge key={m} tone={m === "device-hardware" ? "ok" : "warn"} className="ml-1">
                {m}
              </Badge>
            ))}
          />
          <KV k="Signed samples" v={`${d.signed_count ?? "—"} / ${d.sample_count}`} />
          <KV k="Captured" v={`${day(d.capture_start)} → ${day(d.capture_end)}`} />
        </div>
        <div className="py-2">
          <KV k="Content root (Merkle)" v={<span className="hash">{short("0x" + d.content_root, 10)}</span>} />
          <KV k="Storage" v={<span className="flex items-center justify-end gap-1 text-xs"><Lock className="h-3 w-3" /> AES-256-GCM encrypted, content-addressed</span>} />
          <KV k="Ownership / listing" v={d.mode === "onchain" ? <TxLink hash={d.publish_tx} urlStr={d.publish_tx_url} /> : <ModeBadge mode={d.mode} />} />
          {d.chain_dataset_id && <KV k="On-chain dataset id" v={`#${d.chain_dataset_id}`} />}
          <KV k="Manifest bundle" v={<a className="link text-xs" href={url(`/api/datasets/${d.id}/manifests`)} target="_blank" rel="noreferrer">public JSON</a>} />
        </div>
        {res && (
          <div className="animate-in py-3">
            <div className="mb-1 flex items-center justify-between">
              <span className="label">Verification result</span>
              <Badge tone={res.valid ? "ok" : "bad"}>{res.valid ? "verified" : "failed"}</Badge>
            </div>
            {res.steps.map((s: any) => (
              <CheckRow key={s.name} ok={s.ok} name={s.name} detail={s.detail} />
            ))}
            <div className="mt-1 text-[11px] text-faint">checked {date(res.checked_at)} · recomputed server-side from encrypted storage</div>
          </div>
        )}
        <div className="py-3">
          <ErrorNote>{err}</ErrorNote>
          <Note>
            Verification proves the media is unchanged since capture and was signed by the registered device key. It does not prove the depicted event is genuine.
            {(d.sig_modes || []).includes("dev-software") && " Samples signed in dev-software mode use a platform-held key, not a hardware-protected one."}
          </Note>
        </div>
      </div>
    </Card>
  );
}

export function SampleVerify({ sampleId }: { sampleId: string }) {
  const [res, setRes] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  return (
    <div>
      <Button size="sm" onClick={async () => { setBusy(true); try { setRes(await api(`/api/samples/${sampleId}/verify`, { method: "POST" })); } finally { setBusy(false); } }} loading={busy}>
        <Fingerprint className="h-3.5 w-3.5" /> Verify sample
      </Button>
      {res && (
        <div className="mt-2 animate-in">
          <Badge tone={res.valid ? "ok" : "bad"}>{res.valid ? "integrity + signature valid" : "verification failed"}</Badge>
          <div className="mt-1">
            {res.steps.map((s: any) => <CheckRow key={s.name} ok={s.ok} name={s.name} detail={s.detail} />)}
          </div>
        </div>
      )}
    </div>
  );
}

/** Lets the user choose settlement: real on-chain (wallet) or demo ledger. */
export function useSettlement() {
  const { canOnchain, chain, me } = useSession();
  const [mode, setMode] = useState<"onchain" | "local" | null>(null);
  const effective = mode ?? (canOnchain ? "onchain" : "local");
  const picker = (
    <div className="flex flex-wrap items-center gap-2 text-xs">
      <span className="text-muted">Settle via</span>
      <button
        type="button"
        disabled={!canOnchain}
        onClick={() => setMode("onchain")}
        className={cx("rounded-md border px-2 py-1 disabled:opacity-40", effective === "onchain" ? "border-chain/40 bg-chain/10 text-chain" : "border-line text-muted")}
        title={canOnchain ? "" : !chain?.enabled ? "Contract not configured" : me?.demo ? "Demo personas cannot sign transactions" : "Connect the wallet you signed in with"}
      >
        Sepolia (wallet)
      </button>
      <button
        type="button"
        onClick={() => setMode("local")}
        className={cx("rounded-md border px-2 py-1", effective === "local" ? "border-faint/60 bg-raised text-fg" : "border-line text-muted")}
      >
        Demo ledger
      </button>
    </div>
  );
  return { mode: effective, picker, contract: chain?.contract || "" };
}

export function Sparkline({ values, h = 36, w = 120, tone = "accent" }: { values: number[]; h?: number; w?: number; tone?: string }) {
  if (values.length < 2) return null;
  const max = Math.max(...values), min = Math.min(...values);
  const pts = values.map((v, i) => `${(i / (values.length - 1)) * w},${h - ((v - min) / (max - min || 1)) * (h - 4) - 2}`).join(" ");
  return (
    <svg width={w} height={h}>
      <polyline points={pts} fill="none" stroke={`rgb(var(--${tone}))`} strokeWidth="1.5" />
    </svg>
  );
}

export function LineChart({ series, height = 180, yMax, yFmt = (v: number) => v.toFixed(2) }: { series: { name: string; tone: string; values: number[]; dashed?: boolean }[]; height?: number; yMax?: number; yFmt?: (v: number) => string }) {
  const n = Math.max(...series.map((s) => s.values.length), 0);
  if (n < 1) return <div className="grid h-[180px] place-items-center text-xs text-faint">waiting for first epoch…</div>;
  const all = series.flatMap((s) => s.values);
  const max = yMax ?? Math.max(...all, 0.0001) * 1.05;
  const W = 560, H = height, P = { l: 36, r: 8, t: 8, b: 20 };
  const x = (i: number) => P.l + (n === 1 ? 0 : (i / (n - 1)) * (W - P.l - P.r));
  const y = (v: number) => P.t + (1 - v / max) * (H - P.t - P.b);
  return (
    <div>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" preserveAspectRatio="none" style={{ height }}>
        {[0, 0.25, 0.5, 0.75, 1].map((t) => (
          <g key={t}>
            <line x1={P.l} x2={W - P.r} y1={y(max * t)} y2={y(max * t)} stroke="rgb(var(--line))" strokeWidth="1" />
            <text x={P.l - 6} y={y(max * t) + 3} textAnchor="end" fontSize="10" fill="rgb(var(--faint))">{yFmt(max * t)}</text>
          </g>
        ))}
        {series.map((s) => (
          <polyline key={s.name} fill="none" stroke={`rgb(var(--${s.tone}))`} strokeWidth="1.8" strokeDasharray={s.dashed ? "4 3" : undefined}
            points={s.values.map((v, i) => `${x(i)},${y(v)}`).join(" ")} />
        ))}
        {Array.from({ length: n }).map((_, i) => (
          <text key={i} x={x(i)} y={H - 5} textAnchor="middle" fontSize="10" fill="rgb(var(--faint))">{i + 1}</text>
        ))}
      </svg>
      <div className="mt-1 flex flex-wrap gap-3 text-[11px] text-muted">
        {series.map((s) => (
          <span key={s.name} className="flex items-center gap-1.5">
            <span className="h-0.5 w-3" style={{ background: `rgb(var(--${s.tone}))` }} /> {s.name}
          </span>
        ))}
      </div>
    </div>
  );
}

export function DeviceIcon() {
  return <Cpu className="h-4 w-4" />;
}
export { CalendarClock, Sparkles };
