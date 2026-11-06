"use client";
import { Camera, Droplets, Laptop, Nfc, Radio, ScanLine, Tag, Thermometer, Video, Wifi, WifiOff, X } from "lucide-react";
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
export function LiveStream({ devId, simulated, className, onDown }: { devId: string; simulated?: boolean; className?: string; onDown?: (down: boolean) => void }) {
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
          const wait = Math.max(0, 500 - (now - started));   // cap ~2 fps: software-JPEG CAMs (GC2145) brown out when pushed harder
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
  useEffect(() => { onDown?.(down); }, [down]); // eslint-disable-line react-hooks/exhaustive-deps
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

/** Fallback camera: the laptop/phone camera via getUserMedia (needs localhost or HTTPS). */
export type BrowserCamHandle = { grab: () => Promise<string | null> };

export function BrowserCamera({ camRef, className }: { camRef: { current: BrowserCamHandle | null }; className?: string }) {
  const video = useRef<HTMLVideoElement>(null);
  const [err, setErr] = useState<string | null>(null);
  const [ready, setReady] = useState(false);
  useEffect(() => {
    let stream: MediaStream | null = null;
    let stop = false;
    (async () => {
      try {
        if (!navigator.mediaDevices?.getUserMedia) throw new Error("This browser can't access a camera here (use localhost or HTTPS).");
        stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment", width: { ideal: 1280 }, height: { ideal: 720 } }, audio: false });
        if (stop) { stream.getTracks().forEach((t) => t.stop()); return; }
        if (video.current) { video.current.srcObject = stream; await video.current.play().catch(() => {}); }
        setReady(true);
      } catch (e: any) {
        setErr(e?.name === "NotAllowedError" ? "Camera permission denied: allow camera access in the browser." : e?.message || String(e));
      }
    })();
    camRef.current = {
      grab: async () => {
        const v = video.current;
        if (!v || !v.videoWidth) return null;
        const c = document.createElement("canvas");
        c.width = v.videoWidth;
        c.height = v.videoHeight;
        c.getContext("2d")!.drawImage(v, 0, 0);
        return c.toDataURL("image/jpeg", 0.9);
      },
    };
    return () => {
      stop = true;
      camRef.current = null;
      stream?.getTracks().forEach((t) => t.stop());
    };
  }, [camRef]);
  return (
    <div className={cx("relative aspect-[4/3] overflow-hidden rounded-xl border border-line bg-black", className)}>
      {/* eslint-disable-next-line jsx-a11y/media-has-caption */}
      <video ref={video} playsInline muted className="h-full w-full object-contain" />
      {!ready && <div className="absolute inset-0 grid place-items-center p-4 text-center text-xs text-muted">{err || "Starting this device's camera…"}</div>}
      <div className="absolute left-2 top-2 flex gap-1">
        <Badge tone={ready ? "ok" : "bad"} dot>{ready ? "THIS DEVICE" : "no camera"}</Badge>
        <Badge tone="warn">not the rig camera</Badge>
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

export function CaptureButton({ devId, onCaptured, extra, marked, disabled, getImage, browser }: { devId: string; onCaptured: (s: any) => void; extra?: Record<string, unknown>; marked?: MarkedTag; disabled?: boolean; getImage?: () => Promise<string | null>; browser?: boolean }) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const go = async () => {
    setBusy(true);
    setErr(null);
    try {
      let image_b64: string | undefined;
      if (browser) {
        const img = await getImage?.();
        if (!img) throw new Error("This device's camera isn't ready yet.");
        image_b64 = img;
      }
      onCaptured(await api(`/api/devices/${devId}/capture`, {
        method: "POST",
        json: { attach_rfid: true, rfid_uids: marked ? [marked.uid] : [], ...extra, ...(image_b64 ? { image_b64 } : {}) },
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
        <Camera className="h-4 w-4" /> Capture & sign{browser ? " (this device's camera)" : ""}{marked ? ` · tag ${marked.uid}` : ""}
      </Button>
      <div className="text-[11px] text-faint">{browser
        ? "Takes the photo with this device's camera; sensor readings (if the board is online), RFID and the signature work as usual. The manifest records camera: browser."
        : "Takes a fresh photo, reads the sensor board at the same moment, and signs both together."}</div>
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
  const [source, setSource] = useState<"rig" | "browser">("rig");
  const [camDown, setCamDown] = useState(false);
  const camRef = useRef<BrowserCamHandle | null>(null);
  // latch every tag the reader sees; it stays marked after the tag leaves the field
  useEffect(() => {
    const r = t?.rfid;
    if (r?.uid) setMarked((m) => (m?.uid === r.uid && m.label === r.label ? m : { uid: r.uid, label: r.label, asset_type: r.asset_type, at: Date.now() }));
  }, [t?.rfid?.uid, t?.rfid?.label]);
  const boardOffline = !dev.simulated && t != null && !t.online;
  const browser = source === "browser";
  return (
    <div className="grid gap-4 lg:grid-cols-[1.4fr_1fr]">
      <div className="space-y-2">
        <div className="flex flex-wrap items-center gap-1.5">
          <Button size="sm" variant={browser ? "ghost" : "secondary"} onClick={() => setSource("rig")}><Video className="h-3.5 w-3.5" /> Rig camera</Button>
          <Button size="sm" variant={browser ? "secondary" : "ghost"} onClick={() => setSource("browser")}><Laptop className="h-3.5 w-3.5" /> This device's camera</Button>
        </div>
        {browser ? <BrowserCamera camRef={camRef} /> : <LiveStream devId={dev.id} simulated={dev.simulated} onDown={setCamDown} />}
        {!browser && (camDown || boardOffline) && (
          <div className="flex items-center justify-between gap-2 rounded-lg border border-warn/40 bg-warn/10 px-3 py-2 text-xs">
            <span>{camDown ? "Rig camera is reconnecting." : "Sensor board is offline."} You can capture with this device's camera instead.</span>
            <Button size="sm" onClick={() => setSource("browser")}><Laptop className="h-3.5 w-3.5" /> Use this device's camera</Button>
          </div>
        )}
      </div>
      <div className="space-y-3">
        <SensorTiles t={t} />
        <RfidPanel t={t} marked={marked} onClear={() => setMarked(null)}
          onAssociated={(label) => setMarked((m) => (m ? { ...m, label, asset_type: m.asset_type || "product" } : m))} />
        <CaptureButton devId={dev.id} marked={marked} extra={captureExtra} browser={browser}
          getImage={() => camRef.current?.grab() ?? Promise.resolve(null)}
          disabled={!browser && (boardOffline || camDown)}
          onCaptured={(s) => { onCaptured(s); setMarked(null); }} />
        {!browser && boardOffline && (
          <div className="text-[11px] text-bad">Sensor board offline: rig capture is disabled. Switch to this device's camera to capture without sensor readings.</div>
        )}
        {browser && boardOffline && (
          <div className="text-[11px] text-warn">Sensor board offline: this capture will carry no sensor readings (recorded as sensor_board: offline in the signed manifest).</div>
        )}
      </div>
    </div>
  );
}
