"use client";
import { Cpu, FlaskConical, Lock, MapPin, ShieldAlert, ShoppingCart, Tag, Zap } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { ProofCard, TxLink, useSettlement } from "@/components/domain";
import { Badge, Button, Card, CardHeader, Empty, ErrorNote, KV, ModeBadge, Note, Skeleton, useApi } from "@/components/ui";
import { API_BASE, api, getToken, url } from "@/lib/api";
import { sendVeridata, txErr } from "@/lib/chain";
import { payWithUsdt } from "@/lib/whitechain";
import { day, eth, num, toWei } from "@/lib/format";
import { useSession } from "@/lib/session";

export default function DatasetDetail() {
  const { id } = useParams<{ id: string }>();
  const { me, refresh } = useSession();
  const { data: d, loading, error, reload } = useApi<any>(`/api/datasets/${id}`, [me?.id]);
  const { mode, picker, contract } = useSettlement();
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [rawMsg, setRawMsg] = useState<string | null>(null);
  const { data: wcPrice } = useApi<any>(`/api/whitechain/price/${id}`, [id]);
  const [wcTx, setWcTx] = useState<any>(null);

  if (loading && !d) return <Skeleton className="h-[600px]" />;
  if (error || !d) return <Empty title="Dataset not found" sub={error || ""} />;

  const buy = async () => {
    setErr(null);
    setBusy("buy");
    try {
      if (mode === "onchain") {
        if (d.mode !== "onchain") throw new Error("This dataset is not listed on-chain; use the demo ledger.");
        const tx = await sendVeridata(contract, "purchaseLicense", [BigInt(d.chain_dataset_id)], toWei(d.price));
        await api(`/api/datasets/${d.id}/purchase`, { method: "POST", json: { tx_hash: tx } });
      } else {
        await api(`/api/datasets/${d.id}/purchase`, { method: "POST", json: {} });
      }
      await Promise.all([reload(), refresh()]);
    } catch (e: any) {
      setErr(txErr(e));
    } finally {
      setBusy(null);
    }
  };

  const buyUsdt = async () => {
    setErr(null);
    setBusy("usdt");
    try {
      const r = await payWithUsdt(d.id);
      setWcTx(r.payment);
      await Promise.all([reload(), refresh()]);
    } catch (e: any) {
      setErr(txErr(e));
    } finally {
      setBusy(null);
    }
  };

  const tryRaw = async () => {
    const r = await fetch(`${API_BASE}/api/datasets/${d.id}/download`, { headers: getToken() ? { Authorization: `Bearer ${getToken()}` } : {} });
    setRawMsg(`HTTP ${r.status} — ${(await r.json()).detail}`);
  };

  const own = me && d.owner?.id === me.id;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="max-w-3xl">
          <div className="mb-2 flex flex-wrap gap-1.5">
            <ModeBadge mode={d.mode} />
            {d.categories.map((c: string) => <Badge key={c} tone="accent">{c}</Badge>)}
          </div>
          <h1 className="text-[24px] font-semibold tracking-tight">{d.title}</h1>
          <p className="mt-2 text-sm leading-relaxed text-muted">{d.description}</p>
          <div className="mt-3 flex flex-wrap gap-4 text-xs text-muted">
            <span className="flex items-center gap-1"><MapPin className="h-3.5 w-3.5" />{d.location || "—"}</span>
            <span>{num(d.sample_count)} samples · {d.format}</span>
            <span>Quality {d.quality_score}</span>
            <span>{d.buyers} licensees</span>
          </div>
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-[1fr_380px]">
        <div className="space-y-6">
          <Card>
            <CardHeader title="Privacy-safe preview" sub="Downscaled, watermarked previews. Originals stay encrypted." icon={<Lock className="h-4 w-4" />} />
            <div className="grid grid-cols-3 gap-2 p-4 sm:grid-cols-4 md:grid-cols-6">
              {d.samples.slice(0, 18).map((s: any) => (
                <div key={s.id} className="group relative aspect-square overflow-hidden rounded-lg bg-raised">
                  <img src={url(s.preview_url)} alt={s.label} className="h-full w-full object-cover" loading="lazy" />
                  <div className="absolute inset-x-0 bottom-0 bg-bg/80 px-1.5 py-0.5 text-[10px] text-muted opacity-0 transition group-hover:opacity-100">{s.label}</div>
                </div>
              ))}
            </div>
          </Card>

          <div className="grid gap-6 md:grid-cols-2">
            <Card>
              <CardHeader title="Labels" sub="Class distribution" icon={<Tag className="h-4 w-4" />} />
              <div className="space-y-2 p-4">
                {Object.entries(d.label_counts || {}).map(([k, v]: any) => (
                  <div key={k}>
                    <div className="mb-1 flex justify-between text-xs"><span>{k}</span><span className="tabular-nums text-muted">{v}</span></div>
                    <div className="h-1 rounded-full bg-line"><div className="h-1 rounded-full bg-accent/70" style={{ width: `${(v / d.sample_count) * 100}%` }} /></div>
                  </div>
                ))}
              </div>
            </Card>
            <Card>
              <CardHeader title="Metadata" icon={<Cpu className="h-4 w-4" />} />
              <div className="px-4 py-2">
                <KV k="Sensors" v={d.sensor_types.join(", ")} />
                <KV k="Tags" v={d.tags.join(", ") || "—"} />
                <KV k="Captured" v={`${day(d.capture_start)} – ${day(d.capture_end)}`} />
                <KV k="Devices" v={d.devices.map((x: any) => x.id).join(", ") || "—"} />
                <KV k="Seller" v={<Link className="link" href={`/profile?address=${d.owner.address}`}>{d.owner.name}</Link>} />
              </div>
            </Card>
          </div>

          <Card>
            <CardHeader title="Access policy" icon={<ShieldAlert className="h-4 w-4" />} />
            <div className="space-y-3 p-4 text-sm">
              <ul className="list-inside list-disc space-y-1 text-xs text-muted">
                <li>License: {d.license}. Not resellable or transferable.</li>
                <li>Training happens inside the Veridata Training Room; media is decrypted in memory only.</li>
                <li>No raw download, file browser or notebook. Trained weights are exportable.</li>
                <li>Every access attempt is written to the audit log.</li>
              </ul>
              <div className="flex items-center gap-3">
                <Button size="sm" variant="ghost" onClick={tryRaw}>Try raw dataset download</Button>
                {rawMsg && <span className="font-mono text-[11px] text-bad">{rawMsg}</span>}
              </div>
            </div>
          </Card>
        </div>

        <div className="space-y-6">
          <Card className="p-5">
            <div className="flex items-baseline justify-between">
              <div className="text-2xl font-semibold tabular-nums">{eth(d.price)}</div>
              <span className="text-xs text-muted">one-time · training license</span>
            </div>
            <div className="mt-4 space-y-3">
              {d.licensed ? (
                <>
                  <Badge tone="ok">{own ? "You own this dataset" : "Licensed"}</Badge>
                  {wcTx && (
                    <Note tone="chain">Paid {wcTx.usdt} USDT, gas {(wcTx.gas_cost_wei / 1e18).toFixed(6)} WBT covered by Veridata.{" "}
                      <a className="text-chain hover:underline" href={wcTx.explorer} target="_blank" rel="noreferrer">View on Whitechain explorer</a></Note>
                  )}
                  {d.license_record && (
                    <div className="text-xs text-muted">
                      <TxLink hash={d.license_record.tx_hash} urlStr={d.license_record.tx_url} mode={d.license_record.mode} />
                    </div>
                  )}
                  <Button variant="primary" className="w-full" href={`/workspace?add=${d.id}`}>
                    <FlaskConical className="h-4 w-4" /> Open in Training Room
                  </Button>
                </>
              ) : !me ? (
                <Note>Sign in to license this dataset.</Note>
              ) : (
                <>
                  {picker}
                  <Button variant={mode === "onchain" ? "chain" : "primary"} className="w-full" onClick={buy} loading={busy === "buy"}>
                    <ShoppingCart className="h-4 w-4" /> {mode === "onchain" ? "Buy license on Sepolia" : "Buy with demo ledger"}
                  </Button>
                  {mode === "onchain" && d.mode !== "onchain" && <Note tone="warn">This is a demo-seed listing, not on-chain. Use the demo ledger or publish your own dataset on Sepolia.</Note>}
                  {wcPrice?.enabled && (
                    <div className="space-y-1.5 border-t border-line pt-3">
                      <Button variant="chain" className="w-full" onClick={buyUsdt} loading={busy === "usdt"}>
                        <Zap className="h-4 w-4" /> Pay {wcPrice.usdt} USDT on Whitechain · no gas
                      </Button>
                      <p className="text-[11px] leading-relaxed text-faint">
                        You sign one message (EIP-3009); Veridata&apos;s relayer pays the gas. Same x402 endpoint AI agents use. You need USDT only, no WBT.
                      </p>
                    </div>
                  )}
                </>
              )}
              <ErrorNote>{err}</ErrorNote>
              <p className="text-[11px] leading-relaxed text-faint">5% platform fee. On-chain payments split seller/treasury atomically in Veridata.sol.</p>
            </div>
          </Card>
          <ProofCard d={d} />
        </div>
      </div>
    </div>
  );
}
