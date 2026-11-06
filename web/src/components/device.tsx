"use client";
import { Camera, Droplets, Nfc, Radio, ScanLine, Tag, Thermometer, Wifi, WifiOff, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { api, url, WS_BASE } from "@/lib/api";
import { Badge, Button, cx, ErrorNote } from "./ui";

export type Telemetry = {
  online: boolean;
  simulated?: boolean;
  cam_online?: boolean;
  ir?: boolean;
  temp_c?: number | null;
  humidity_pct?: number | null;
  rfid?: { uid: string; seen_ms_ago: number; label?: string | null; asset_type?: string | null } | null;
  fw?: string;
  error?: string;
  ts: number;
};

export function useTelemetry(devId: string | null) {
  const [t, setT] = useState<Telemetry | null>(null);
  const [lastTag, setLastTag] = useState<Telemetry["rfid"]>(null);
  useEffect(() => {
    if (!devId) return;
    let ws: WebSocket | null = null;
    let stop = false;
    let retry: any;
    const open = () => {
      ws = new WebSocket(`${WS_BASE}/api/devices/${devId}/ws`);
      ws.onmessage = (ev) => {
        const d: Telemetry = JSON.parse(ev.data);
        setT(d);
        if (d.rfid?.uid) setLastTag(d.rfid);
      };
      ws.onclose = () => {
        if (!stop) retry = setTimeout(open, 1500);
      };
    };
    open();
    return () => {
      stop = true;
      clearTimeout(retry);
      ws?.close();
    };
  }, [devId]);
  return { t, lastTag };
}

/** Live preview by polling single frames through the backend. Unlike one long MJPEG request, a
 *  dropped frame or a CAM reboot only fails one poll; the next one retries, so it never freezes. */
export function LiveStream({ devId, simulated, className }: { devId: string; simulated?: boolean; className?: string }) {
  const [src, setSrc] = useState<string | null>(null);
  const [fails, setFails] = useState(0);
  const [fps, setFps] = useState(0);
  useEffect(() => {
    let stop = false;
    let prev: string | null = null;
    let frames = 0;
    let t0 = performance.now();
    const loop = async () => {
      while (!stop) {
        if (document.hidden) { await new Promise((r) => setTimeout(r, 500)); continue; }
        const started = performance.now();
        try {
          const ctl = new AbortController();
          const to = setTimeout(() => ctl.abort(), 8000);
          const r = await fetch(url(`/api/devices/${devId}/frame?t=${Date.now()}`), { cache: "no-store", signal: ctl.signal });
          clearTimeout(to);
          if (!r.ok) throw new Error(String(r.status));
          const blob = await r.blob();
          if (stop) break;
          const next = URL.createObjectURL(blob);
          setSrc(next);
          if (prev) URL.revokeObjectURL(prev);
          prev = next;
          setFails(0);
          frames++;
          const now = performance.now();
          if (now - t0 > 2000) { setFps(Math.round((frames * 10000) / (now - t0)) / 10); frames = 0; t0 = now; }
          const wait = Math.max(0, 200 - (now - started));   // cap ~5 fps; the CAM sets the real pace
          if (wait) await new Promise((r) => setTimeout(r, wait));
        } catch {
          setFails((f) => f + 1);
          await new Promise((r) => setTimeout(r, 1000));   // keep retrying forever
        }
      }
      if (prev) URL.revokeObjectURL(prev);
    };
    loop();
    return () => { stop = true; };
  }, [devId]);
  const down = fails >= 3;
  return (
    <div className={cx("relative aspect-[4/3] overflow-hidden rounded-xl border border-line bg-black", className)}>
      {src ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={src} alt="live camera" className={cx("h-full w-full object-contain", down && "opacity-50")} />
      ) : (
        <div className="grid h-full place-items-center text-xs text-muted">{fails ? "Camera unreachable, retrying…" : "Connecting to camera…"}</div>
      )}
      <div className="absolute left-2 top-2 flex gap-1">
        <Badge tone={down ? "bad" : "ok"} dot>
          <span className={down ? "" : "animate-pulseDot"}>{down ? "reconnecting…" : "LIVE"}</span>
        </Badge>
        {!down && fps > 0 && <Badge>{fps} fps</Badge>}
        {simulated && <Badge tone="warn">SIMULATED</Badge>}
      </div>
    </div>
  );
}

