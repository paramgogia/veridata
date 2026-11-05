"use client";
import { ExternalLink, KeyRound, Link2 } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { DeviceLive, ManifestView, useTelemetry } from "@/components/device";
import { SampleVerify, TxLink } from "@/components/domain";
import { Badge, Button, Card, CardHeader, Empty, ErrorNote, KV, Note, PageHeader, Skeleton, useApi } from "@/components/ui";
import { api, url } from "@/lib/api";
import { sendVeridata, txErr } from "@/lib/chain";
import { ago, date } from "@/lib/format";
import { useSession } from "@/lib/session";

export default function DeviceDashboard() {
  const { id } = useParams<{ id: string }>();
  const { me, canOnchain, chain } = useSession();
  const { data: dev, loading, reload } = useApi<any>(`/api/devices/${id}`);
  const [last, setLast] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  if (loading && !dev) return <Skeleton className="h-[600px]" />;
  if (!dev) return <Empty title="Device not found" />;
  const mine = me && me.id === dev.owner_id;

  const registerOnchain = async () => {
    setBusy(true);
    setErr(null);
    try {
      const meta = `${dev.kind}|${dev.signing_mode}|${(dev.sensors || []).join(",")}`;
      const tx = await sendVeridata(chain!.contract, "registerDevice", [`0x${dev.chain_device_id}`, `0x${dev.pubkey}`, meta]);
      await api(`/api/devices/${dev.id}/confirm-chain`, { method: "POST", json: { tx_hash: tx } });
      await reload();
    } catch (e: any) {
      setErr(txErr(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow={<Link href="/devices" className="hover:text-fg">Devices</Link>}
        title={dev.name}
        sub={<span className="font-mono text-xs">{dev.id}</span>}
        right={
          <div className="flex flex-wrap gap-1.5">
            {dev.simulated ? <Badge tone="warn">simulated</Badge> : <Badge tone="ok">hardware</Badge>}
            <Badge tone={dev.signing_mode === "device-hardware" ? "ok" : "warn"}>{dev.signing_mode}</Badge>
            {mine && <Button size="sm" href={`/upload?device=${dev.id}`}>Open capture workflow</Button>}
          </div>
        }
      />
      {mine ? (
        <Card className="p-4">
          <DeviceLive dev={dev} onCaptured={(s) => { setLast(s); reload(); }} />
        </Card>
      ) : (
        <ReadOnlyLive dev={dev} />
      )}

      <div className="grid gap-6 lg:grid-cols-[1fr_380px]">
        <Card>
          <CardHeader title="Recent captures" sub="Signed at capture time; media stored encrypted" />
          {last && (
            <div className="grid gap-4 border-b border-line p-4 md:grid-cols-[200px_1fr]">
              <img src={url(last.preview_url)} alt="" className="w-full rounded-lg border border-line" />
              <div className="space-y-3">
                <ManifestView s={last} />
                <SampleVerify sampleId={last.id} />
              </div>
            </div>
          )}
          <div className="grid grid-cols-3 gap-2 p-4 sm:grid-cols-4 md:grid-cols-6">
            {(dev.recent || []).map((s: any) => (
              <button key={s.id} onClick={() => api(`/api/samples/${s.id}`).then(setLast)} className="group relative aspect-square overflow-hidden rounded-lg border border-line bg-raised text-left">
                <img src={url(s.preview_url)} alt="" className="h-full w-full object-cover" />
                <div className="absolute inset-x-0 bottom-0 bg-bg/80 px-1 text-[10px] text-muted">{ago(s.captured_at)}</div>
              </button>
            ))}
            {!dev.recent?.length && <div className="col-span-full text-xs text-muted">No captures yet.</div>}
          </div>
        </Card>

        <Card>
          <CardHeader title="Identity & verification" icon={<KeyRound className="h-4 w-4" />} />
          <div className="px-5 py-3">
            <KV k="Device ID" v={dev.id} mono />
            <KV k="On-chain id" v={`0x${dev.chain_device_id.slice(0, 14)}…`} mono />
            <KV k="Owner" v={dev.owner.slice(0, 10) + "…"} mono />
            <KV k="Key" v={`P-256 · ${dev.key_fp}`} mono />
            <KV k="Signing" v={dev.signing_mode} />
            <KV k="Status" v={dev.status} />
            <KV k="Registered" v={date(dev.created_at)} />
            <KV k="Registration tx" v={dev.registration_mode === "onchain" ? <TxLink hash={dev.registration_tx} urlStr={dev.registration_tx_url} /> : "off-chain registry"} />
          </div>
          <div className="space-y-3 border-t border-line p-5">
            {mine && dev.registration_mode !== "onchain" && (
              <>
                <Button variant="chain" className="w-full" onClick={registerOnchain} loading={busy} disabled={!canOnchain}>
                  <Link2 className="h-4 w-4" /> Register key on Sepolia
                </Button>
                {!canOnchain && <Note>Sign in with a wallet (not a demo persona) and configure the contract to anchor this device on-chain.</Note>}
              </>
            )}
            <ErrorNote>{err}</ErrorNote>
            {dev.signing_mode === "dev-software" && (
              <Note tone="warn">Development mode: manifests are signed by a platform-held software key for this device. Flash <span className="font-mono">firmware/veridata_main</span> to sign on the ESP32 itself.</Note>
            )}
            {!dev.simulated && (
              <div className="space-y-1 text-[11px] text-faint">
                <div className="flex items-center gap-1"><ExternalLink className="h-3 w-3" /> cam: <span className="font-mono">{dev.capture_url || "—"}</span></div>
                <div className="flex items-center gap-1"><ExternalLink className="h-3 w-3" /> board: <span className="font-mono">{dev.control_url || "—"}</span></div>
              </div>
            )}
          </div>
        </Card>
      </div>
    </div>
  );
}

function ReadOnlyLive({ dev }: { dev: any }) {
  const { t } = useTelemetry(dev.id);
  return (
    <Card className="p-4 text-sm text-muted">
      Status: {t ? (t.online ? "online" : "offline") : "…"} · Only the device owner can view the live stream and control capture.
    </Card>
  );
}
