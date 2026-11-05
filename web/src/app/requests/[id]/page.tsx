"use client";
import { Camera, Coins, Database, FlaskConical, Lock, RotateCcw } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { TxLink } from "@/components/domain";
import { Badge, Button, Card, CardHeader, Empty, ErrorNote, KV, ModeBadge, Note, Progress, Skeleton, Stat, useApi } from "@/components/ui";
import { api, url } from "@/lib/api";
import { sendVeridata, txErr } from "@/lib/chain";
import { ago, date, eth, num } from "@/lib/format";
import { useSession } from "@/lib/session";

export default function RequestDetail() {
  const { id } = useParams<{ id: string }>();
  const { me, chain, refresh } = useSession();
  const { data: r, loading, reload } = useApi<any>(`/api/requests/${id}`);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  if (loading && !r) return <Skeleton className="h-[500px]" />;
  if (!r) return <Empty title="Request not found" />;
  const isBuyer = me && r.buyer?.id === me.id;
  const refundable = r.status !== "closed" && (r.days_left <= 0 || r.accepted >= r.quantity);
  const s = r.spec || {};

  const doRefund = async () => {
    setBusy(true);
    setErr(null);
    try {
      let tx = "";
      if (r.mode === "onchain") tx = await sendVeridata(chain!.contract, "closeAndRefund", [BigInt(r.chain_request_id)]);
      await api(`/api/requests/${r.id}/refund`, { method: "POST", json: { tx_hash: tx } });
      await Promise.all([reload(), refresh()]);
    } catch (e: any) {
      setErr(txErr(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="max-w-3xl">
          <div className="mb-2 flex flex-wrap gap-1.5">
            <Badge tone="accent">{r.category}</Badge>
            <ModeBadge mode={r.mode} />
            <Badge tone={r.status === "open" ? "ok" : "neutral"}>{r.status}</Badge>
          </div>
          <h1 className="text-[24px] font-semibold tracking-tight">{r.title}</h1>
          <p className="mt-2 text-sm text-muted">{r.description}</p>
          <div className="mt-2 text-xs text-muted">Requested by <Link className="link" href={`/profile?address=${r.buyer.address}`}>{r.buyer.name}</Link> · posted {ago(r.created_at)}</div>
        </div>
        {!isBuyer && r.status === "open" && (
          <Button variant="primary" href={`/upload?request=${r.id}`}><Camera className="h-4 w-4" /> Contribute samples</Button>
        )}
      </div>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label="Per accepted sample" value={eth(r.price_per_sample)} />
        <Stat label="Fulfilled" value={`${num(r.accepted)} / ${num(r.quantity)}`} sub={`${num(r.remaining)} remaining`} />
        <Stat label="Remaining escrow" value={eth(r.remaining_escrow)} icon={<Lock className="h-4 w-4" />} />
        <Stat label="Deadline" value={`${r.days_left} days`} sub={date(r.deadline)} />
      </div>
      <Progress value={r.progress} tone={r.progress >= 1 ? "ok" : "accent"} />

      <div className="grid gap-6 lg:grid-cols-[1fr_360px]">
        <Card>
          <CardHeader title="Submissions" sub="Verification-gated payouts from escrow" />
          {r.submissions.length === 0 ? (
            <div className="p-5"><Empty title="No submissions yet" sub="Contributors capture with registered devices and submit here." /></div>
          ) : (
            <div className="divide-y divide-line">
              {r.submissions.map((x: any) => (
                <div key={x.id} className="flex items-start gap-3 px-5 py-3">
                  {x.sample?.preview_url ? <img src={url(x.sample.preview_url)} alt="" className="h-12 w-16 shrink-0 rounded-md object-cover" /> : <div className="grid h-12 w-16 shrink-0 place-items-center rounded-md bg-raised text-[10px] text-faint">batch</div>}
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center justify-between gap-2">
                      <span className="truncate text-sm font-medium">{x.contributor?.name}</span>
                      <Badge tone={x.status === "accepted" ? "ok" : x.status === "rejected" ? "bad" : "neutral"}>{x.status}</Badge>
                    </div>
                    <div className="mt-0.5 text-xs text-muted">
                      {x.status === "accepted" ? <>+{eth(x.payout)} · <TxLink hash={x.tx_hash} urlStr={x.tx_url} mode={x.mode} /></> : x.reasons?.join(" · ")}
                    </div>
                    <div className="text-[11px] text-faint">{ago(x.created_at)}</div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </Card>

        <div className="space-y-6">
          <Card>
            <CardHeader title="Requirements" />
            <div className="px-5 py-3">
              <KV k="Format" v={s.media_format} />
              <KV k="Min resolution" v={s.min_resolution} />
              <KV k="Min quality" v={s.min_quality} />
              <KV k="Accepted labels" v={(s.labels || []).join(", ") || "any"} />
              <KV k="Sensors" v={(s.sensors || []).join(", ") || "—"} />
              <KV k="Required metadata" v={(s.required_metadata || []).join(", ") || "—"} />
              <KV k="Location" v={s.location || "any"} />
              <KV k="Conditions" v={s.conditions || "—"} />
              <KV k="Device signature" v={s.require_device_signature ? <Badge tone="ok">required</Badge> : "optional"} />
              <KV k="Spec hash" v={<span className="hash">{r.spec_hash.slice(0, 16)}…</span>} />
            </div>
          </Card>
          <Card>
            <CardHeader title="Escrow" icon={<Coins className="h-4 w-4" />} />
            <div className="px-5 py-3">
              <KV k="Deposited" v={eth(r.deposited)} />
              <KV k="Released to contributors" v={eth(r.released)} />
              <KV k="Refunded" v={eth(r.refunded)} />
              <KV k="Locked" v={<b>{eth(r.remaining_escrow)}</b>} />
              <KV k="Funding tx" v={<TxLink hash={r.fund_tx} urlStr={r.fund_tx_url} mode={r.mode} />} />
              {r.chain_request_id && <KV k="On-chain request" v={`#${r.chain_request_id}`} />}
            </div>
            {isBuyer && (
              <div className="space-y-2 border-t border-line p-5">
                {r.delivery_dataset_id && (
                  <Button className="w-full" href={`/workspace?add=${r.delivery_dataset_id}`}><FlaskConical className="h-4 w-4" /> Train on delivered samples</Button>
                )}
                <Button variant="secondary" className="w-full" onClick={doRefund} loading={busy} disabled={!refundable}><RotateCcw className="h-4 w-4" /> Close & refund remainder</Button>
                {!refundable && r.status !== "closed" && <Note>Refunds unlock after the deadline or once the request is filled.</Note>}
                <ErrorNote>{err}</ErrorNote>
              </div>
            )}
            {r.delivery_dataset_id && !isBuyer && (
              <div className="border-t border-line px-5 py-3 text-xs text-muted"><Database className="mr-1 inline h-3.5 w-3.5" />Accepted samples are delivered to the buyer’s private training dataset; you keep attribution.</div>
            )}
          </Card>
        </div>
      </div>
    </div>
  );
}
