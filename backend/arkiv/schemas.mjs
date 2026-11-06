import { addr, dec, defineSchema, str } from "@arkiv-network/sdk/schema";

export const Contributor = defineSchema("veridata.contributor", {
  wallet: addr().indexed(),
  name: str(),
  bio: str(),
  roles: str().indexed(),
  reputation: dec().indexed(),
  sample_count: dec().indexed(),
  created_at: dec().indexed(),
});

export const DeviceEntity = defineSchema("veridata.device", {
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

export const RequestEntity = defineSchema("veridata.request", {
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

export const SampleEntity = defineSchema("veridata.sample", {
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

export const DatasetEntity = defineSchema("veridata.dataset", {
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

export const SubmissionEntity = defineSchema("veridata.submission", {
  submission_id: dec().indexed(),
  request_id: dec().indexed(),
  sample_id: str().indexed(),
  contributor_wallet: addr().indexed(),
  status: str().indexed(),
  payout: dec().indexed(),
  mode: str().indexed(),
  created_at: dec().indexed(),
});

export const AuditEntity = defineSchema("veridata.audit_event", {
  actor: addr().indexed(),
  action: str().indexed(),
  target: str(),
  mode: str().indexed(),
  created_at: dec().indexed(),
});
