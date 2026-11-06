"use client";
/**
 * Arkiv DB-chain integration — read-side.
 *
 * The frontend reads public marketplace data (requests, datasets, devices, samples,
 * contributor profiles) directly from Arkiv's Rabdi testnet. No backend roundtrip
 * for public data.
 *
 * Writes happen on the backend (platform wallet → Node.js writer → Arkiv).
 */
import { createPublicClient } from "@arkiv-network/sdk";
import { addr, dec, defineSchema, str } from "@arkiv-network/sdk/schema";
import { rabdi } from "@arkiv-network/sdk/chains";
import { http } from "viem";

// ---- Arkiv public client (read-only) ----

const ARKIV_ACCESS_KEY = process.env.NEXT_PUBLIC_ARKIV_ACCESS_KEY || "";

export const arkivClient = createPublicClient({
  chain: rabdi({ accessKey: ARKIV_ACCESS_KEY }),
  transport: http(),
});

// ---- Schema definitions (must match backend/arkiv/schemas.mjs exactly) ----

export const ContributorSchema = defineSchema("veridata.contributor", {
  wallet: addr().indexed(),
  name: str(),
  bio: str(),
  roles: str().indexed(),
  reputation: dec().indexed(),
  sample_count: dec().indexed(),
  created_at: dec().indexed(),
});

export const DeviceSchema = defineSchema("veridata.device", {
  device_id: str().indexed(),
  owner_wallet: addr().indexed(),
  name: str(),
  kind: str().indexed(),
  pubkey_hex: str(),
  signing_mode: str().indexed(),
  registration_tx: str(),
  registration_mode: str().indexed(),
  status: str().indexed(),
  created_at: dec().indexed(),
});

export const RequestSchema = defineSchema("veridata.request", {
  request_id: dec().indexed(),
  buyer_wallet: addr().indexed(),
  title: str(),
  category: str().indexed(),
  quantity: dec().indexed(),
  accepted: dec().indexed(),
  price_per_sample: dec().indexed(),
  total_escrow: dec().indexed(),
  remaining_escrow: dec().indexed(),
  status: str().indexed(),
  require_device_sig: str().indexed(),
  min_quality: dec().indexed(),
  sensors: str().indexed(),
  spec_hash: str(),
  chain_request_id: dec(),
  fund_tx: str(),
  mode: str().indexed(),
  created_at: dec().indexed(),
});

export const SampleSchema = defineSchema("veridata.sample", {
  sample_id: str().indexed(),
  contributor_wallet: addr().indexed(),
  device_id: str().indexed(),
  media_sha256: str(),
  manifest_hash: str().indexed(),
  storage_root_media: str(),
  storage_root_manifest: str(),
  quality_score: dec().indexed(),
  status: str().indexed(),
  label: str().indexed(),
  categories: str().indexed(),
  sensors: str().indexed(),
  sig_mode: str().indexed(),
  captured_at: dec().indexed(),
  dataset_id: dec().indexed(),
});

export const DatasetSchema = defineSchema("veridata.dataset", {
  dataset_id: dec().indexed(),
  owner_wallet: addr().indexed(),
  title: str(),
  categories: str().indexed(),
  sensor_types: str().indexed(),
  location: str().indexed(),
  quality_score: dec().indexed(),
  sample_count: dec().indexed(),
  price: dec().indexed(),
  content_root: str(),
  chain_dataset_id: dec(),
  publish_tx: str(),
  mode: str().indexed(),
  status: str().indexed(),
  created_at: dec().indexed(),
});

export const SubmissionSchema = defineSchema("veridata.submission", {
  submission_id: dec().indexed(),
  request_id: dec().indexed(),
  sample_id: str().indexed(),
  contributor_wallet: addr().indexed(),
  status: str().indexed(),
  payout: dec().indexed(),
  mode: str().indexed(),
  created_at: dec().indexed(),
});

export const AuditSchema = defineSchema("veridata.audit_event", {
  actor: addr().indexed(),
  action: str().indexed(),
  target: str(),
  mode: str().indexed(),
  created_at: dec().indexed(),
});

// ---- Query helpers ----

/** Query open data requests from Arkiv. */
export async function queryRequests(filters: {
  status?: string;
  category?: string;
}): Promise<any[]> {
  const parts = ["arkiv.schema = str('veridata.request')"];
  if (filters.status) parts.push(`status = str('${filters.status}')`);
  if (filters.category) parts.push(`category = str('${filters.category}')`);

  try {
    const result = await arkivClient.query(parts.join(" AND "), {
      select: "*",
      limit: 100,
    });
    return (result.entities || []).map(entityToRequest);
  } catch (e) {
    console.warn("[arkiv] queryRequests failed, falling back:", e);
    return [];
  }
}

