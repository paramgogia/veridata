"use client";
import { Cpu, Plus } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Badge, Button, Card, Empty, ErrorNote, Field, Modal, Note, PageHeader, Skeleton, Tabs, useApi } from "@/components/ui";
import { api } from "@/lib/api";
import { ago } from "@/lib/format";
import { useSession } from "@/lib/session";

export default function Devices() {
  const { me } = useSession();
  const [scope, setScope] = useState<"mine" | "all">("mine");
  const { data, loading } = useApi<any[]>(`/api/devices${scope === "mine" ? "?mine=true" : ""}`, [scope, me?.id]);
  const [open, setOpen] = useState(false);
  return (
    <div>
      <PageHeader
        eyebrow="Hardware"
        title="Devices"
        sub="Registered capture rigs: ESP32-CAM + ultrasonic + IR + RFID + servo. Each device has its own P-256 signing key; user identity and device identity are kept separate."
        right={<Button variant="primary" onClick={() => setOpen(true)} disabled={!me}><Plus className="h-4 w-4" /> Register device</Button>}
      />
      <div className="mb-4"><Tabs value={scope} onChange={setScope} items={[{ id: "mine", label: "My devices" }, { id: "all", label: "Network" }]} /></div>
      {loading && !data ? (
        <div className="grid gap-3 md:grid-cols-3">{Array.from({ length: 3 }).map((_, i) => <Skeleton key={i} className="h-36" />)}</div>
      ) : !data?.length ? (
        <Empty icon={<Cpu className="h-6 w-6" />} title={me ? "No devices yet" : "Sign in to see your devices"} sub="Register your ESP32 rig, or a simulated device if hardware isn't at hand." action={me && <Button onClick={() => setOpen(true)}>Register device</Button>} />
      ) : (
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {data.map((d) => (
            <Link key={d.id} href={`/devices/${d.id}`} className="group">
              <Card className="h-full p-4 transition-colors group-hover:border-faint/60">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <div className="truncate text-sm font-semibold">{d.name}</div>
                    <div className="font-mono text-[11px] text-muted">{d.id}</div>
                  </div>
                  {d.simulated ? <Badge tone="warn">simulated</Badge> : <Badge tone="ok">hardware</Badge>}
                </div>
                <div className="mt-3 flex flex-wrap gap-1.5">
                  <Badge tone={d.signing_mode === "device-hardware" ? "ok" : "warn"}>{d.signing_mode}</Badge>
                  <Badge tone={d.registration_mode === "onchain" ? "chain" : "neutral"}>{d.registration_mode === "onchain" ? "registered on Sepolia" : "registry (off-chain)"}</Badge>
                  {d.status !== "registered" && <Badge tone="bad">{d.status}</Badge>}
                </div>
                <div className="mt-3 text-[11px] text-faint">key fp {d.key_fp} · seen {ago(d.last_seen)}</div>
              </Card>
            </Link>
          ))}
        </div>
      )}
      <RegisterModal open={open} onClose={() => setOpen(false)} />
    </div>
  );
}

function RegisterModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const router = useRouter();
  const defaults = useApi<any>(open ? "/api/devices/defaults" : null, [open]);
  const [kind, setKind] = useState<"hardware" | "simulated">("hardware");
  const [name, setName] = useState("");
  const [cap, setCap] = useState<string | null>(null);
  const [str, setStr] = useState<string | null>(null);
  const [ctl, setCtl] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const d = defaults.data || {};
  const submit = async () => {
    setBusy(true);
    setErr(null);
    try {
      const dev = await api("/api/devices", {
        method: "POST",
        json: { name: name || (kind === "simulated" ? "Simulated rig" : "ESP32 capture rig"), simulated: kind === "simulated",
          capture_url: cap ?? d.capture_url ?? "", stream_url: str ?? d.stream_url ?? "", control_url: ctl ?? d.control_url ?? "" },
      });
      router.push(`/devices/${dev.id}`);
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  };
  return (
      <Modal open={open} onClose={onClose} title="Register a capture device">
        <div className="space-y-4">
          <Tabs value={kind} onChange={setKind} items={[{ id: "hardware", label: "ESP32 hardware" }, { id: "simulated", label: "Simulated" }]} />
          <Field label="Device name"><input className="input" value={name} onChange={(e) => setName(e.target.value)} placeholder="Aisle 4 shelf monitor" /></Field>
          {kind === "hardware" ? (
            <>
              <Field label="ESP32-CAM still URL" hint="CameraWebServer /capture"><input className="input font-mono text-xs" value={cap ?? d.capture_url ?? ""} onChange={(e) => setCap(e.target.value)} /></Field>
              <Field label="ESP32-CAM MJPEG stream" hint=":81/stream"><input className="input font-mono text-xs" value={str ?? d.stream_url ?? ""} onChange={(e) => setStr(e.target.value)} /></Field>
              <Field label="Main board API" hint="veridata_main firmware"><input className="input font-mono text-xs" value={ctl ?? d.control_url ?? ""} onChange={(e) => setCtl(e.target.value)} /></Field>
              <Note>If the main board answers <span className="font-mono">/pubkey</span>, its on-device P-256 key is used (<b>device-hardware</b> signing). Otherwise a <b>dev-software</b> key is generated and held encrypted by the platform — clearly labelled on every manifest.</Note>
            </>
          ) : (
            <Note tone="warn">Simulated devices generate synthetic frames and sensor readings for demos. Everything they produce is labelled SIMULATED.</Note>
          )}
          <ErrorNote>{err}</ErrorNote>
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={onClose}>Cancel</Button>
            <Button variant="primary" onClick={submit} loading={busy}>Register</Button>
          </div>
        </div>
      </Modal>
  );
}
