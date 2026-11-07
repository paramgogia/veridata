"use client";
import { Plus } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { DemandCard, useSettlement } from "@/components/domain";
import { SignInModal } from "@/components/shell";
import { Button, Chips, Empty, ErrorNote, Field, Modal, Note, PageHeader, Skeleton, Tabs, useApi } from "@/components/ui";
import { api } from "@/lib/api";
import { sendVeridata, txErr } from "@/lib/chain";
import { eth, toGwei } from "@/lib/format";
import { useSession } from "@/lib/session";

const CATS = ["agriculture", "crop-disease", "pest-damage", "insurance", "vehicle-damage", "autonomous-driving", "retail", "warehouse", "inventory", "occupancy", "ir-sensing", "industrial", "logistics", "cold-chain", "recycling", "presence"];

export default function RequestsPage() {
  return (
    <Suspense>
      <Requests />
    </Suspense>
  );
}

function Requests() {
  const sp = useSearchParams();
  const { me } = useSession();
  const [status, setStatus] = useState<"open" | "filled" | "closed" | "all">("open");
  const [category, setCategory] = useState(sp.get("category") || "");
  const [mine, setMine] = useState(false);
  const { data, loading } = useApi<any[]>(`/api/requests?status=${status}&category=${category}&mine=${mine}&sort=recent`, [status, category, mine, me?.id]);
  const [open, setOpen] = useState(false);
  useEffect(() => {
    if (sp.get("new")) setOpen(true);
  }, [sp]);
  return (
    <div>
      <PageHeader eyebrow="Buyer requests" title="Commission the data you need" sub="Describe exactly what to capture, fund the reward into escrow, and pay only for samples that pass provenance, quality and privacy verification." right={<Button variant="primary" onClick={() => setOpen(true)}><Plus className="h-4 w-4" /> New request</Button>} />
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <Tabs value={status} onChange={setStatus} items={[{ id: "open", label: "Open" }, { id: "filled", label: "Filled" }, { id: "closed", label: "Closed" }, { id: "all", label: "All" }]} />
        <select className="input h-8 w-48 text-xs" value={category} onChange={(e) => setCategory(e.target.value)}>
          <option value="">All categories</option>
          {CATS.map((c) => <option key={c}>{c}</option>)}
        </select>
        {me && <label className="flex items-center gap-2 text-xs text-muted"><input type="checkbox" checked={mine} onChange={(e) => setMine(e.target.checked)} /> My requests</label>}
      </div>
      {loading && !data ? (
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">{Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-48" />)}</div>
      ) : !data?.length ? (
        <Empty title="No requests here" sub="Post a funded request and it will appear on the Demand Board." />
      ) : (
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">{data.map((r) => <DemandCard key={r.id} r={r} />)}</div>
      )}
      <NewRequest open={open} onClose={() => setOpen(false)} />
    </div>
  );
}

