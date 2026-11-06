"use client";
import { FlaskConical, Plus, Search } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { RequireAuth } from "@/components/shell";
import { Badge, Button, Card, CardHeader, cx, Empty, ErrorNote, Field, ModeBadge, Note, PageHeader, Skeleton, useApi } from "@/components/ui";
import { api, url } from "@/lib/api";
import { ago, num } from "@/lib/format";

export default function WorkspacePage() {
  return (
    <RequireAuth what="the Training Room">
      <Suspense>
        <Workspaces />
      </Suspense>
    </RequireAuth>
  );
}

function Workspaces() {
  const sp = useSearchParams();
  const router = useRouter();
  const [q, setQ] = useState("");
  const ws = useApi<any[]>("/api/workspaces");
  const lic = useApi<any[]>(`/api/training/datasets?q=${encodeURIComponent(q)}`, [q]);
  const [sel, setSel] = useState<number[]>([]);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    const a = sp.get("add");
    if (a) setSel((s) => Array.from(new Set([...s, +a])));
  }, [sp]);
  const create = async () => {
    setBusy(true);
    setErr(null);
    try {
      const w = await api("/api/workspaces", { method: "POST", json: { name: name || "New workspace", dataset_ids: sel } });
      router.push(`/workspace/${w.id}`);
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <div>
      <PageHeader eyebrow="Training Room" title="Controlled AI workspace" sub="Fine-tune models on datasets you have licensed. Data is decrypted only inside the training process — no downloads, file browser or shell. You take home the weights." />
      <div className="grid gap-6 lg:grid-cols-[1fr_360px]">
        <Card>
          <CardHeader title="Licensed datasets" sub="Select datasets to add to a new workspace" right={
            <div className="relative w-56"><Search className="pointer-events-none absolute left-2.5 top-2 h-3.5 w-3.5 text-faint" /><input className="input h-8 pl-8 text-xs" placeholder="Search licensed…" value={q} onChange={(e) => setQ(e.target.value)} /></div>
          } />
          {lic.loading && !lic.data ? (
            <div className="space-y-2 p-4">{Array.from({ length: 3 }).map((_, i) => <Skeleton key={i} className="h-16" />)}</div>
          ) : !lic.data?.length ? (
            <div className="p-5"><Empty icon={<FlaskConical className="h-6 w-6" />} title="No licensed datasets yet" sub="License a dataset in the marketplace, or fund a request — delivered samples appear here." action={<Button href="/marketplace">Browse marketplace</Button>} /></div>
          ) : (
            <div className="divide-y divide-line">
              {lic.data.map((d) => {
                const on = sel.includes(d.id);
                return (
                  <button key={d.id} onClick={() => setSel(on ? sel.filter((x) => x !== d.id) : [...sel, d.id])} className={cx("flex w-full items-center gap-3 px-5 py-3 text-left transition-colors", on ? "bg-accent/5" : "hover:bg-raised/50")}>
                    <input type="checkbox" readOnly checked={on} />
                    {d.cover_url ? <img src={url(d.cover_url)} alt="" className="h-10 w-14 rounded-md object-cover" /> : <div className="h-10 w-14 rounded-md bg-raised" />}
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-sm font-medium">{d.title}</div>
                      <div className="truncate text-xs text-muted">{num(d.sample_count)} samples · classes: {Object.keys(d.label_counts).join(", ")}</div>
                    </div>
                    <div className="flex shrink-0 gap-1"><Badge tone={d.access === "owner" ? "accent" : "ok"}>{d.access}</Badge><ModeBadge mode={d.mode} /></div>
                  </button>
                );
              })}
            </div>
          )}
        </Card>
        <div className="space-y-6">
          <Card className="space-y-3 p-5">
            <div className="text-sm font-semibold">New workspace</div>
            <Field label="Name"><input className="input" value={name} onChange={(e) => setName(e.target.value)} placeholder="Shelf stock-out detector" /></Field>
            <div className="text-xs text-muted">{sel.length} dataset{sel.length === 1 ? "" : "s"} selected</div>
            <Button variant="primary" className="w-full" onClick={create} loading={busy} disabled={!sel.length}><Plus className="h-4 w-4" /> Create workspace</Button>
            <ErrorNote>{err}</ErrorNote>
          </Card>
          <ZeroGPanel />
          <Card>
            <CardHeader title="Your workspaces" />
            <div className="divide-y divide-line">
              {(ws.data || []).map((w) => (
                <Link key={w.id} href={`/workspace/${w.id}`} className="block px-5 py-3 hover:bg-raised/50">
                  <div className="text-sm font-medium">{w.name}</div>
                  <div className="text-xs text-muted">{w.datasets.length} datasets · {w.runs.length} runs · {ago(w.created_at)}</div>
                </Link>
              ))}
              {ws.data?.length === 0 && <div className="px-5 py-4 text-xs text-muted">None yet.</div>}
            </div>
          </Card>
          <Note>Restrictions by design: no raw dataset downloads, no file browser, no arbitrary export, no notebooks or shell.</Note>
        </div>
      </div>
    </div>
  );
}

function ZeroGPanel() {
  const ft = useApi<any>("/api/zerog/ft", [], 15000);
  if (!ft.data) return <Card><CardHeader title="0G TEE fine-tuning" sub="loading…" /></Card>;
  const d = ft.data;
  const funded = (d.funding?.ledger_total_0g || 0) > 0;
  return (
    <Card>
      <CardHeader
        title="0G TEE fine-tuning"
        sub={d.enabled
          ? `Provider ${d.provider ? `${d.provider.slice(0, 8)}…` : "none"} · wallet ${d.funding?.wallet_0g} 0G · ledger ${d.funding?.ledger_total_0g} 0G`
          : "0G wallet key not configured"}
        right={d.tasks?.length > 0 ? <Badge tone={d.tasks[0].deliver_index ? "ok" : "warn"}>{d.tasks[0].progress || "queued"}</Badge> : funded ? <Badge>ready</Badge> : <Badge tone="warn">unfunded</Badge>}
      />
      <div className="divide-y divide-line">
        {(d.tasks || []).map((t: any) => (
          <div key={t.id} className="flex items-center justify-between gap-2 px-5 py-2.5">
            <div className="min-w-0">
              <div className="truncate text-xs font-medium">task {t.id?.slice(0, 8)}…</div>
              <div className="text-[11px] text-muted">Qwen2.5-0.5B LoRA · fee {t.fee_0g} 0G · {t.progress}</div>
            </div>
            <div className="text-right text-[11px] text-muted">
              {t.deliver_index ? <Badge tone="ok">deliverable #{t.deliver_index}</Badge> : <Badge>{t.progress || "queued"}</Badge>}
            </div>
          </div>
        ))}
        {(!d.tasks || d.tasks.length === 0) && (
          <div className="px-5 py-4 text-xs text-muted">
            {d.error ? `0G pipeline: ${d.error}` : funded
              ? "No fine-tuning tasks yet — run backend/scripts/zerog_finetune.py <dataset_id> to train in a TEE."
              : "Funding: create the 0G compute ledger (3 0G) and fund the provider (1 0G) to train in a TEE. See README → 0G integration."}
          </div>
        )}
      </div>
    </Card>
  );
}