/** Query datasets from Arkiv. */
export async function queryDatasets(filters: {
  category?: string;
  sensor?: string;
  minQuality?: number;
  maxPrice?: number;
  status?: string;
}): Promise<any[]> {
  const parts = ["arkiv.schema = str('veridata.dataset')"];
  if (filters.status) parts.push(`status = str('${filters.status}')`);
  if (filters.category) parts.push(`categories = str('${filters.category}')`);
  if (filters.sensor) parts.push(`sensor_types = str('${filters.sensor}')`);
  if (filters.minQuality) parts.push(`quality_score >= dec('${filters.minQuality}')`);
  if (filters.maxPrice) parts.push(`price <= dec('${filters.maxPrice}')`);

  try {
    const result = await arkivClient.query(parts.join(" AND "), {
      select: "*",
      limit: 100,
    });
    return (result.entities || []).map(entityToDataset);
  } catch (e) {
    console.warn("[arkiv] queryDatasets failed, falling back:", e);
    return [];
  }
}

/** Query devices from Arkiv. */
export async function queryDevices(filters: {
  status?: string;
  owner?: string;
}): Promise<any[]> {
  const parts = ["arkiv.schema = str('veridata.device')"];
  if (filters.status) parts.push(`status = str('${filters.status}')`);
  if (filters.owner) parts.push(`owner_wallet = addr(${filters.owner.toLowerCase()})`);

  try {
    const result = await arkivClient.query(parts.join(" AND "), {
      select: "*",
      limit: 100,
    });
    return (result.entities || []).map(entityToDevice);
  } catch (e) {
    console.warn("[arkiv] queryDevices failed, falling back:", e);
    return [];
  }
}

/** Query contributor profile from Arkiv. */
export async function queryContributor(wallet: string): Promise<any | null> {
  try {
    const result = await arkivClient.query(
      `arkiv.schema = str('veridata.contributor') AND wallet = addr(${wallet.toLowerCase()})`,
      { select: "*", limit: 1 },
    );
    const entities = result.entities || [];
    return entities.length > 0 ? entityToContributor(entities[0]) : null;
  } catch (e) {
    console.warn("[arkiv] queryContributor failed:", e);
    return null;
  }
}

// ---- Entity → view mappers (match the existing API response shapes) ----

function val(attr: any): string {
  return attr?.value ?? attr ?? "";
}

function numVal(attr: any): number {
  const v = val(attr);
  return v ? Number(v) : 0;
}

function entityToRequest(e: any): any {
  const a = e.$attributes || e.attributes || {};
  const total = numVal(a.total_escrow);
  const accepted = numVal(a.accepted);
  const quantity = numVal(a.quantity);
  const pps = numVal(a.price_per_sample);
  const remaining = total - (accepted * pps);
  const deadline = e.$expiresAt ? Number(e.$expiresAt) : 0;
  const daysLeft = deadline ? Math.max(0, (deadline - Date.now() / 1000) / 86400) : 0;
  const buyerWallet = val(a.buyer_wallet) || e.$owner || e.owner || "";
  return {
    id: numVal(a.request_id),
    title: val(a.title),
    category: val(a.category),
    quantity,
    accepted,
    price_per_sample: pps,
    remaining_escrow: Math.max(0, remaining),
    status: val(a.status),
    mode: val(a.mode),
    deadline,
    days_left: Math.round(daysLeft * 10) / 10,
    progress: quantity > 0 ? accepted / quantity : 0,
    created_at: numVal(a.created_at),
    fund_tx: val(a.fund_tx),
    buyer: { address: buyerWallet, name: buyerWallet.slice(0, 10) + "…" },
    _source: "arkiv",
  };
}

function entityToDataset(e: any): any {
  const a = e.$attributes || e.attributes || {};
  const ownerWallet = val(a.owner_wallet) || e.$owner || e.owner || "";
  return {
    id: numVal(a.dataset_id),
    title: val(a.title),
    categories: val(a.categories) ? val(a.categories).split(",") : [],
    sensor_types: val(a.sensor_types) ? val(a.sensor_types).split(",") : [],
    location: val(a.location),
    quality_score: numVal(a.quality_score),
    sample_count: numVal(a.sample_count),
    price: numVal(a.price),
    content_root: val(a.content_root),
    mode: val(a.mode),
    status: val(a.status),
    created_at: numVal(a.created_at),
    owner: { address: ownerWallet, name: ownerWallet.slice(0, 10) + "…" },
    _source: "arkiv",
  };
}

function entityToDevice(e: any): any {
  const a = e.$attributes || e.attributes || {};
  return {
    id: val(a.device_id),
    name: val(a.name),
    kind: val(a.kind),
    signing_mode: val(a.signing_mode),
    registration_mode: val(a.registration_mode),
    status: val(a.status),
    simulated: val(a.kind) === "simulated",
    key_fp: (val(a.pubkey_hex) || "").slice(0, 16) + "…",
    created_at: numVal(a.created_at),
    last_seen: numVal(a.created_at),
    _source: "arkiv",
  };
}

function entityToContributor(e: any): any {
  const a = e.$attributes || e.attributes || {};
  const walletAddr = val(a.wallet) || e.$owner || e.owner || "";
  return {
    address: walletAddr,
    name: val(a.name),
    bio: val(a.bio),
    roles: val(a.roles) ? val(a.roles).split(",") : [],
    reputation: numVal(a.reputation),
    sample_count: numVal(a.sample_count),
    created_at: numVal(a.created_at),
    _source: "arkiv",
  };
}

/** Check if Arkiv is configured (access key present). */
export function arkivEnabled(): boolean {
  return !!ARKIV_ACCESS_KEY;
}
