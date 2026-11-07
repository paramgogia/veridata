"use client";
import { ArrowRight, ArrowUpRight, Github } from "lucide-react";
import Link from "next/link";
import { useApi } from "@/components/ui";
import { num } from "@/lib/format";

const REPO = "https://github.com/paramgogia/veridata";
const SEPOLIA_CONTRACT = "0x513Fb1925A6a0D81960f1D3eb7d7D4C418D8A596";
const WHITECHAIN_CONTRACT = "0x997E7f5B2e1Ea27290a5705F39F1A2e468483FBC";

function Mark({ size = 22 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden>
      <rect x="1" y="1" width="22" height="22" rx="6" stroke="rgb(var(--accent))" strokeWidth="1.5" />
      <path d="M6.5 8l5.5 9 5.5-9" stroke="rgb(var(--fg))" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx="12" cy="7" r="1.4" fill="rgb(var(--ok))" />
    </svg>
  );
}

/** An illustrative capture manifest, laid out the way the app stores it. */
function ManifestCard() {
  const k = "text-muted";
  const s = "text-ok";
  const n = "text-chain";
  return (
    <div id="manifest" className="relative">
      <div className="rounded-2xl border border-line bg-panel">
        <div className="flex items-center justify-between border-b border-line px-4 py-2.5">
          <span className="font-mono text-[11px] text-faint">capture manifest · example</span>
          <span className="flex items-center gap-1.5 font-mono text-[11px] text-ok">
            <span className="h-1.5 w-1.5 animate-pulseDot rounded-full bg-ok" /> ES256 valid
          </span>
        </div>
        <pre className="overflow-x-auto px-4 py-4 font-mono text-[12px] leading-[1.7] text-fg">
{"{\n"}
{"  "}<span className={k}>&quot;device_id&quot;</span>: <span className={s}>&quot;argus-rig-01&quot;</span>,{"\n"}
{"  "}<span className={k}>&quot;captured_at&quot;</span>: <span className={n}>1762412290.418</span>,{"\n"}
{"  "}<span className={k}>&quot;media&quot;</span>: {"{\n"}
{"    "}<span className={k}>&quot;type&quot;</span>: <span className={s}>&quot;video/webm&quot;</span>, <span className={k}>&quot;duration_s&quot;</span>: <span className={n}>5.0</span>,{"\n"}
{"    "}<span className={k}>&quot;sha256&quot;</span>: <span className={s}>&quot;9f2c41…e41a&quot;</span>,{"\n"}
{"    "}<span className={k}>&quot;keyframe_sha256&quot;</span>: <span className={s}>&quot;41b07d…7c2d&quot;</span>{"\n"}
{"  },\n"}
{"  "}<span className={k}>&quot;sensors&quot;</span>: {"{ "}<span className={k}>&quot;ir&quot;</span>: <span className={n}>true</span>, <span className={k}>&quot;temp_c&quot;</span>: <span className={n}>27.4</span>, <span className={k}>&quot;humidity_pct&quot;</span>: <span className={n}>61.0</span>{" },\n"}
{"  "}<span className={k}>&quot;rfid&quot;</span>: [{"{ "}<span className={k}>&quot;uid&quot;</span>: <span className={s}>&quot;04A1B2C3&quot;</span>{" }"}],{"\n"}
{"  "}<span className={k}>&quot;storage&quot;</span>: {"{ "}<span className={k}>&quot;root_0g&quot;</span>: <span className={s}>&quot;0x6d1f…a903&quot;</span>{" },\n"}
{"  "}<span className={k}>&quot;signer&quot;</span>: {"{ "}<span className={k}>&quot;alg&quot;</span>: <span className={s}>&quot;ES256&quot;</span>, <span className={k}>&quot;key_fp&quot;</span>: <span className={s}>&quot;a3f9c1…&quot;</span>{" }\n"}
{"}"}
        </pre>
        <div className="grid grid-cols-3 border-t border-line font-mono text-[10.5px] text-muted">
          <div className="border-r border-line px-4 py-2.5"><div className="text-faint">leaf</div>12 of 40</div>
          <div className="border-r border-line px-4 py-2.5"><div className="text-faint">root</div>Sepolia</div>
          <div className="px-4 py-2.5"><div className="text-faint">blob</div>0G storage</div>
        </div>
      </div>
    </div>
  );
}