function NewRequest({ open, onClose }: { open: boolean; onClose: () => void }) {
  const router = useRouter();
  const { me, refresh } = useSession();
  const { mode, picker, contract } = useSettlement();
  const [f, setF] = useState({
    title: "", description: "", category: "agriculture", quantity: 500, price: "0.0005", days: 14, media_format: "image/jpeg",
    min_resolution: "640x480", location: "", conditions: "", labels: "", min_quality: 55, require_device_signature: true,
  });
  const [sensors, setSensors] = useState<string[]>(["camera"]);
  const [meta, setMeta] = useState<string[]>(["description"]);
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  if (open && !me) return <SignInModal open onClose={onClose} />;
  const total = Number(f.price) * f.quantity;
  const set = (k: string, v: any) => setF((x) => ({ ...x, [k]: v }));
  const submit = async () => {
    setErr(null);
    try {
      setBusy("Creating specification…");
      const r = await api("/api/requests", {
        method: "POST",
        json: {
          title: f.title, description: f.description, category: f.category, quantity: +f.quantity, price_per_sample: toGwei(f.price), deadline_days: +f.days,
          media_format: f.media_format, min_resolution: f.min_resolution, sensors, location: f.location, conditions: f.conditions,
          required_metadata: meta, require_device_signature: f.require_device_signature, min_quality: +f.min_quality,
          labels: f.labels.split(",").map((s) => s.trim()).filter(Boolean),
        },
      });
      let tx = "";
      if (mode === "onchain") {
        setBusy("Deposit escrow in your wallet…");
        tx = await sendVeridata(contract, "createRequest", [`0x${r.spec_hash}`, BigInt(r.price_wei), r.quantity, BigInt(r.deadline_unix)], BigInt(r.deposit_wei));
      }
      setBusy("Confirming escrow…");
      await api(`/api/requests/${r.id}/confirm`, { method: "POST", json: { tx_hash: tx } });
      await refresh();
      router.push(`/requests/${r.id}`);
    } catch (e: any) {
      setErr(txErr(e));
    } finally {
      setBusy(null);
    }
  };
  return (
    <Modal open={open} onClose={onClose} title="New data request" wide>
      <div className="grid gap-4 md:grid-cols-2">
        <div className="space-y-3 md:col-span-2">
          <Field label="Title"><input className="input" value={f.title} onChange={(e) => set("title", e.target.value)} placeholder="500 high-quality images of mango leaves showing visible pest damage" /></Field>
          <Field label="Description"><textarea className="textarea" rows={2} value={f.description} onChange={(e) => set("description", e.target.value)} placeholder="Framing, distance, what to include and exclude…" /></Field>
        </div>
        <Field label="Category"><select className="input" value={f.category} onChange={(e) => set("category", e.target.value)}>{CATS.map((c) => <option key={c}>{c}</option>)}</select></Field>
        <Field label="Accepted labels" hint="comma separated"><input className="input" value={f.labels} onChange={(e) => set("labels", e.target.value)} placeholder="pest_damage" /></Field>
        <Field label="Quantity"><input className="input" type="number" min={1} value={f.quantity} onChange={(e) => set("quantity", +e.target.value)} /></Field>
        <Field label="Price per accepted sample (ETH)"><input className="input" inputMode="decimal" value={f.price} onChange={(e) => set("price", e.target.value)} /></Field>
        <Field label="Format"><select className="input" value={f.media_format} onChange={(e) => set("media_format", e.target.value)}><option>image/jpeg</option><option>video/mjpeg</option><option>sensor/json</option></select></Field>
        <Field label="Min resolution"><input className="input" value={f.min_resolution} onChange={(e) => set("min_resolution", e.target.value)} /></Field>
        <Field label="Location"><input className="input" value={f.location} onChange={(e) => set("location", e.target.value)} placeholder="Konkan belt, India" /></Field>
        <Field label="Capture conditions"><input className="input" value={f.conditions} onChange={(e) => set("conditions", e.target.value)} placeholder="daylight, 10–30 cm" /></Field>
        <Field label="Deadline (days)"><input className="input" type="number" min={1} value={f.days} onChange={(e) => set("days", +e.target.value)} /></Field>
        <Field label="Min quality score"><input className="input" type="number" min={0} max={100} value={f.min_quality} onChange={(e) => set("min_quality", +e.target.value)} /></Field>
        <Field label="Sensor requirements"><Chips options={["camera", "ir", "rfid", "temp_humidity"]} value={sensors} onChange={setSensors} /></Field>
        <Field label="Required metadata"><Chips options={["description", "ir", "rfid", "temp_c", "humidity_pct"]} value={meta} onChange={setMeta} /></Field>
        <label className="flex items-center gap-2 text-xs text-muted md:col-span-2"><input type="checkbox" checked={f.require_device_signature} onChange={(e) => set("require_device_signature", e.target.checked)} /> Require a valid registered-device signature (recommended)</label>
      </div>
      <div className="mt-5 flex flex-wrap items-center justify-between gap-3 border-t border-line pt-4">
        <div>
          <div className="text-xs text-muted">Escrow deposit</div>
          <div className="text-lg font-semibold tabular-nums">{isFinite(total) ? total.toFixed(4) : "—"} ETH</div>
          <div className="mt-1">{picker}</div>
        </div>
        <div className="flex flex-col items-end gap-2">
          <Button variant={mode === "onchain" ? "chain" : "primary"} onClick={submit} loading={!!busy} disabled={!f.title || f.quantity < 1 || !(Number(f.price) > 0)}>
            {mode === "onchain" ? "Fund escrow on Sepolia" : "Fund (demo ledger)"}
          </Button>
          {busy && <span className="text-xs text-muted">{busy}</span>}
        </div>
      </div>
      <div className="mt-3 space-y-2">
        <ErrorNote>{err}</ErrorNote>
        <Note>Unreleased escrow is refundable after the deadline. Each accepted sample pays {eth(toGwei(f.price || 0))} minus a 5% platform fee; a sample hash can only be paid once.</Note>
      </div>
    </Modal>
  );
}
