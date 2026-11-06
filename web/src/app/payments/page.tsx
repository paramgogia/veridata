"use client";
import { Bot, Fuel, Gauge, ShieldCheck, Wallet, Zap } from "lucide-react";
import { Badge, Card, CardHeader, Empty, KV, Note, Skeleton, Stat, useApi } from "@/components/ui";

const short = (a?: string) => (a ? `${a.slice(0, 6)}…${a.slice(-4)}` : "—");

/** Business view for the Whitechain checkout: relayer health, gas spent, USDT volume, every payment. */
export default function Payments() {
  const { data: s, loading } = useApi<any>("/api/whitechain/status", []);
  if (loading && !s) return <Skeleton className="h-[500px]" />;
  if (!s) return <Empty title="Payments unavailable" sub="backend unreachable" />;
  const ex = s.explorer;
  const t = s.totals || {};
  const perPay = t.payments ? t.gasSpentWbt / t.payments : 0;
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold">USDT payments on Whitechain</h1>
        <p className="text-sm text-muted">Buyers and AI agents pay dataset licenses in USDT with one signature. Veridata&apos;s relayer pays the gas in WBT.</p>
      </div>
      {!s.enabled && <Note tone="warn">Checkout disabled: set WHITECHAIN_PAY_ADDRESS (and a relayer key) in .env and restart the backend.</Note>}
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label="USDT volume" value={`${t.volumeUsdt ?? 0} USDT`} sub={`${t.payments ?? 0} payments · ${t.agentPayments ?? 0} by agents`} icon={<Zap className="h-4 w-4" />} />
        <Stat label="Paid to sellers" value={`${t.sellerPayoutsUsdt ?? 0} USDT`} sub="split on-chain, same tx" icon={<Wallet className="h-4 w-4" />} />
        <Stat label="Platform fees" value={`${t.feesUsdt ?? 0} USDT`} sub={`${(s.feeBps ?? 500) / 100}% · treasury ${short(s.treasury)}`} icon={<Gauge className="h-4 w-4" />} />
        <Stat label="Gas we paid" value={`${(t.gasSpentWbt ?? 0).toFixed(6)} WBT`} sub={`≈ ${perPay.toFixed(6)} WBT per payment`} icon={<Fuel className="h-4 w-4" />} />
      </div>
      <div className="grid gap-6 lg:grid-cols-2">
        <Card className="p-5">
          <CardHeader title="Relayer (gas tank)" icon={<Fuel className="h-4 w-4" />}
            right={<Badge tone={s.relayerWbt > s.guards?.minRelayerWbt ? "ok" : "bad"} dot>{s.relayerWbt > s.guards?.minRelayerWbt ? "funded" : "paused"}</Badge>} />
          <div className="mt-3 space-y-1.5 text-sm">
            <KV k="Relayer" v={<a className="text-chain hover:underline" href={`${ex}/address/${s.relayer}`} target="_blank" rel="noreferrer">{short(s.relayer)}</a>} mono />
            <KV k="WBT balance" v={`${(s.relayerWbt ?? 0).toFixed(4)} WBT`} />
            <KV k="Runway" v={perPay ? `≈ ${Math.floor((s.relayerWbt ?? 0) / perPay).toLocaleString()} more payments` : "—"} />
            <KV k="Contract" v={s.contract ? <a className="text-chain hover:underline" href={`${ex}/address/${s.contract}`} target="_blank" rel="noreferrer">{short(s.contract)}</a> : "not deployed"} mono />
            <KV k="USDT" v={<a className="text-chain hover:underline" href={`${ex}/token/${s.usdt}`} target="_blank" rel="noreferrer">{short(s.usdt)}</a>} mono />
            <KV k="Network" v={`Whitechain Sepolia · ${s.chainId}${s.gasPriceGwei != null ? ` · gas ${s.gasPriceGwei.toFixed(2)} gwei` : ""}`} />
          </div>
        </Card>
        <Card className="p-5">
          <CardHeader title="Drain protection" icon={<ShieldCheck className="h-4 w-4" />} />
          <ul className="mt-3 list-disc space-y-1 pl-5 text-[13px] text-muted">
            <li>Relays only <span className="font-mono">VeridataPay.purchase</span>; the signed nonce binds dataset + seller, amount must equal the price.</li>
            <li>Signature verified off-chain, then the call is simulated: forged or failing payments never cost gas.</li>
            <li>Gas price cap {s.guards?.maxGasGwei} gwei, gas limit {s.guards?.gasLimit?.toLocaleString()} per tx.</li>
            <li>{s.guards?.dailyTxCap} relayed payments/day, {s.guards?.perBuyerHourly} per wallet/hour, plus per-IP rate limits.</li>
            <li>Pauses automatically below {s.guards?.minRelayerWbt} WBT. Covered by the {(s.feeBps ?? 500) / 100}% USDT fee.</li>
          </ul>
        </Card>
      </div>
      <Card className="p-5">
        <CardHeader title="Payments" sub="every party: buyer/agent, seller, platform" icon={<Bot className="h-4 w-4" />} />
        {s.payments?.length ? (
          <div className="mt-3 overflow-x-auto">
            <table className="w-full text-left text-[13px]">
              <thead className="text-[11px] uppercase text-faint">
                <tr><th className="py-1.5">Dataset</th><th>Payer</th><th>Seller</th><th>USDT</th><th>Fee</th><th>Gas (WBT)</th><th>Via</th><th>Tx</th></tr>
              </thead>
              <tbody>
                {s.payments.map((p: any) => (
                  <tr key={p.tx_hash} className="border-t border-line">
                    <td className="max-w-[220px] truncate py-1.5">{p.title || `#${p.dataset_id}`}</td>
                    <td className="font-mono">{short(p.buyer)}</td>
                    <td className="font-mono">{short(p.seller)}</td>
                    <td className="tabular-nums">{p.usdt}</td>
                    <td className="tabular-nums">{p.fee}</td>
                    <td className="tabular-nums">{p.gasWbt.toFixed(6)}</td>
                    <td><Badge tone={p.via === "x402-agent" ? "chain" : "neutral"}>{p.via === "x402-agent" ? "AI agent" : "web"}</Badge></td>
                    <td><a className="font-mono text-chain hover:underline" href={p.tx_url} target="_blank" rel="noreferrer">{p.tx_hash.slice(0, 10)}…</a></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="mt-3 text-sm text-muted">No payments yet.</div>
        )}
      </Card>
    </div>
  );
}