const STEPS = [
  { n: "01", t: "Capture", d: "An ESP32-CAM takes a photo or a 5-second clip while the sensor board reads IR presence, temperature, humidity and any RFID tag in range." },
  { n: "02", t: "Sign", d: "Media hash, sensor readings and tag are written into one manifest and signed with the device's registered P-256 key. Edit one pixel and the signature breaks." },
  { n: "03", t: "Verify", d: "Hash, signature and device registration are checked, then an AI pass scores quality and flags faces or near-duplicates before anything is listed." },
  { n: "04", t: "Sell", d: "Samples are bundled into a dataset whose Merkle root is anchored on Ethereum. Buyers pay in ETH, or in USDT on Whitechain without holding gas." },
  { n: "05", t: "Train", d: "Licensed buyers fine-tune inside the Training Room. Raw media is decrypted in memory only and never downloadable; weights ship with a provenance card." },
];

const LAYERS = [
  { chain: "Ethereum Sepolia", what: "Device keys, dataset Merkle roots, request escrow", why: "A permanent public anchor that anyone can check against the files they receive.", href: `https://sepolia.etherscan.io/address/${SEPOLIA_CONTRACT}` },
  { chain: "0G", what: "Encrypted media and manifests, AI checks, TEE fine-tuning", why: "Storage and compute addressed by content root, resolvable without our servers.", href: "https://0g.ai" },
  { chain: "Whitechain", what: "License payments in USDT, relayer-paid gas, x402 for AI agents", why: "A buyer, or a script, can pay with stablecoins without ever holding a gas token.", href: `https://explorer.testnet.whitechain.io/address/${WHITECHAIN_CONTRACT}` },
  { chain: "Arkiv", what: "Public index of devices, requests, datasets and verified samples", why: "Marketplace data is queryable by anyone, not locked in one company's database.", href: "https://arkiv.network" },
];

