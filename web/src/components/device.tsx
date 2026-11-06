"use client";
import { Camera, Nfc, Radio, RotateCw, Ruler, ScanLine, Thermometer, Wifi, WifiOff } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { api, url, WS_BASE } from "@/lib/api";
import { Badge, Button, Card, CardHeader, cx, ErrorNote, Field } from "./ui";

export type Telemetry = {
  online: boolean;
  simulated?: boolean;
  cam_online?: boolean;
  distance_cm?: number;
  ir?: boolean;
  servo_deg?: number | null;
  temp_c?: number | null;
  humidity_pct?: number | null;
  rfid?: { uid: string; seen_ms_ago: number; label?: string | null; asset_type?: string | null } | null;
  fw?: string;
  error?: string;
  ts: number;
};

export function useTelemetry(devId: string | null) {
  const [t, setT] = useState<Telemetry | null>(null);
  const [history, setHistory] = useState<number[]>([]);
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
        if (typeof d.distance_cm === "number") setHistory((h) => [...h.slice(-59), d.distance_cm!]);
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
  return { t, history, lastTag };
}

export function LiveStream({ devId, simulated, className }: { devId: string; simulated?: boolean; className?: string }) {
  const [failed, setFailed] = useState(false);
  const [key, setKey] = useState(0);
  return (
    <div className={cx("relative aspect-[4/3] overflow-hidden rounded-xl border border-line bg-black", className)}>
      {!failed ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img key={key} src={url(`/api/devices/${devId}/stream?k=${key}`)} alt="live stream" className="h-full w-full object-contain" onError={() => setFailed(true)} />
      ) : (
        <div className="grid h-full place-items-center text-center text-xs text-muted">
          <div>
            <WifiOff className="mx-auto mb-2 h-5 w-5" />
            Camera stream unreachable
            <div className="mt-2">
              <Button size="sm" onClick={() => { setFailed(false); setKey((k) => k + 1); }}>Retry</Button>
            </div>
          </div>
        </div>
      )}
      <div className="absolute left-2 top-2 flex gap-1">
        <Badge tone={failed ? "bad" : "ok"} dot>
          <span className={failed ? "" : "animate-pulseDot"}>{failed ? "offline" : "LIVE"}</span>
        </Badge>
        {simulated && <Badge tone="warn">SIMULATED</Badge>}
      </div>
    </div>
  );
}

export function SensorTiles({ t, history }: { t: Telemetry | null; history: number[] }) {
  const max = 200;
  return (
    <div className="grid grid-cols-2 gap-2">
      <div className="rounded-xl border border-line bg-raised/40 p-3">
        <div className="label flex items-center gap-1"><Ruler className="h-3 w-3" /> Ultrasonic</div>
        <div className="mt-1 text-lg font-semibold tabular-nums">{t?.distance_cm != null ? `${t.distance_cm.toFixed(1)} cm` : "—"}</div>
        <svg viewBox="0 0 120 28" className="mt-1 h-7 w-full">
          <polyline fill="none" stroke="rgb(var(--accent))" strokeWidth="1.4"
            points={history.map((v, i) => `${(i / 59) * 120},${28 - (Math.min(v, max) / max) * 26 - 1}`).join(" ")} />
        </svg>
      </div>
      <div className="rounded-xl border border-line bg-raised/40 p-3">
        <div className="label flex items-center gap-1"><Radio className="h-3 w-3" /> IR sensor</div>
        <div className={cx("mt-1 text-lg font-semibold", t?.ir ? "text-warn" : "text-muted")}>{t ? (t.ir ? "Object detected" : "Clear") : "—"}</div>
        <div className="mt-1 text-[11px] text-faint">digital obstacle / presence output</div>
      </div>
      {t?.temp_c !== undefined && (
        <div className="rounded-xl border border-line bg-raised/40 p-3">
          <div className="label flex items-center gap-1"><Thermometer className="h-3 w-3" /> Temp / humidity</div>
          <div className="mt-1 text-lg font-semibold tabular-nums">{t.temp_c != null ? `${t.temp_c.toFixed(1)} °C` : "—"}</div>
          <div className="mt-1 text-[11px] text-faint">{t.humidity_pct != null ? `${t.humidity_pct.toFixed(0)} % RH` : "DHT: no reading"}</div>
        </div>
      )}
      <div className="rounded-xl border border-line bg-raised/40 p-3">
        <div className="label flex items-center gap-1"><RotateCw className="h-3 w-3" /> Servo</div>
        <div className="mt-1 text-lg font-semibold tabular-nums">{t?.servo_deg != null ? `${Math.round(t.servo_deg)}°` : "—"}</div>
        <div className="mt-1 text-[11px] text-faint">{t && t.servo_deg == null && !t.simulated ? "not fitted on this rig" : "camera pan angle"}</div>
      </div>
      <div className="rounded-xl border border-line bg-raised/40 p-3">
        <div className="label flex items-center gap-1">{t?.online ? <Wifi className="h-3 w-3" /> : <WifiOff className="h-3 w-3" />} Link</div>
        <div className={cx("mt-1 text-sm font-semibold", t?.online ? "text-ok" : "text-bad")}>{t ? (t.online ? "Main board online" : "Main board offline") : "connecting…"}</div>
        <div className="mt-1 text-[11px] text-faint">{t?.fw ? `fw ${t.fw}` : t?.error || ""}</div>
      </div>
    </div>
  );
}

