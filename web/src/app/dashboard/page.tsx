"use client";
import { ArrowDownLeft, ArrowUpRight, Coins, Cpu, Database, FlaskConical, Lock, Wallet } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { TxLink } from "@/components/domain";
import { RequireAuth } from "@/components/shell";
import { Badge, Button, Card, CardHeader, cx, Empty, ModeBadge, PageHeader, Progress, Stat, Tabs, useApi } from "@/components/ui";
import { api } from "@/lib/api";
import { ago, eth, pct } from "@/lib/format";
import { useSession } from "@/lib/session";

export default function DashboardPage() {
  return (
    <RequireAuth what="your dashboard">
      <Dashboard />
    </RequireAuth>
  );
}

function Dashboard() {
  const { me, refresh } = useSession();
  const d = useApi<any>("/api/dashboard", [me?.id]);
  const txs = useApi<any[]>("/api/transactions", [me?.id]);
  const [tab, setTab] = useState<"contributor" | "buyer">("contributor");
  const x = d.data;
  if (!x) return null;
  const st = x.stats;
  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Overview"
        title={`Welcome back, ${me!.name}`}
        sub="Earnings, escrow, licenses and training at a glance. Every amount shows whether it settled on Sepolia or on the demo ledger."
        right={<Tabs value={tab} onChange={setTab} items={[{ id: "contributor", label: "Contributor" }, { id: "buyer", label: "Buyer" }]} />}
      />
      {me!.demo && (
        <Card className="flex flex-wrap items-center justify-between gap-3 border-warn/25 p-4">
          <div className="text-xs text-muted"><Badge tone="warn">Demo persona</Badge> <span className="ml-2">Demo-ledger balance <b className="text-fg">{eth(st.demo_balance)}</b> — no real value.</span></div>
          <Button size="sm" onClick={async () => { await api("/api/me/faucet", { method: "POST" }); refresh(); d.reload(); }}>Top up demo ledger</Button>
        </Card>
      )}

      {tab === "contributor" ? (
        <>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <Stat label="Total earned" value={eth(st.earned)} icon={<Coins className="h-4 w-4" />} sub="payouts + dataset sales" />
            <Stat label="Accepted samples" value={st.accepted_submissions} sub={`${st.rejected_submissions} rejected`} />
            <Stat label="Requests fulfilled" value={st.fulfilled_requests} />
            <Stat label="Devices" value={x.devices.length} icon={<Cpu className="h-4 w-4" />} />
          </div>
          <div className="grid gap-6 lg:grid-cols-2">
            <Card>
              <CardHeader title="Recent submissions" right={<Button size="sm" href="/demand">Find requests</Button>} />
              <div className="divide-y divide-line">
                {x.submissions.map((s: any) => (
                  <Link key={s.id} href={`/requests/${s.request_id}`} className="flex items-center justify-between gap-3 px-5 py-2.5 text-xs hover:bg-raised/40">
                    <span>Request #{s.request_id} · {ago(s.created_at)}</span>
                    {s.status === "accepted" ? <span className="flex items-center gap-2 text-ok">+{eth(s.payout)} <TxLink hash={s.tx_hash} urlStr={s.tx_url} mode={s.mode} /></span> : <Badge tone="bad">rejected</Badge>}
                  </Link>
                ))}
                {!x.submissions.length && <div className="p-5"><Empty title="No submissions yet" sub="Pick a request on the Demand Board and capture samples." /></div>}
              </div>
            </Card>
            <Card>
              <CardHeader title="My datasets" right={<Button size="sm" href="/upload">Publish new</Button>} />
              <div className="divide-y divide-line">
                {x.datasets.map((ds: any) => (
                  <Link key={ds.id} href={`/marketplace/${ds.id}`} className="flex items-center justify-between gap-3 px-5 py-2.5 text-xs hover:bg-raised/40">
                    <span className="truncate">{ds.title}</span>
                    <span className="flex shrink-0 items-center gap-2"><ModeBadge mode={ds.mode} />{eth(ds.price)}</span>
                  </Link>
                ))}
                {!x.datasets.length && <div className="p-5"><Empty icon={<Database className="h-5 w-5" />} title="No datasets published" /></div>}
              </div>
            </Card>
          </div>
        </>
      ) : (
        <>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <Stat label="Escrow deposited" value={eth(x.escrow.deposited)} icon={<Wallet className="h-4 w-4" />} />
            <Stat label="Locked" value={eth(x.escrow.locked)} icon={<Lock className="h-4 w-4" />} />
            <Stat label="Released" value={eth(x.escrow.released)} sub="paid to contributors" />
            <Stat label="Refunded" value={eth(x.escrow.refunded)} />
          </div>
          <div className="grid gap-6 lg:grid-cols-2">
            <Card>
              <CardHeader title="My requests" right={<Button size="sm" href="/requests?new=1">New request</Button>} />
              <div className="divide-y divide-line">
                {x.requests.map((r: any) => (
                  <Link key={r.id} href={`/requests/${r.id}`} className="block px-5 py-3 hover:bg-raised/40">
                    <div className="flex justify-between gap-2 text-xs"><span className="truncate font-medium">{r.title}</span><ModeBadge mode={r.mode} /></div>
                    <div className="mt-2 flex items-center gap-3 text-[11px] text-muted"><Progress value={r.progress} className="flex-1" /><span className="tabular-nums">{r.accepted}/{r.quantity}</span></div>
                  </Link>
                ))}
                {!x.requests.length && <div className="p-5"><Empty title="No requests yet" /></div>}
              </div>
            </Card>
            <Card>
              <CardHeader title="Licenses & training" right={<Button size="sm" href="/workspace"><FlaskConical className="h-3.5 w-3.5" /> Training Room</Button>} />
              <div className="divide-y divide-line">
                {x.licenses.map((l: any, i: number) => (
                  <Link key={i} href={`/marketplace/${l.dataset.id}`} className="flex items-center justify-between gap-3 px-5 py-2.5 text-xs hover:bg-raised/40">
                    <span className="truncate">{l.dataset.title}</span>
                    <span className="flex shrink-0 items-center gap-2"><TxLink hash={l.tx_hash} urlStr={l.tx_url} mode={l.mode} /></span>
                  </Link>
                ))}
                {x.runs.map((r: any) => (
                  <Link key={r.id} href={`/workspace/${r.workspace_id}`} className="flex items-center justify-between px-5 py-2.5 text-xs hover:bg-raised/40">
                    <span>Run #{r.id} · {r.base_model}</span>
                    <span className="text-muted">{r.after ? `val acc ${pct(r.after.accuracy)}` : r.status}</span>
                  </Link>
                ))}
                {!x.licenses.length && !x.runs.length && <div className="p-5"><Empty title="No licenses yet" /></div>}
              </div>
            </Card>
          </div>
        </>
      )}

      <Card>
        <CardHeader title="Transactions" sub="Deposits, payouts, purchases, fees and refunds" />
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead className="text-left text-faint">
              <tr className="border-b border-line">
                <th className="px-5 py-2 font-medium">Type</th><th className="px-3 py-2 font-medium">Reference</th><th className="px-3 py-2 text-right font-medium">Amount</th><th className="px-3 py-2 font-medium">Settlement</th><th className="px-5 py-2 font-medium">When</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {(txs.data || []).map((t) => (
                <tr key={t.id}>
                  <td className="px-5 py-2"><span className="flex items-center gap-1.5">{t.direction === "in" ? <ArrowDownLeft className="h-3.5 w-3.5 text-ok" /> : <ArrowUpRight className="h-3.5 w-3.5 text-muted" />}{t.kind.replace(/_/g, " ")}</span></td>
                  <td className="px-3 py-2 font-mono text-muted">{t.ref || t.memo}</td>
                  <td className={cx("px-3 py-2 text-right tabular-nums", t.direction === "in" ? "text-ok" : "")}>{t.direction === "in" ? "+" : "−"}{eth(t.amount)}</td>
                  <td className="px-3 py-2">{t.mode === "onchain" ? <TxLink hash={t.tx_hash} urlStr={t.tx_url} /> : <span className="text-faint">demo ledger</span>}</td>
                  <td className="px-5 py-2 text-muted">{ago(t.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {txs.data?.length === 0 && <div className="p-5 text-xs text-muted">No transactions.</div>}
        </div>
      </Card>
    </div>
  );
}