export default function Landing() {
  const stats = useApi<any>("/api/stats").data;
  const figure = (v: unknown) => (typeof v === "number" ? num(v) : "—");
  return (
    <div className="min-h-screen bg-bg text-fg">
      {/* top bar */}
      <header className="sticky top-0 z-20 border-b border-line bg-bg/85 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-6xl items-center justify-between px-5">
          <Link href="/" className="flex items-center gap-2">
            <Mark />
            <span className="text-[15px] font-semibold tracking-tight">Argus</span>
          </Link>
          <nav className="flex items-center gap-1 text-[13px]">
            <a href="#how" className="hidden rounded-lg px-3 py-1.5 text-muted hover:text-fg sm:block">How it works</a>
            <a href="#stack" className="hidden rounded-lg px-3 py-1.5 text-muted hover:text-fg sm:block">Architecture</a>
            <a href={REPO} target="_blank" rel="noreferrer" className="hidden rounded-lg px-3 py-1.5 text-muted hover:text-fg sm:block">GitHub</a>
            <Link href="/demand" className="ml-2 inline-flex h-8 items-center gap-1.5 rounded-lg bg-fg px-3 font-medium text-bg hover:bg-fg/90">
              Open app <ArrowRight className="h-3.5 w-3.5" />
            </Link>
          </nav>
        </div>
      </header>

      {/* hero */}
      <section className="border-b border-line">
        <div className="mx-auto grid max-w-6xl gap-12 px-5 pb-20 pt-16 lg:grid-cols-[1.05fr_1fr] lg:gap-16 lg:pt-24">
          <div className="flex flex-col justify-center">
            <div className="label mb-5">Hardware-signed training data</div>
            <h1 className="text-[40px] font-semibold leading-[1.05] tracking-[-0.025em] sm:text-[52px]">
              Training data that can prove where it came from.
            </h1>
            <p className="mt-6 max-w-[34rem] text-[16px] leading-relaxed text-muted">
              Argus rigs sign every photo, clip and sensor reading at the moment of capture. Buyers check the signature,
              the Merkle root and the storage proof before they pay. Contributors are paid for every sample that passes.
            </p>
            <div className="mt-8 flex flex-wrap items-center gap-3">
              <Link href="/demand" className="inline-flex h-10 items-center gap-2 rounded-lg bg-fg px-4 text-sm font-medium text-bg hover:bg-fg/90">
                Open the app <ArrowRight className="h-4 w-4" />
              </Link>
              <Link href="/demo/insurance" className="inline-flex h-10 items-center gap-2 rounded-lg border border-line px-4 text-sm text-fg hover:border-faint">
                Try the tamper test
              </Link>
            </div>
            <dl className="mt-12 grid max-w-md grid-cols-3 gap-6 border-t border-line pt-6">
              <div><dt className="text-[11px] text-faint">Signed samples</dt><dd className="mt-1 text-xl font-semibold tabular-nums">{figure(stats?.verified_samples)}</dd></div>
              <div><dt className="text-[11px] text-faint">Datasets</dt><dd className="mt-1 text-xl font-semibold tabular-nums">{figure(stats?.verified_datasets)}</dd></div>
              <div><dt className="text-[11px] text-faint">Devices</dt><dd className="mt-1 text-xl font-semibold tabular-nums">{figure(stats?.active_devices)}</dd></div>
            </dl>
          </div>
          <ManifestCard />
        </div>
      </section>

      {/* problem */}
      <section className="border-b border-line">
        <div className="mx-auto grid max-w-6xl gap-10 px-5 py-20 md:grid-cols-[1fr_1.4fr]">
          <h2 className="text-[26px] font-semibold leading-tight tracking-tight">The problem is not a shortage of images.</h2>
          <div className="space-y-4 text-[15px] leading-relaxed text-muted">
            <p>
              Teams building vision models for farms, warehouses and insurance claims can buy pictures by the million.
              What they cannot buy is certainty: whether a frame was really taken where and when the label says, whether it was
              edited, generated, or scraped from somebody who never agreed to it.
            </p>
            <p>
              Argus moves that question to the moment of capture. The device that took the picture signs it, the readings around it
              ride along in the same signature, and every later step can be checked by anyone holding the file.
            </p>
          </div>
        </div>
      </section>

      {/* how it works */}
      <section id="how" className="border-b border-line">
        <div className="mx-auto max-w-6xl px-5 py-20">
          <div className="mb-10 flex items-end justify-between gap-6">
            <h2 className="text-[26px] font-semibold tracking-tight">From the lens to a licensed model</h2>
            <span className="hidden font-mono text-[11px] text-faint md:block">capture → sign → verify → sell → train</span>
          </div>
          <ol className="grid border-l border-t border-line sm:grid-cols-2 lg:grid-cols-5">
            {STEPS.map((s) => (
              <li key={s.n} className="border-b border-r border-line p-5">
                <div className="font-mono text-[11px] text-accent">{s.n}</div>
                <div className="mt-3 text-[15px] font-semibold">{s.t}</div>
                <p className="mt-2 text-[13px] leading-relaxed text-muted">{s.d}</p>
              </li>
            ))}
          </ol>
        </div>
      </section>

      {/* architecture */}
      <section id="stack" className="border-b border-line">
        <div className="mx-auto max-w-6xl px-5 py-20">
          <h2 className="text-[26px] font-semibold tracking-tight">Where each piece lives</h2>
          <p className="mt-3 max-w-2xl text-[15px] text-muted">
            No single database to trust. Proof, storage, payment and discovery each sit on the network built for that job.
          </p>
          <div className="mt-10 divide-y divide-line border-y border-line">
            {LAYERS.map((l) => (
              <a key={l.chain} href={l.href} target="_blank" rel="noreferrer"
                className="group grid gap-2 py-5 transition-colors hover:bg-panel/60 md:grid-cols-[200px_1fr_1fr] md:gap-8 md:px-2">
                <div className="flex items-center gap-1.5 text-[15px] font-semibold">
                  {l.chain} <ArrowUpRight className="h-3.5 w-3.5 text-faint transition-colors group-hover:text-fg" />
                </div>
                <div className="text-[14px] text-fg">{l.what}</div>
                <div className="text-[14px] text-muted">{l.why}</div>
              </a>
            ))}
          </div>
        </div>
      </section>

      {/* audiences */}
      <section className="border-b border-line">
        <div className="mx-auto grid max-w-6xl md:grid-cols-2">
          <div className="border-line px-5 py-16 md:border-r md:pr-12">
            <div className="label">For contributors</div>
            <h3 className="mt-3 text-[22px] font-semibold tracking-tight">Point a rig at real work. Get paid per sample.</h3>
            <ul className="mt-6 space-y-3 text-[14px] text-muted">
              <li>Buyers post what they need: the label, the sensors, the price per accepted sample.</li>
              <li>Escrowed requests pay out as soon as the buyer accepts, straight to your wallet.</li>
              <li>Your raw footage is never handed over. Buyers train on it, they do not download it.</li>
            </ul>
            <Link href="/upload" className="mt-8 inline-flex items-center gap-1.5 text-sm font-medium text-fg hover:underline underline-offset-4">
              Start capturing <ArrowRight className="h-4 w-4" />
            </Link>
          </div>
          <div className="border-t border-line px-5 py-16 md:border-t-0 md:pl-12">
            <div className="label">For AI teams</div>
            <h3 className="mt-3 text-[22px] font-semibold tracking-tight">Buy data you can audit, train where it stays private.</h3>
            <ul className="mt-6 space-y-3 text-[14px] text-muted">
              <li>Every dataset carries a proof card: signatures, Merkle root, 0G storage roots.</li>
              <li>Pay in USDT with one signature; agents can buy over HTTP 402 with no human in the loop.</li>
              <li>Fine-tuned weights come with a model card that lists exactly which licensed data went in.</li>
            </ul>
            <Link href="/marketplace" className="mt-8 inline-flex items-center gap-1.5 text-sm font-medium text-fg hover:underline underline-offset-4">
              Browse datasets <ArrowRight className="h-4 w-4" />
            </Link>
          </div>
        </div>
      </section>

      {/* honesty note */}
      <section className="border-b border-line">
        <div className="mx-auto max-w-6xl px-5 py-20">
          <div className="grid gap-10 md:grid-cols-[1fr_1.4fr]">
            <h2 className="text-[26px] font-semibold leading-tight tracking-tight">What a signature proves, and what it doesn&apos;t.</h2>
            <div className="grid gap-6 sm:grid-cols-2">
              <div className="rounded-2xl border border-line p-5">
                <div className="font-mono text-[11px] text-ok">proves</div>
                <p className="mt-3 text-[14px] leading-relaxed text-muted">
                  This exact file came from this registered device, at this time, with these sensor readings, and has not been altered since.
                </p>
              </div>
              <div className="rounded-2xl border border-line p-5">
                <div className="font-mono text-[11px] text-warn">does not prove</div>
                <p className="mt-3 text-[14px] leading-relaxed text-muted">
                  That the scene is what the label claims. That is the job of request specs, quality checks and the contributor&apos;s track record.
                </p>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* closing */}
      <section>
        <div className="mx-auto flex max-w-6xl flex-col items-start justify-between gap-6 px-5 py-16 md:flex-row md:items-center">
          <div>
            <h2 className="text-[26px] font-semibold tracking-tight">See it with a real rig.</h2>
            <p className="mt-2 text-[15px] text-muted">
              {stats ? `${figure(stats.open_requests)} open requests on the board right now.` : "Open requests, datasets and the Training Room are one click away."}
            </p>
          </div>
          <Link href="/demand" className="inline-flex h-10 items-center gap-2 rounded-lg bg-fg px-4 text-sm font-medium text-bg hover:bg-fg/90">
            Open the app <ArrowRight className="h-4 w-4" />
          </Link>
        </div>
      </section>

      <footer className="border-t border-line">
        <div className="mx-auto flex max-w-6xl flex-col gap-4 px-5 py-8 text-[12px] text-faint md:flex-row md:items-center md:justify-between">
          <div className="flex items-center gap-2">
            <Mark size={16} /> <span>Argus · built at ETHGlobal Mumbai</span>
          </div>
          <div className="flex flex-wrap items-center gap-x-5 gap-y-2">
            <a className="hover:text-fg" href={`https://sepolia.etherscan.io/address/${SEPOLIA_CONTRACT}`} target="_blank" rel="noreferrer">Sepolia contract</a>
            <a className="hover:text-fg" href={`https://explorer.testnet.whitechain.io/address/${WHITECHAIN_CONTRACT}`} target="_blank" rel="noreferrer">Whitechain contract</a>
            <a className="inline-flex items-center gap-1 hover:text-fg" href={REPO} target="_blank" rel="noreferrer"><Github className="h-3.5 w-3.5" /> Source</a>
          </div>
        </div>
      </footer>
    </div>
  );
}