export function RfidPanel({ t, lastTag, onAssociated }: { t: Telemetry | null; lastTag: Telemetry["rfid"]; onAssociated?: () => void }) {
  const [label, setLabel] = useState("");
  const [type, setType] = useState("product");
  const [busy, setBusy] = useState(false);
  const live = t?.rfid;
  const tag = live || lastTag;
  const save = async () => {
    if (!tag) return;
    setBusy(true);
    try {
      await api("/api/rfid", { method: "POST", json: { uid: tag.uid, label, asset_type: type } });
      setLabel("");
      onAssociated?.();
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="rounded-xl border border-line bg-raised/40 p-3">
      <div className="flex items-center justify-between">
        <div className="label flex items-center gap-1"><Nfc className="h-3 w-3" /> RFID (RC522)</div>
        {live ? <Badge tone="ok" dot>tag in field</Badge> : <Badge>no tag</Badge>}
      </div>
      {tag ? (
        <div className="mt-2">
          <div className="font-mono text-sm">{tag.uid}</div>
          <div className="text-xs text-muted">{tag.label ? `${tag.label} · ${tag.asset_type}` : "Unregistered tag"}{!live && " · last seen"}</div>
          {!tag.label && (
            <div className="mt-2 flex gap-1.5">
              <input className="input h-8 text-xs" placeholder="Associate with object / SKU…" value={label} onChange={(e) => setLabel(e.target.value)} />
              <select className="input h-8 w-28 text-xs" value={type} onChange={(e) => setType(e.target.value)}>
                <option>product</option><option>pallet</option><option>location</option><option>asset</option>
              </select>
              <Button size="sm" onClick={save} loading={busy} disabled={!label}>Save</Button>
            </div>
          )}
        </div>
      ) : (
        <div className="mt-2 text-xs text-muted">Hold a tag near the reader to attach it to the next capture.</div>
      )}
      <div className="mt-2 text-[10px] leading-relaxed text-faint">RFID identifies a tag, not the authenticity or ownership of the object.</div>
    </div>
  );
}

export function ServoControl({ devId, value, disabled }: { devId: string; value?: number; disabled?: boolean }) {
  const [deg, setDeg] = useState(value ?? 90);
  const [err, setErr] = useState<string | null>(null);
  const timer = useRef<any>();
  const touched = useRef(false);
  useEffect(() => {
    if (!touched.current && value != null) setDeg(Math.round(value));
  }, [value]);
  const send = (v: number) => {
    touched.current = true;
    setDeg(v);
    clearTimeout(timer.current);
    timer.current = setTimeout(async () => {
      try {
        setErr(null);
        await api(`/api/devices/${devId}/servo`, { method: "POST", json: { deg: v } });
      } catch (e: any) {
        setErr(e.message);
      }
    }, 120);
  };
  return (
    <div>
      <Field label="Camera angle (servo)" hint={`${deg}°`}>
        <input type="range" min={0} max={180} value={deg} disabled={disabled} onChange={(e) => send(+e.target.value)} className="w-full accent-[rgb(var(--accent))]" />
      </Field>
      <div className="mt-2 flex gap-1.5">
        {[0, 45, 90, 135, 180].map((p) => (
          <Button key={p} size="sm" variant="ghost" disabled={disabled} onClick={() => send(p)}>{p}°</Button>
        ))}
      </div>
      {err && <div className="mt-1"><ErrorNote>{err}</ErrorNote></div>}
    </div>
  );
}

export function CaptureButton({ devId, onCaptured, extra, disabled }: { devId: string; onCaptured: (s: any) => void; extra?: Record<string, unknown>; disabled?: boolean }) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [attach, setAttach] = useState(true);
  const go = async () => {
    setBusy(true);
    setErr(null);
    try {
      onCaptured(await api(`/api/devices/${devId}/capture`, { method: "POST", json: { attach_rfid: attach, ...extra } }));
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="space-y-2">
      <label className="flex items-center gap-2 text-xs text-muted">
        <input type="checkbox" checked={attach} onChange={(e) => setAttach(e.target.checked)} /> Attach RFID tag in field to manifest
      </label>
      <Button variant="primary" className="w-full" onClick={go} loading={busy} disabled={disabled}>
        <Camera className="h-4 w-4" /> Capture & sign
      </Button>
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
  const { t, history, lastTag } = useTelemetry(dev.id);
  return (
    <div className="grid gap-4 lg:grid-cols-[1.4fr_1fr]">
      <div className="space-y-3">
        <LiveStream devId={dev.id} simulated={dev.simulated} />
        <ServoControl devId={dev.id} value={t?.servo_deg ?? undefined} />
      </div>
      <div className="space-y-3">
        <SensorTiles t={t} history={history} />
        <RfidPanel t={t} lastTag={lastTag} />
        <CaptureButton devId={dev.id} onCaptured={onCaptured} extra={captureExtra} />
      </div>
    </div>
  );
}

