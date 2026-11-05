"use client";
import { AlertTriangle, Box, Download, FileJson, Play, Settings2, ShieldBan, Terminal } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { LineChart } from "@/components/domain";
import { RequireAuth } from "@/components/shell";
import { Badge, Button, Card, CardHeader, cx, Empty, ErrorNote, Field, KV, Note, Progress, Skeleton, useApi } from "@/components/ui";
import { API_BASE, api, download, getToken } from "@/lib/api";
import { date, num, pct } from "@/lib/format";

export default function SessionPage() {
  return (
    <RequireAuth what="the Training Room">
      <Session />
    </RequireAuth>
  );
}

function Session() {
  const { id } = useParams<{ id: string }>();
  const ws = useApi<any>(`/api/workspaces/${id}`);
  const models = useApi<any[]>("/api/training/models");
  const lic = useApi<any[]>("/api/training/datasets");
  const [model, setModel] = useState("veri-cnn-s");
  const [p, setP] = useState({ epochs: 10, learning_rate: 0.003, batch_size: 32, val_split: 0.25, augment: true });
  const [runId, setRunId] = useState<number | null>(null);
  const [run, setRun] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const [denied, setDenied] = useState<string | null>(null);
  const logRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!runId && ws.data?.runs?.length) setRunId(ws.data.runs[0].id);
  }, [ws.data, runId]);

  useEffect(() => {
    if (!runId) return;
    let t: any;
    const poll = async () => {
      try {
        const r = await api(`/api/runs/${runId}`);
        setRun(r);
        if (r.status === "running" || r.status === "queued") t = setTimeout(poll, 1200);
        else ws.reload();
      } catch {}
    };
    poll();
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runId]);

  useEffect(() => {
    logRef.current?.scrollTo({ top: logRef.current.scrollHeight });
  }, [run?.logs?.length]);

  if (ws.loading && !ws.data) return <Skeleton className="h-[600px]" />;
  if (!ws.data) return <Empty title="Workspace not found" />;
  const w = ws.data;
  const inWs = new Set<number>(w.dataset_ids);
  const toggleDs = async (dsId: number) => {
    const ids = inWs.has(dsId) ? w.dataset_ids.filter((x: number) => x !== dsId) : [...w.dataset_ids, dsId];
    ws.setData(await api(`/api/workspaces/${w.id}`, { method: "PATCH", json: { name: w.name, dataset_ids: ids } }));
  };
  const classes = new Set<string>();
  (lic.data || []).filter((d) => inWs.has(d.id)).forEach((d) => Object.keys(d.label_counts).forEach((c) => classes.add(c)));
  const compatible = classes.size >= 2;
  const start = async () => {
    setStarting(true);
    setErr(null);
    try {
      const r = await api(`/api/workspaces/${w.id}/runs`, { method: "POST", json: { base_model: model, ...p } });
      setRunId(r.id);
      setRun(r);
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setStarting(false);
    }
  };
  const tryRaw = async () => {
    const dsId = w.dataset_ids[0];
    const r = await fetch(`${API_BASE}/api/datasets/${dsId}/download`, { headers: { Authorization: `Bearer ${getToken()}` } });
    setDenied(`GET /api/datasets/${dsId}/download → ${r.status}: ${(await r.json()).detail}`);
  };
  const running = run && (run.status === "running" || run.status === "queued");
  const h = run?.history || [];

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <div className="label mb-2"><Link href="/workspace" className="hover:text-fg">Training Room</Link></div>
          <h1 className="text-[22px] font-semibold tracking-tight">{w.name}</h1>
        </div>
        <div className="flex gap-2">
          <Badge tone="ok"><ShieldBan className="h-3 w-3" /> controlled environment</Badge>
        </div>
      </div>

      <div className="grid gap-6 xl:grid-cols-[360px_1fr]">
        <div className="space-y-6">
          <Card>
            <CardHeader title="1 · Datasets" sub="Licensed datasets only" icon={<Box className="h-4 w-4" />} />
            <div className="divide-y divide-line">
              {(lic.data || []).map((d) => (
                <label key={d.id} className="flex cursor-pointer items-start gap-3 px-5 py-2.5 hover:bg-raised/40">
                  <input type="checkbox" className="mt-1" checked={inWs.has(d.id)} onChange={() => toggleDs(d.id)} disabled={!!running} />
                  <div className="min-w-0">
                    <div className="truncate text-[13px] font-medium">{d.title}</div>
                    <div className="text-[11px] text-muted">{num(d.sample_count)} samples · <Link className="link" href={`/marketplace/${d.id}`}>Proof Card</Link></div>
                    <div className="mt-1 flex flex-wrap gap-1">{Object.entries(d.label_counts).map(([k, v]: any) => <Badge key={k}>{k} {v}</Badge>)}</div>
                  </div>
                </label>
              ))}
            </div>
            <div className="border-t border-line px-5 py-3 text-xs">
              {compatible ? <span className="text-ok">Compatible · {classes.size} classes: {Array.from(classes).join(", ")}</span> : <span className="text-warn">Need ≥ 2 labelled classes across selected datasets</span>}
            </div>
          </Card>

          <Card>
            <CardHeader title="2 · Base model" icon={<Box className="h-4 w-4" />} />
            <div className="space-y-2 p-4">
              {(models.data || []).map((m) => (
                <button key={m.id} onClick={() => setModel(m.id)} className={cx("w-full rounded-xl border p-3 text-left transition-colors", model === m.id ? "border-accent/50 bg-accent/5" : "border-line hover:border-faint/60")}>
                  <div className="flex items-center justify-between"><span className="text-sm font-medium">{m.name}</span><span className="text-[11px] text-muted">{m.params}</span></div>
                  <div className="mt-0.5 text-[11px] text-muted">{m.input} · {m.task}</div>
                  <div className="mt-1 text-[11px] leading-relaxed text-faint">{m.desc}</div>
                </button>
              ))}
            </div>
          </Card>

          <Card>
            <CardHeader title="3 · Configuration" icon={<Settings2 className="h-4 w-4" />} />
            <div className="grid grid-cols-2 gap-3 p-4">
              <Field label="Epochs"><input className="input" type="number" min={1} max={40} value={p.epochs} onChange={(e) => setP({ ...p, epochs: +e.target.value })} /></Field>
              <Field label="Learning rate"><input className="input" type="number" step="0.0005" value={p.learning_rate} onChange={(e) => setP({ ...p, learning_rate: +e.target.value })} /></Field>
              <Field label="Batch size"><select className="input" value={p.batch_size} onChange={(e) => setP({ ...p, batch_size: +e.target.value })}>{[8, 16, 32, 64].map((b) => <option key={b}>{b}</option>)}</select></Field>
              <Field label="Validation split"><select className="input" value={p.val_split} onChange={(e) => setP({ ...p, val_split: +e.target.value })}>{[0.15, 0.2, 0.25, 0.3].map((b) => <option key={b} value={b}>{pct(b)}</option>)}</select></Field>
              <label className="col-span-2 flex items-center gap-2 text-xs text-muted"><input type="checkbox" checked={p.augment} onChange={(e) => setP({ ...p, augment: e.target.checked })} /> Augmentation (flip + noise)</label>
            </div>
            <div className="border-t border-line p-4">
              <Button variant="primary" className="w-full" onClick={start} loading={starting} disabled={!!running || !compatible}><Play className="h-4 w-4" /> Start fine-tuning</Button>
              <div className="mt-2"><ErrorNote>{err}</ErrorNote></div>
            </div>
          </Card>
        </div>

        <div className="space-y-6">
          {!run ? (
            <Card className="p-6"><Empty icon={<Terminal className="h-6 w-6" />} title="No runs yet" sub="Pick datasets, a base model and parameters, then start fine-tuning. Training runs for real on the platform's CPU workers." /></Card>
          ) : (
            <>
              <Card>
                <CardHeader title={`4 · Run #${run.id} · ${run.base_model}`} sub={`started ${date(run.created_at)}`} right={<Badge tone={run.status === "completed" ? "ok" : run.status === "failed" ? "bad" : "accent"} dot>{run.status}</Badge>} />
                <div className="space-y-4 p-5">
                  <Progress value={run.progress} tone={run.status === "completed" ? "ok" : "accent"} />
                  <div className="grid gap-6 md:grid-cols-2">
                    <div>
                      <div className="label mb-2">Loss</div>
                      <LineChart series={[{ name: "train", tone: "accent", values: h.map((x: any) => x.train_loss) }, { name: "validation", tone: "warn", values: h.map((x: any) => x.val_loss), dashed: true }]} />
                    </div>
                    <div>
                      <div className="label mb-2">Accuracy</div>
                      <LineChart yMax={1} yFmt={(v) => `${Math.round(v * 100)}%`} series={[{ name: "train", tone: "accent", values: h.map((x: any) => x.train_acc) }, { name: "validation", tone: "ok", values: h.map((x: any) => x.val_acc), dashed: true }]} />
                    </div>
                  </div>
                  <div ref={logRef} className="h-44 overflow-auto rounded-lg border border-line bg-bg p-3 font-mono text-[11px] leading-relaxed text-muted">
                    {(run.logs || []).map((l: string, i: number) => <div key={i} className={l.includes("ERROR") ? "text-bad" : l.includes("WARNING") ? "text-warn" : ""}>{l}</div>)}
                    {running && <div className="animate-pulseDot">▍</div>}
                  </div>
                  {run.error && <ErrorNote>{run.error}</ErrorNote>}
                </div>
              </Card>

              {run.status === "completed" && run.after && (
                <div className="grid gap-6 lg:grid-cols-2">
                  <Card>
                    <CardHeader title="5 · Evaluation" sub="Held-out validation split" />
                    <div className="p-5">
                      <div className="grid grid-cols-2 gap-3">
                        <div className="rounded-xl border border-line p-3">
                          <div className="label">Before</div>
                          <div className="mt-1 text-2xl font-semibold tabular-nums text-muted">{pct(run.before.accuracy)}</div>
                          <div className="text-[11px] text-faint">base model, untrained head · loss {run.before.loss}</div>
                        </div>
                        <div className="rounded-xl border border-ok/30 bg-ok/5 p-3">
                          <div className="label">After</div>
                          <div className="mt-1 text-2xl font-semibold tabular-nums text-ok">{pct(run.after.accuracy)}</div>
                          <div className="text-[11px] text-faint">fine-tuned · loss {run.after.loss}</div>
                        </div>
                      </div>
                      <div className="mt-4">
                        <div className="label mb-2">Per-class accuracy</div>
                        {run.classes.map((c: string, i: number) => (
                          <div key={c} className="mb-1.5 grid grid-cols-[110px_1fr_80px] items-center gap-2 text-xs">
                            <span className="truncate">{c}</span>
                            <div className="relative h-1.5 rounded-full bg-line">
                              <div className="absolute h-1.5 rounded-full bg-faint/60" style={{ width: `${(run.before.per_class?.[i] ?? 0) * 100}%` }} />
                              <div className="absolute h-1.5 rounded-full bg-ok" style={{ width: `${(run.after.per_class?.[i] ?? 0) * 100}%`, opacity: 0.85 }} />
                            </div>
                            <span className="text-right tabular-nums text-muted">{pct(run.before.per_class?.[i] ?? 0)} → {pct(run.after.per_class?.[i] ?? 0)}</span>
                          </div>
                        ))}
                      </div>
                      <div className={cx("mt-4 flex items-start gap-2 rounded-lg border p-3 text-xs", run.after.memorization_risk === "low" ? "border-line text-muted" : "border-warn/30 bg-warn/5 text-warn")}>
                        <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                        <span>Generalization gap {pct(run.after.generalization_gap)} (train {pct(run.after.train_accuracy)} vs val {pct(run.after.accuracy)}) → memorization risk <b>{run.after.memorization_risk}</b>. This is a coarse indicator; exported weights can still leak information about training samples.</span>
                      </div>
                    </div>
                  </Card>
                  <Card>
                    <CardHeader title="6 · Export" sub="Weights + model card with training provenance" />
                    <div className="space-y-3 p-5">
                      <Button variant="primary" className="w-full" onClick={() => download(`/api/runs/${run.id}/weights`, `veridata-run${run.id}-${run.base_model}.pt`)}><Download className="h-4 w-4" /> Download weights (.pt)</Button>
                      <Button className="w-full" onClick={() => download(`/api/runs/${run.id}/card`, `veridata-run${run.id}-model-card.json`)}><FileJson className="h-4 w-4" /> Model card (JSON)</Button>
                      <div className="pt-1">
                        <KV k="Weights sha256" v={<span className="hash">{run.weights_sha256.slice(0, 20)}…</span>} />
                        <KV k="Classes" v={run.classes.join(", ")} />
                        <KV k="Hyperparameters" v={`${run.params.epochs} ep · lr ${run.params.learning_rate} · bs ${run.params.batch_size}`} />
                      </div>
                      <div className="label pt-2">Training provenance</div>
                      {(run.card?.provenance || []).map((pv: any) => (
                        <div key={pv.dataset_id} className="rounded-lg border border-line p-2.5 text-[11px]">
                          <div className="font-medium text-fg">{pv.title}</div>
                          <div className="font-mono text-muted">root {pv.content_root?.slice(0, 18)}… · {pv.samples} samples</div>
                          <div className="text-muted">license: {pv.license_mode}{pv.license_tx && pv.license_tx !== "owner" ? ` · ${pv.license_tx.slice(0, 12)}…` : ""}</div>
                        </div>
                      ))}
                    </div>
                  </Card>
                </div>
              )}

              <Card className="p-5">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <div className="text-sm font-semibold">Original data stays restricted</div>
                    <div className="text-xs text-muted">Licensed media can be used for training here but never exported.</div>
                  </div>
                  <Button size="sm" variant="ghost" onClick={tryRaw} disabled={!w.dataset_ids.length}>Attempt raw dataset export</Button>
                </div>
                {denied && <div className="mt-3 font-mono text-[11px] text-bad">{denied}</div>}
              </Card>
            </>
          )}
          {w.runs.length > 1 && (
            <Card>
              <CardHeader title="Run history" />
              <div className="divide-y divide-line">
                {w.runs.map((r: any) => (
                  <button key={r.id} onClick={() => setRunId(r.id)} className={cx("flex w-full items-center justify-between px-5 py-2.5 text-left text-xs hover:bg-raised/50", r.id === runId && "bg-raised/60")}>
                    <span>#{r.id} · {r.base_model}</span>
                    <span className="text-muted">{r.after ? `${pct(r.before.accuracy)} → ${pct(r.after.accuracy)}` : r.status}</span>
                  </button>
                ))}
              </div>
            </Card>
          )}
          <Note>Training runs in-process on decrypted-in-memory data. This is an MVP isolation boundary (process + API restrictions), not a hardware enclave.</Note>
        </div>
      </div>
    </div>
  );
}
