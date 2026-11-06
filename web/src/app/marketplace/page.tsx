"use client";
import { Search, SlidersHorizontal } from "lucide-react";
import { useMemo, useState } from "react";
import { DatasetCard } from "@/components/domain";
import { Empty, Field, PageHeader, Skeleton, useApi } from "@/components/ui";
import { toGwei } from "@/lib/format";

const CATS = ["agriculture", "crop-disease", "pest-damage", "insurance", "vehicle-damage", "autonomous-driving", "night", "weather", "retail", "warehouse", "inventory", "occupancy", "ir-sensing", "rfid-tagged"];
const SENSORS = ["camera", "rfid", "ir", "temp_c", "humidity_pct", "ir-grid"];

export default function Marketplace() {
  const [q, setQ] = useState("");
  const [category, setCategory] = useState("");
  const [sensor, setSensor] = useState("");
  const [location, setLocation] = useState("");
  const [minQ, setMinQ] = useState(0);
  const [maxPrice, setMaxPrice] = useState("");
  const [since, setSince] = useState("");
  const [until, setUntil] = useState("");
  const [verified, setVerified] = useState(false);
  const [sort, setSort] = useState("recent");
  const qs = useMemo(() => {
    const p = new URLSearchParams();
    if (q) p.set("q", q);
    if (category) p.set("category", category);
    if (sensor) p.set("sensor", sensor);
    if (location) p.set("location", location);
    if (minQ) p.set("min_quality", String(minQ));
    if (maxPrice) p.set("max_price", String(toGwei(maxPrice)));
    if (since) p.set("since", String(new Date(since).getTime() / 1000));
    if (until) p.set("until", String(new Date(until).getTime() / 1000 + 86400));
    if (verified) p.set("verified", "true");
    p.set("sort", sort);
    return p.toString();
  }, [q, category, sensor, location, minQ, maxPrice, since, until, verified, sort]);
  const { data, loading, error } = useApi<any[]>(`/api/datasets?${qs}`, [qs]);

  return (
    <div>
      <PageHeader eyebrow="Marketplace · Arkiv-indexed" title="Verified datasets" sub="Every dataset is a Merkle root of device-signed capture manifests. Indexed on Arkiv DB-chain and resolvable with SQL-like filters; raw data is never downloadable." />
      <div className="grid gap-6 lg:grid-cols-[240px_1fr]">
        <aside className="space-y-4">
          <div className="relative">
            <Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-faint" />
            <input className="input pl-9" placeholder="Search datasets…" value={q} onChange={(e) => setQ(e.target.value)} />
          </div>
          <div className="card space-y-4 p-4">
            <div className="label flex items-center gap-1.5">
              <SlidersHorizontal className="h-3.5 w-3.5" /> Filters
            </div>
            <Field label="Category">
              <select className="input" value={category} onChange={(e) => setCategory(e.target.value)}>
                <option value="">All categories</option>
                {CATS.map((c) => <option key={c}>{c}</option>)}
              </select>
            </Field>
            <Field label="Sensor type">
              <select className="input" value={sensor} onChange={(e) => setSensor(e.target.value)}>
                <option value="">Any sensor</option>
                {SENSORS.map((c) => <option key={c}>{c}</option>)}
              </select>
            </Field>
            <Field label="Capture location">
              <input className="input" placeholder="e.g. Pune" value={location} onChange={(e) => setLocation(e.target.value)} />
            </Field>
            <Field label="Min quality score" hint={String(minQ)}>
              <input type="range" min={0} max={100} value={minQ} onChange={(e) => setMinQ(+e.target.value)} className="w-full accent-[rgb(var(--accent))]" />
            </Field>
            <Field label="Max price (ETH)">
              <input className="input" inputMode="decimal" placeholder="0.005" value={maxPrice} onChange={(e) => setMaxPrice(e.target.value)} />
            </Field>
            <div className="grid grid-cols-2 gap-2">
              <Field label="From">
                <input type="date" className="input px-2 text-xs" value={since} onChange={(e) => setSince(e.target.value)} />
              </Field>
              <Field label="To">
                <input type="date" className="input px-2 text-xs" value={until} onChange={(e) => setUntil(e.target.value)} />
              </Field>
            </div>
            <label className="flex items-center gap-2 text-xs text-muted">
              <input type="checkbox" checked={verified} onChange={(e) => setVerified(e.target.checked)} /> Content root present / on-chain
            </label>
          </div>
        </aside>
        <div>
          <div className="mb-3 flex items-center justify-between text-xs text-muted">
            <span>{data ? `${data.length} datasets` : " "}</span>
            <select className="input h-8 w-40 text-xs" value={sort} onChange={(e) => setSort(e.target.value)}>
              <option value="recent">Newest</option>
              <option value="quality">Highest quality</option>
              <option value="samples">Most samples</option>
              <option value="price">Lowest price</option>
            </select>
          </div>
          {loading && !data ? (
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">{Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-[300px]" />)}</div>
          ) : error ? (
            <Empty title="Couldn't load datasets" sub={error} />
          ) : data?.length === 0 ? (
            <Empty title="No datasets match these filters" sub="Try widening your search, or post a request so contributors capture what you need." />
          ) : (
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
              {data!.map((d) => <DatasetCard key={d.id} d={d} />)}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
