"use client";
import { ArrowRight, BadgeCheck, Coins, Cpu, Database, Flame, Lock, Plus, Radar } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { DatasetCard, DemandCard, TxLink } from "@/components/domain";
import { Badge, Button, Card, CardHeader, Empty, ModeBadge, Skeleton, Stat, Tabs, useApi } from "@/components/ui";
import { ago, eth, num } from "@/lib/format";
import { queryRequests, arkivEnabled } from "@/lib/arkiv";

export default function DemandBoard() {
  const [sort, setSort] = useState<"value" | "deadline" | "recent" | "progress">("value");
  const [arkivData, setArkivData] = useState<any[] | null>(null);
  const [usingArkiv, setUsingArkiv] = useState(false);
  const stats = useApi("/api/stats");
  const reqs = useApi<any[]>(`/api/requests?sort=${sort}`, [sort]);
  const fulfilled = useApi<any[]>("/api/requests/recent-fulfilled");
  const datasets = useApi<any[]>("/api/datasets?sort=quality&limit=4");

  useEffect(() => {
    if (arkivEnabled()) {
      queryRequests({ status: "open" })
        .then((entities) => {
          if (entities && entities.length > 0) {
            setArkivData(entities);
            setUsingArkiv(true);
          }
        })
        .catch(() => { });
    }
  }, []);

  const s = stats.data;
  const list = arkivData && arkivData.length > 0 ? arkivData : (reqs.data || []);
  const top = [...list].sort((a, b) => b.remaining_escrow - a.remaining_escrow)[0];

  return (
    <div className="space-y-8">
      <section className="flex flex-wrap items-end justify-between gap-6">
        <div className="max-w-2xl">
          <div className="label mb-2 flex items-center gap-1.5">
            <Radar className="h-3.5 w-3.5" /> Demand Board
            {usingArkiv ? (
              <Badge tone="accent" dot>Decentralized DB: Arkiv Rabdi</Badge>
            ) : (
              <Badge tone="neutral">Source: Argus API (Arkiv not reachable)</Badge>
            )}
          </div>
          <h1 className="text-[28px] font-semibold leading-tight tracking-tight">What AI teams need captured right now</h1>
          <p className="mt-2 text-sm text-muted">
            AI teams post what they need captured: photos or short clips with RFID, IR and temperature/humidity readings signed in. Contributors capture with an Argus rig, pass provenance, quality and privacy checks, and get paid per accepted sample.
          </p>
          <div className="mt-3 flex flex-wrap items-center gap-2 text-[11px] text-muted">
            <Badge tone="chain" dot>On-chain · Sepolia</Badge> ETH locked in the Veridata.sol escrow; the buyer releases payouts per accepted sample, unused funds are refundable.
            <Badge>Demo ledger</Badge> walkthrough requests on the off-chain demo ledger.
          </div>
        </div>
        <div className="flex gap-2">
          <Button href="/requests?new=1" variant="primary">
            <Plus className="h-4 w-4" /> Post a request
          </Button>
          <Button href="/upload">Contribute data</Button>
        </div>
      </section>

      <section className="grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-6">
        {!s ? (
          Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-[86px]" />)
        ) : (
          <>
            <Stat label="Contributor earnings" value={eth(s.contributor_earnings, 2)} icon={<Coins className="h-4 w-4" />} sub="payouts + sales" />
            <Stat label="Escrow locked" value={eth(s.escrow_locked, 2)} icon={<Lock className="h-4 w-4" />} sub={`${eth(s.escrow_onchain ?? 0, 3)} on Sepolia · ${s.onchain_requests ?? 0} of ${s.open_requests} requests`} />
            <Stat label="Verified datasets" value={num(s.verified_datasets)} icon={<Database className="h-4 w-4" />} />
            <Stat label="Signed samples" value={num(s.verified_samples)} icon={<BadgeCheck className="h-4 w-4" />} />
            <Stat label="Active devices" value={num(s.active_devices)} icon={<Cpu className="h-4 w-4" />} />
            <Stat label="On-chain txs" value={num(s.onchain_txs)} icon={<Flame className="h-4 w-4" />} sub="Sepolia settlements" />
          </>
        )}
      </section>

      {top && (
        <section>
          <Link href={`/requests/${top.id}`} className="group block">
            <Card className="relative overflow-hidden border-accent/25 p-5 md:p-6">
              <div className="pointer-events-none absolute -right-24 -top-24 h-64 w-64 rounded-full bg-accent/10 blur-3xl" />
              <div className="flex flex-wrap items-center justify-between gap-6">
                <div className="min-w-0">
                  <div className="mb-2 flex items-center gap-2">
                    <Badge tone="accent">Highest-value request</Badge>
                    <ModeBadge mode={top.mode} />
                  </div>
                  <div className="text-xl font-semibold tracking-tight">{top.title}</div>
                  <div className="mt-1 text-sm text-muted">
                    {top.buyer?.name} · {top.category} · {top.days_left} days left
                  </div>
                </div>
                <div className="flex items-center gap-8 text-sm">
                  <div>
                    <div className="text-faint text-xs">Required</div>
                    <div className="font-semibold tabular-nums">{num(top.quantity)}</div>
                  </div>
                  <div>
                    <div className="text-faint text-xs">Per sample</div>
                    <div className="font-semibold tabular-nums">{eth(top.price_per_sample)}</div>
                  </div>
                  <div>
                    <div className="text-faint text-xs">Fulfilled</div>
                    <div className="font-semibold tabular-nums">
                      {num(top.accepted)} / {num(top.quantity)}
                    </div>
                  </div>
                  <div>
                    <div className="text-faint text-xs">Remaining escrow</div>
                    <div className="font-semibold tabular-nums text-ok">{eth(top.remaining_escrow)}</div>
                  </div>
                  <ArrowRight className="h-5 w-5 text-muted transition-transform group-hover:translate-x-1" />
                </div>
              </div>
            </Card>
          </Link>
        </section>
      )}

      <section className="grid gap-6 xl:grid-cols-[1fr_320px]">
        <div>
          <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
            <h2 className="text-sm font-semibold">Open requests</h2>
            <Tabs
              value={sort}
              onChange={setSort}
              items={[
                { id: "value", label: "High value" },
                { id: "progress", label: "Most requested" },
                { id: "deadline", label: "Ending soon" },
                { id: "recent", label: "Newest" },
              ]}
            />
          </div>
          {reqs.loading && !reqs.data ? (
            <div className="grid gap-3 md:grid-cols-2">{Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-[190px]" />)}</div>
          ) : reqs.error ? (
            <Empty title="Can't reach the Argus API" sub={`${reqs.error}. Start the backend on :8000.`} />
          ) : list.length === 0 ? (
            <Empty title="No open requests" sub="Be the first buyer to post a funded request." action={<Button href="/requests?new=1">Post a request</Button>} />
          ) : (
            <div className="grid gap-3 md:grid-cols-2">
              {list.map((r) => (
                <DemandCard key={r.id} r={r} />
              ))}
            </div>
          )}
        </div>

        <aside className="space-y-4">
          <Card>
            <CardHeader title="Trending categories" sub="Remaining samples requested" />
            <div className="space-y-2.5 p-4">
              {(s?.trending_categories || []).map((c: any) => {
                const max = s.trending_categories[0]?.demand || 1;
                return (
                  <Link key={c.category} href={`/requests?category=${c.category}`} className="block">
                    <div className="mb-1 flex justify-between text-xs">
                      <span>{c.category}</span>
                      <span className="tabular-nums text-muted">{num(c.demand)}</span>
                    </div>
                    <div className="h-1 rounded-full bg-line">
                      <div className="h-1 rounded-full bg-accent/70" style={{ width: `${(c.demand / max) * 100}%` }} />
                    </div>
                  </Link>
                );
              })}
            </div>
          </Card>
          <Card>
            <CardHeader title="Recently fulfilled" sub="Accepted samples & payouts" />
            <div className="divide-y divide-line">
              {(fulfilled.data || []).slice(0, 6).map((f: any, i: number) => (
                <div key={i} className="px-4 py-2.5 text-xs">
                  <div className="flex justify-between gap-2">
                    <span className="truncate font-medium">{f.contributor?.name}</span>
                    <span className="shrink-0 tabular-nums text-ok">+{eth(f.payout)}</span>
                  </div>
                  <div className="mt-0.5 flex justify-between gap-2 text-muted">
                    <span className="truncate">{f.title}</span>
                    <span className="shrink-0">{f.tx_hash ? <TxLink hash={f.tx_hash} urlStr={f.tx_url} /> : ago(f.created_at)}</span>
                  </div>
                </div>
              ))}
              {fulfilled.data?.length === 0 && <div className="p-4 text-xs text-muted">Nothing yet.</div>}
            </div>
          </Card>
        </aside>
      </section>

      <section>
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-sm font-semibold">Available datasets</h2>
          <Link href="/marketplace" className="text-xs text-muted hover:text-fg">
            Browse marketplace →
          </Link>
        </div>
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          {(datasets.data || []).map((d) => (
            <DatasetCard key={d.id} d={d} />
          ))}
        </div>
      </section>
    </div>
  );
}
