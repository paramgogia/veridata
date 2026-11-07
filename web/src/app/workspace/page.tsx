"use client";
import { FlaskConical, Plus, Search, Sparkles } from "lucide-react";
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
  const [ds, setDs] = useState("1");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  if (!ft.data) return <Card><CardHeader title="0G TEE fine-tuning" sub="loading…" /></Card>;
  const d = ft.data;
  const funded = (d.funding?.ledger_total_0g || 0) > 0;
  const run = d.run || {};
  const running = run.status === "running";
  const start = async () => {
    setBusy(true);
    setErr(null);
    try {
      await api("/api/zerog/ft/tasks", { method: "POST", json: { dataset_id: Number(ds) } });
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Card>
      <CardHeader
        title="0G TEE fine-tuning"
        sub={d.enabled
          ? `Provider ${d.provider ? `${d.provider.slice(0, 8)}…` : "none"} · wallet ${d.funding?.wallet_0g} 0G · ledger ${d.funding?.ledger_total_0g} 0G`
          : "0G wallet key not configured"}
        right={running
          ? <Badge tone="warn">{run.stage || "running"}</Badge>
          : d.tasks?.length > 0 ? <Badge tone={d.tasks[0].deliver_index ? "ok" : "warn"}>{d.tasks[0].progress || "queued"}</Badge>
            : funded ? <Badge>ready</Badge> : <Badge tone="warn">unfunded</Badge>}
      />
      <div className="divide-y divide-line">
        <div className="flex items-center gap-2 px-5 py-3">
          <Field label="Dataset id" className="w-20"><input className="input" value={ds} onChange={(e) => setDs(e.target.value)} /></Field>
          <Button variant="primary" size="sm" onClick={start} loading={busy} disabled={running || !funded}>
            <Sparkles className="h-3.5 w-3.5" /> Fine-tune in TEE
          </Button>
        </div>
        {err && <div className="px-5 py-2"><ErrorNote>{err}</ErrorNote></div>}
        {running && (
          <div className="px-5 py-3">
            <div className="text-xs font-medium">Run: dataset {run.dataset_id} · task {run.task_id ? `${run.task_id.slice(0, 8)}…` : "—"}</div>
            <div className="mt-1 max-h-28 overflow-y-auto space-y-0.5 rounded-md bg-bg p-2 font-mono text-[10px] leading-relaxed text-muted">
              {(run.logs || []).map((l: string, i: number) => <div key={i}>{l}</div>)}
              {!(run.logs || []).length && <div>starting…</div>}
            </div>
          </div>
        )}
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
        {(!d.tasks || d.tasks.length === 0) && !running && (
          <div className="px-5 py-4 text-xs text-muted">
            {d.error ? `0G pipeline: ${d.error}` : funded
              ? "No fine-tuning tasks yet — pick a dataset id above and fine-tune it inside a 0G TEE."
              : "Funding: create the 0G compute ledger (3 0G) and fund the provider (1 0G) to train in a TEE. See README → 0G integration."}
          </div>
        )}
        <ZeroGDeploy d={d} />
      </div>
    </Card>
  );
}

function ZeroGDeploy({ d }: { d: any }) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [msg, setMsg] = useState("");
  const [reply, setReply] = useState<any>(null);
  const [chatting, setChatting] = useState(false);
  const deploy = d.deploy || {};
  const deploying = deploy.status === "running";
  const agents = d.agents || [];
  const finished = (d.tasks || []).find((t: any) => t.progress === "Finished");
  const agent = agents.find((a: any) => a.state === "ready") || agents[0];
  const doDeploy = async () => {
    setBusy(true); setErr(null);
    try {
      await api("/api/zerog/ft/deploy", { method: "POST", json: { task_id: finished.id } });
    } catch (e: any) {
      setErr(e.message);
    } finally { setBusy(false); }
  };
  const doChat = async () => {
    setChatting(true); setReply(null);
    try {
      setReply(await api("/api/zerog/ft/chat", { method: "POST", json: { adapter: agent.adapter, message: msg } }));
    } catch (e: any) {
      setErr(e.message);
    } finally { setChatting(false); }
  };
  if (!finished && agents.length === 0 && !deploying) return null;
  return (
    <div className="border-t border-line">
      <div className="px-5 py-3">
        <div className="mb-1 text-xs font-semibold text-faint">Deploy & serve</div>
        {finished && !agents.length && (
          <Button size="sm" variant="primary" loading={busy || deploying} onClick={doDeploy}>
            <Sparkles className="h-3.5 w-3.5" /> Deploy adapter ({finished.id.slice(0, 8)}…)
          </Button>
        )}
        {deploying && (
          <div className="mt-2 max-h-20 overflow-y-auto rounded-md bg-bg p-2 font-mono text-[10px] leading-relaxed text-muted">
            {(deploy.logs || []).map((l: string, i: number) => <div key={i}>{l}</div>)}
          </div>
        )}
        {deploy.status === "error" && <div className="mt-1"><ErrorNote>{deploy.error}</ErrorNote></div>}
        {agents.map((a: any) => (
          <div key={a.adapter} className="mt-1 flex items-center justify-between gap-2">
            <span className="text-[11px] text-muted">adapter <span className="hash">{a.adapter?.slice(0, 14)}…</span></span>
            <Badge tone={a.state === "ready" ? "ok" : "warn"}>{a.state}</Badge>
          </div>
        ))}
        {agent && (
          <div className="mt-2 flex items-center gap-2">
            <input className="input" placeholder={`Ask ${agent.adapter.slice(0, 10)}…`} value={msg} onChange={(e) => setMsg(e.target.value)} />
            <Button size="sm" variant="primary" loading={chatting} onClick={doChat} disabled={!msg}>Send</Button>
          </div>
        )}
        {reply && <div className="mt-2 rounded-md bg-bg p-2 text-xs text-muted">{JSON.stringify(reply, null, 2).slice(0, 600)}</div>}
        {err && <div className="mt-1"><ErrorNote>{err}</ErrorNote></div>}
      </div>
    </div>
  );
}