export function SensorTiles({ t }: { t: Telemetry | null }) {
  return (
    <div className="grid grid-cols-2 gap-2">
      <div className="rounded-xl border border-line bg-raised/40 p-3">
        <div className="label flex items-center gap-1"><Radio className="h-3 w-3" /> IR sensor</div>
        <div className={cx("mt-1 text-lg font-semibold", t?.ir ? "text-warn" : "text-muted")}>{t?.online ? (t.ir ? "Object detected" : "Clear") : "—"}</div>
        <div className="mt-1 text-[11px] text-faint">obstacle / presence</div>
      </div>
      <div className="rounded-xl border border-line bg-raised/40 p-3">
        <div className="label flex items-center gap-1"><Thermometer className="h-3 w-3" /> Temperature</div>
        <div className="mt-1 text-lg font-semibold tabular-nums">{t?.temp_c != null ? `${t.temp_c.toFixed(1)} °C` : "—"}</div>
        <div className="mt-1 text-[11px] text-faint">{t?.online && t.temp_c == null ? "DHT: no reading" : "DHT sensor"}</div>
      </div>
      <div className="rounded-xl border border-line bg-raised/40 p-3">
        <div className="label flex items-center gap-1"><Droplets className="h-3 w-3" /> Humidity</div>
        <div className="mt-1 text-lg font-semibold tabular-nums">{t?.humidity_pct != null ? `${t.humidity_pct.toFixed(0)} %` : "—"}</div>
        <div className="mt-1 text-[11px] text-faint">relative humidity</div>
      </div>
      <div className="rounded-xl border border-line bg-raised/40 p-3">
        <div className="label flex items-center gap-1">{t?.online ? <Wifi className="h-3 w-3" /> : <WifiOff className="h-3 w-3" />} Sensor board</div>
        <div className={cx("mt-1 text-sm font-semibold", t?.online ? "text-ok" : "text-bad")}>{t ? (t.online ? "Online" : "Offline") : "connecting…"}</div>
        <div className="mt-1 truncate text-[11px] text-faint">{t?.online ? (t.simulated ? "simulated readings" : `live · fw ${t.fw}`) : t?.error || ""}</div>
      </div>
    </div>
  );
}

export type MarkedTag = { uid: string; label?: string | null; asset_type?: string | null; at: number } | null;

