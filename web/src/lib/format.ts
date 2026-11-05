// Amounts from the API are integer gwei (1e-9 ETH).
export const GWEI = 1_000_000_000;

export function eth(gwei: number | null | undefined, digits?: number): string {
  const v = (gwei || 0) / GWEI;
  const d = digits ?? (v === 0 ? 0 : v < 0.01 ? 4 : v < 1 ? 3 : 2);
  return `${v.toLocaleString(undefined, { minimumFractionDigits: Math.min(d, 2), maximumFractionDigits: d })} ETH`;
}
export const ethNum = (gwei: number) => gwei / GWEI;
export const toGwei = (ethStr: string | number) => Math.round(Number(ethStr) * GWEI);
export const toWei = (gwei: number) => BigInt(gwei) * 1_000_000_000n;

export function short(h?: string | null, n = 6) {
  if (!h) return "—";
  return h.length > n * 2 + 2 ? `${h.slice(0, n + 2)}…${h.slice(-4)}` : h;
}

export function ago(ts?: number | null) {
  if (!ts) return "—";
  const s = Date.now() / 1000 - ts;
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
}

export function date(ts?: number | null) {
  if (!ts) return "—";
  return new Date(ts * 1000).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}
export function day(ts?: number | null) {
  if (!ts) return "—";
  return new Date(ts * 1000).toLocaleDateString(undefined, { dateStyle: "medium" });
}

export const num = (n: number) => n.toLocaleString();
export const pct = (x: number) => `${Math.round(x * 100)}%`;
