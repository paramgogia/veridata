"use client";
import { FlipHorizontal2, ShieldCheck, ShieldX } from "lucide-react";
import { useState } from "react";
import { Badge, Button, Card, CardHeader, CheckRow, cx, Note, PageHeader, Skeleton, useApi } from "@/components/ui";
import { api, url } from "@/lib/api";

export default function InsuranceDemo() {
  const { data } = useApi<any[]>("/api/demo/insurance");
  const [res, setRes] = useState<Record<string, any>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const [tamper, setTamper] = useState<any>(null);

  const verify = async (id: string) => {
    setBusy(id);
    try {
      const r = await api(`/api/samples/${id}/verify`, { method: "POST" });
      setRes((x) => ({ ...x, [id]: r }));
    } finally {
      setBusy(null);
    }
  };
  const verifyAll = async () => {
    for (const s of data || []) await verify(s.id);
  };
  const doTamper = async () => {
    const target = (data || []).find((s) => res[s.id]?.valid) || data?.[0];
    if (!target) return;
    setBusy("tamper");
    try {
      setTamper({ sample: target, ...(await api(`/api/demo/tamper/${target.id}`, { method: "POST" })) });
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Use case · Insurance evidence"
        title="Provenance & tamper detection"
        sub="An insurer receives six damage photos for its fraud model. Three come from a registered capture device with valid signatures; three lack valid provenance. Verification is real: decrypt, re-hash, check the ES256 signature against the registered device key."
        right={<><Button onClick={verifyAll} loading={!!busy && busy !== "tamper"}>Verify all six</Button><Button variant="primary" onClick={doTamper} loading={busy === "tamper"} disabled={!data?.length}><FlipHorizontal2 className="h-4 w-4" /> Modify one pixel</Button></>}
      />
      {!data ? (
        <div className="grid gap-3 md:grid-cols-3">{Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-72" />)}</div>
      ) : (
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {data.map((s, i) => {
            const r = res[s.id];
            return (
              <Card key={s.id} className={cx("overflow-hidden transition-colors", r && (r.valid ? "border-ok/40" : "border-bad/40"))}>
                <div className="relative aspect-[4/3] bg-raised">
                  <img src={url(s.preview_url)} alt="" className="h-full w-full object-cover" />
                  <div className="absolute left-2 top-2"><Badge>Photo {i + 1}</Badge></div>
                  {r && (
                    <div className="absolute right-2 top-2">
                      {r.valid ? <Badge tone="ok"><ShieldCheck className="h-3 w-3" /> accepted</Badge> : <Badge tone="bad"><ShieldX className="h-3 w-3" /> rejected</Badge>}
                    </div>
                  )}
                </div>
                <div className="p-3.5">
                  <div className="text-[13px] font-medium">{s.description}</div>
                  <div className="mt-1 font-mono text-[11px] text-muted">sha256 {s.media_sha256.slice(0, 24)}…</div>
                  {!r ? (
                    <Button size="sm" className="mt-3" onClick={() => verify(s.id)} loading={busy === s.id}>Verify</Button>
                  ) : (
                    <div className="mt-2 border-t border-line pt-1">{r.steps.map((x: any) => <CheckRow key={x.name} ok={x.ok} name={x.name} detail={x.detail} />)}</div>
                  )}
                </div>
              </Card>
            );
          })}
        </div>
      )}
      {tamper && (
        <Card className="animate-in">
          <CardHeader title={`Tamper test · ${tamper.sample.description}`} sub={`Pixel (${tamper.pixel.x},${tamper.pixel.y}) changed from rgb(${tamper.pixel.from.join(",")}) to rgb(${tamper.pixel.to.join(",")}) — invisible to the eye.`} />
          <div className="grid gap-6 p-5 md:grid-cols-2">
            <div>
              <div className="mb-2 flex items-center justify-between"><span className="label">Original (stored)</span><Badge tone={tamper.original.valid ? "ok" : "bad"}>{tamper.original.valid ? "valid" : "invalid"}</Badge></div>
              {tamper.original.steps.map((x: any) => <CheckRow key={x.name} ok={x.ok} name={x.name} detail={x.detail} />)}
            </div>
            <div>
              <div className="mb-2 flex items-center justify-between"><span className="label">One pixel modified</span><Badge tone={tamper.tampered.valid ? "ok" : "bad"}>{tamper.tampered.valid ? "valid" : "hash mismatch"}</Badge></div>
              {tamper.tampered.steps.map((x: any) => <CheckRow key={x.name} ok={x.ok} name={x.name} detail={x.detail} />)}
            </div>
          </div>
        </Card>
      )}
      <Note>What this proves: the image bytes are unchanged since a registered device signed them. What it does not prove: that the damage is real or wasn’t staged — a registered camera can still photograph a fake scene. Provenance narrows fraud; it doesn’t eliminate it.</Note>
    </div>
  );
}