export function RfidPanel({ t, marked, onClear, onAssociated }: { t: Telemetry | null; marked: MarkedTag; onClear: () => void; onAssociated?: (label: string) => void }) {
  const [label, setLabel] = useState("");
  const [type, setType] = useState("product");
  const [busy, setBusy] = useState(false);
  const live = t?.rfid;
  const save = async () => {
    if (!marked) return;
    setBusy(true);
    try {
      await api("/api/rfid", { method: "POST", json: { uid: marked.uid, label, asset_type: type } });
      onAssociated?.(label);
      setLabel("");
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className={cx("rounded-xl border p-3 transition-colors", marked ? "border-ok/60 bg-ok/10" : "border-line bg-raised/40")}>
      <div className="flex items-center justify-between">
        <div className="label flex items-center gap-1"><Nfc className="h-3 w-3" /> RFID (RC522)</div>
        {live ? <Badge tone="ok" dot>tag in field</Badge> : marked ? <Badge tone="ok"><Tag className="h-3 w-3" /> marked</Badge> : <Badge>no tag</Badge>}
      </div>
      {marked ? (
        <div className="mt-2">
          <div className="flex items-center justify-between gap-2">
            <div className="font-mono text-base font-semibold">{marked.uid}</div>
            <button onClick={onClear} className="rounded p-1 text-muted hover:bg-raised hover:text-fg" title="Clear tag"><X className="h-3.5 w-3.5" /></button>
          </div>
          <div className="text-xs text-muted">{marked.label ? `${marked.label} · ${marked.asset_type}` : "Unregistered tag"}</div>
          <div className="mt-1 text-[11px] font-medium text-ok">✓ Will be attached to the next capture</div>
          {!marked.label && (
            <div className="mt-2 flex gap-1.5">
              <input className="input h-8 text-xs" placeholder="Name this tag (object / SKU)…" value={label} onChange={(e) => setLabel(e.target.value)} />
              <select className="input h-8 w-28 text-xs" value={type} onChange={(e) => setType(e.target.value)}>
                <option>product</option><option>pallet</option><option>location</option><option>asset</option>
              </select>
              <Button size="sm" onClick={save} loading={busy} disabled={!label}>Save</Button>
            </div>
          )}
        </div>
      ) : (
        <div className="mt-2 text-xs text-muted">Hold a tag near the reader. It stays marked until you capture or clear it.</div>
      )}
      <div className="mt-2 text-[10px] leading-relaxed text-faint">RFID identifies a tag, not the authenticity or ownership of the object.</div>
    </div>
  );
}

export function CaptureButton({ devId, onCaptured, extra, marked, disabled }: { devId: string; onCaptured: (s: any) => void; extra?: Record<string, unknown>; marked?: MarkedTag; disabled?: boolean }) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const go = async () => {
    setBusy(true);
    setErr(null);
    try {
      onCaptured(await api(`/api/devices/${devId}/capture`, {
        method: "POST",
        json: { attach_rfid: true, rfid_uids: marked ? [marked.uid] : [], ...extra },
      }));
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="space-y-2">
      <Button variant="primary" className="w-full" onClick={go} loading={busy} disabled={disabled}>
        <Camera className="h-4 w-4" /> Capture & sign{marked ? ` · tag ${marked.uid}` : ""}
      </Button>
      <div className="text-[11px] text-faint">Takes a fresh photo, reads the sensor board at the same moment, and signs both together.</div>
      <ErrorNote>{err}</ErrorNote>
    </div>
  );
}

export function ManifestView({ s }: { s: any }) {
  if (!s?.manifest) return <div className="text-xs text-muted">No signed manifest (imported media — no device provenance).</div>;
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap gap-1.5">
        <Badge tone={s.sig_mode === "device-hardware" ? "ok" : "warn"}><ScanLine className="h-3 w-3" /> ES256 · {s.sig_mode}</Badge>
        <Badge>manifest {s.manifest_hash.slice(0, 10)}…</Badge>
      </div>
      <pre className="max-h-64 overflow-auto rounded-lg border border-line bg-bg p-3 font-mono text-[11px] leading-relaxed text-muted">{JSON.stringify(s.manifest, null, 2)}</pre>
      <div className="break-all font-mono text-[10px] text-faint">sig: {s.signature}</div>
    </div>
  );
}

export function DeviceLive({ dev, onCaptured, captureExtra }: { dev: any; onCaptured: (s: any) => void; captureExtra?: Record<string, unknown> }) {
  const { t } = useTelemetry(dev.id);
  const [marked, setMarked] = useState<MarkedTag>(null);
  // latch every tag the reader sees; it stays marked after the tag leaves the field
  useEffect(() => {
    const r = t?.rfid;
    if (r?.uid) setMarked((m) => (m?.uid === r.uid && m.label === r.label ? m : { uid: r.uid, label: r.label, asset_type: r.asset_type, at: Date.now() }));
  }, [t?.rfid?.uid, t?.rfid?.label]);
  return (
    <div className="grid gap-4 lg:grid-cols-[1.4fr_1fr]">
      <LiveStream devId={dev.id} simulated={dev.simulated} />
      <div className="space-y-3">
        <SensorTiles t={t} />
        <RfidPanel t={t} marked={marked} onClear={() => setMarked(null)}
          onAssociated={(label) => setMarked((m) => (m ? { ...m, label, asset_type: m.asset_type || "product" } : m))} />
        <CaptureButton devId={dev.id} marked={marked} extra={captureExtra}
          disabled={!dev.simulated && t != null && !t.online}
          onCaptured={(s) => { onCaptured(s); setMarked(null); }} />
        {!dev.simulated && t != null && !t.online && (
          <div className="text-[11px] text-bad">Sensor board offline: capture is disabled so every sample carries real readings.</div>
        )}
      </div>
    </div>
  );
}
