"use client";
import { Cpu, Database, Star } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { DatasetCard } from "@/components/domain";
import { RequireAuth } from "@/components/shell";
import { Badge, Button, Card, CardHeader, Empty, ErrorNote, Field, KV, PageHeader, Skeleton, Stat, useApi } from "@/components/ui";
import { api } from "@/lib/api";
import { ago, date, eth } from "@/lib/format";
import { useSession } from "@/lib/session";

export default function ProfilePage() {
  return (
    <Suspense>
      <ProfileInner />
    </Suspense>
  );
}

function ProfileInner() {
  const sp = useSearchParams();
  const addr = sp.get("address");
  const { me } = useSession();
  if (!addr) return <RequireAuth what="your profile">{me && <Profile address={me.address} editable />}</RequireAuth>;
  return <Profile address={addr} editable={me?.address === addr.toLowerCase()} />;
}

function Profile({ address, editable }: { address: string; editable?: boolean }) {
  const { refresh } = useSession();
  const { data, reload } = useApi<any>(`/api/profile/${address}`, [address]);
  const audit = useApi<any[]>(editable ? "/api/audit?limit=15" : null, [editable]);
  const [edit, setEdit] = useState(false);
  const [f, setF] = useState({ name: "", bio: "", contributor: true, buyer: true });
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    if (data) setF({ name: data.user.name, bio: data.user.bio, contributor: data.user.roles.includes("contributor"), buyer: data.user.roles.includes("buyer") });
  }, [data]);
  if (!data) return <Skeleton className="h-96" />;
  const u = data.user, st = data.stats;
  const save = async () => {
    try {
      await api("/api/me", { method: "PATCH", json: { name: f.name, bio: f.bio, roles: [f.contributor && "contributor", f.buyer && "buyer"].filter(Boolean) } });
      setEdit(false);
      reload();
      refresh();
    } catch (e: any) {
      setErr(e.message);
    }
  };
  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Profile"
        title={<span className="flex items-center gap-3">{u.name}{u.demo && <Badge tone="warn">demo persona</Badge>}</span>}
        sub={<span className="font-mono text-xs">{u.address}</span>}
        right={editable && <Button size="sm" onClick={() => setEdit(!edit)}>{edit ? "Cancel" : "Edit profile"}</Button>}
      />
      {edit ? (
        <Card className="max-w-xl space-y-3 p-5">
          <Field label="Display name"><input className="input" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></Field>
          <Field label="Description"><textarea className="textarea" rows={3} value={f.bio} onChange={(e) => setF({ ...f, bio: e.target.value })} /></Field>
          <div className="flex gap-4 text-xs text-muted">
            <label className="flex items-center gap-2"><input type="checkbox" checked={f.contributor} onChange={(e) => setF({ ...f, contributor: e.target.checked })} /> Contributor</label>
            <label className="flex items-center gap-2"><input type="checkbox" checked={f.buyer} onChange={(e) => setF({ ...f, buyer: e.target.checked })} /> Buyer / model builder</label>
          </div>
          <ErrorNote>{err}</ErrorNote>
          <Button variant="primary" onClick={save}>Save</Button>
          <p className="text-[11px] text-faint">Profile data is stored off-chain. Only your wallet address and device/dataset references appear on-chain.</p>
        </Card>
      ) : (
        <p className="max-w-2xl text-sm text-muted">{u.bio || "No description."}</p>
      )}
      <div className="flex flex-wrap gap-1.5">{u.roles.map((r: string) => <Badge key={r} tone="accent">{r}</Badge>)}<Badge><Star className="h-3 w-3" /> reputation {u.reputation?.toFixed(2)}</Badge><Badge>joined {date(u.created_at)}</Badge></div>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
        <Stat label="Earnings" value={eth(st.earned)} />
        <Stat label="Samples captured" value={st.samples} />
        <Stat label="Accepted" value={st.accepted_submissions} sub={`${st.rejected_submissions} rejected`} />
        <Stat label="Requests fulfilled" value={st.fulfilled_requests} />
        <Stat label="Licenses bought" value={st.licenses_bought} sub={`spent ${eth(st.spent)}`} />
      </div>
      <div className="grid gap-6 lg:grid-cols-[1fr_360px]">
        <div>
          <h2 className="mb-3 text-sm font-semibold">Datasets</h2>
          {data.datasets.length ? <div className="grid gap-3 sm:grid-cols-2">{data.datasets.map((d: any) => <DatasetCard key={d.id} d={d} />)}</div> : <Empty icon={<Database className="h-5 w-5" />} title="No published datasets" />}
        </div>
        <div className="space-y-6">
          <Card>
            <CardHeader title="Registered devices" icon={<Cpu className="h-4 w-4" />} />
            <div className="divide-y divide-line">
              {data.devices.map((d: any) => (
                <Link key={d.id} href={`/devices/${d.id}`} className="block px-5 py-2.5 hover:bg-raised/40">
                  <div className="text-[13px] font-medium">{d.name}</div>
                  <div className="text-[11px] text-muted">{d.id} · {d.signing_mode} · {d.registration_mode}</div>
                </Link>
              ))}
              {!data.devices.length && <div className="px-5 py-4 text-xs text-muted">No devices.</div>}
            </div>
          </Card>
          {editable && (
            <Card>
              <CardHeader title="Audit log" sub="Your security-relevant actions" />
              <div className="divide-y divide-line">
                {(audit.data || []).map((a) => (
                  <div key={a.id} className="px-5 py-2 text-[11px]">
                    <div className="flex justify-between"><span className="font-mono">{a.action}</span><span className="text-faint">{ago(a.created_at)}</span></div>
                    <div className="truncate text-muted">{a.target}</div>
                  </div>
                ))}
                {audit.data?.length === 0 && <div className="px-5 py-4 text-xs text-muted">No events yet.</div>}
              </div>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}
