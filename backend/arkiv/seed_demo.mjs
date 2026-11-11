#!/usr/bin/env node
/**
 * Canonical Arkiv Seeder for VeriData.
 * Seeds initial demo requests, datasets, devices, and contributor profiles
 * onto the Arkiv Rabdi DB-chain testnet.
 *
 * Every record here is DEMO data: mode/registration_mode are "demo-seed" and the
 * transaction-hash fields are empty, because none of these were settled on any chain.
 * Never put made-up transaction hashes in public entities.
 *
 * Usage:
 *   node seed_demo.mjs
 */
import { createWalletClient, ExpirationTime, addr, dec } from "@arkiv-network/sdk";
import { rabdi } from "@arkiv-network/sdk/chains";
import { http } from "viem";
import { privateKeyToAccount } from "viem/accounts";
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";
import * as schemas from "./schemas.mjs";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const envPath = path.resolve(__dirname, "../../.env");
if (fs.existsSync(envPath)) {
  for (const line of fs.readFileSync(envPath, "utf8").split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#") || !trimmed.includes("=")) continue;
    const [k, ...v] = trimmed.split("=");
    if (!process.env[k.trim()]) process.env[k.trim()] = v.join("=").trim();
  }
}

const accessKey = process.env.ARKIV_ACCESS_KEY || process.env.NEXT_PUBLIC_ARKIV_ACCESS_KEY;
const privateKey = process.env.ARKIV_PRIVATE_KEY;

if (!accessKey || !privateKey) {
  console.error("Missing ARKIV_ACCESS_KEY or ARKIV_PRIVATE_KEY in .env");
  process.exit(1);
}

const client = createWalletClient({
  chain: rabdi({ accessKey }),
  transport: http(),
  account: privateKeyToAccount(privateKey.startsWith("0x") ? privateKey : `0x${privateKey}`),
});

const DEMO_REQUESTS = [
  {
    request_id: dec("1"),
    buyer_wallet: addr("0xb0b0000000000000000000000000000000beef01"),
    title: "Rain at Night: Rural Road Driving Clips",
    category: "traffic",
    quantity: dec("2000"),
    accepted: dec("340"),
    price_per_sample: dec("500000"), // gwei (0.0005 ETH)
    total_escrow: dec("1000000000"),
    remaining_escrow: dec("830000000"),
    status: "open",
    require_device_sig: "true",
    min_quality: dec("85"),
    sensors: "camera,ultrasonic,ir",
    spec_hash: "",
    chain_request_id: dec("1"),
    fund_tx: "",
    mode: "demo-seed",
    created_at: dec(String(Math.floor(Date.now() / 1000) - 86400 * 2)),
    days_duration: 14,
  },
  {
    request_id: dec("2"),
    buyer_wallet: addr("0xb0b0000000000000000000000000000000beef01"),
    title: "Crop Disease: Pest Damage Progression on Leaves",
    category: "agriculture",
    quantity: dec("1500"),
    accepted: dec("512"),
    price_per_sample: dec("400000"),
    total_escrow: dec("600000000"),
    remaining_escrow: dec("395200000"),
    status: "open",
    require_device_sig: "true",
    min_quality: dec("80"),
    sensors: "camera,dht temp/humidity",
    spec_hash: "",
    chain_request_id: dec("2"),
    fund_tx: "",
    mode: "demo-seed",
    created_at: dec(String(Math.floor(Date.now() / 1000) - 86400 * 3)),
    days_duration: 30,
  },
  {
    request_id: dec("3"),
    buyer_wallet: addr("0xb0b0000000000000000000000000000000beef01"),
    title: "Warehouse Inventory: RFID-Tagged Pallet Scans",
    category: "retail",
    quantity: dec("800"),
    accepted: dec("210"),
    price_per_sample: dec("600000"),
    total_escrow: dec("480000000"),
    remaining_escrow: dec("354000000"),
    status: "open",
    require_device_sig: "true",
    min_quality: dec("90"),
    sensors: "camera,rc522 rfid",
    spec_hash: "",
    chain_request_id: dec("3"),
    fund_tx: "",
    mode: "demo-seed",
    created_at: dec(String(Math.floor(Date.now() / 1000) - 86400)),
    days_duration: 7,
  },
];

const DEMO_DATASETS = [
  {
    dataset_id: dec("1"),
    owner_wallet: addr("0xa5ba000000000000000000000000000000c0ffee"),
    title: "Monsoon Highway Perception v1 (Night Rain)",
    categories: "traffic,weather",
    sensor_types: "camera,ultrasonic,ir",
    location: "Mumbai-Pune Expressway",
    quality_score: dec("94.2"),
    sample_count: dec("150"),
    price: dec("15000000"), // 0.015 ETH
    content_root: "0x9f8e7d6c5b4a3f2e1d0c9b8a7f6e5d4c3b2a1f0e9d8c7b6a5f4e3d2c1b0a9f8e",
    chain_dataset_id: dec("1"),
    publish_tx: "",
    mode: "demo-seed",
    status: "listed",
    created_at: dec(String(Math.floor(Date.now() / 1000) - 86400 * 5)),
  },
  {
    dataset_id: dec("2"),
    owner_wallet: addr("0xa5ba000000000000000000000000000000c0ffee"),
    title: "Ratnagiri Alphonso Mango Leaf Blight & Microclimate",
    categories: "agriculture",
    sensor_types: "camera,dht temp/humidity,ir",
    location: "Ratnagiri Agri Co-op",
    quality_score: dec("91.8"),
    sample_count: dec("220"),
    price: dec("20000000"),
    content_root: "0x8e7d6c5b4a3f2e1d0c9b8a7f6e5d4c3b2a1f0e9d8c7b6a5f4e3d2c1b0a9f8e7d",
    chain_dataset_id: dec("2"),
    publish_tx: "",
    mode: "demo-seed",
    status: "listed",
    created_at: dec(String(Math.floor(Date.now() / 1000) - 86400 * 4)),
  },
];

const DEMO_DEVICES = [
  {
    device_id: "vd-esp32-cam-01",
    owner_wallet: addr("0xa5ba000000000000000000000000000000c0ffee"),
    name: "Ratnagiri Field Unit #01 (ESP32-CAM)",
    kind: "esp32-cam",
    pubkey_hex: "04a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1b2c3d4",
    signing_mode: "device-hardware",
    registration_tx: "",
    registration_mode: "demo-seed",
    status: "registered",
    created_at: dec(String(Math.floor(Date.now() / 1000) - 86400 * 10)),
  },
  {
    device_id: "vd-sim-rig-02",
    owner_wallet: addr("0xa5ba000000000000000000000000000000c0ffee"),
    name: "Simulated Highway Perception Rig",
    kind: "simulated",
    pubkey_hex: "04f6e5d4c3b2a1f0e9d8c7b6a5f4e3d2c1b0a9f8e7d6c5b4a3f2e1d0c9b8a7f6e5d4c3b2a1f0e9d8c7b6a5f4e3d2c1b0a9f8e7d6c5b4a3f2e1d0c9b8a7f6e5d4c3",
    signing_mode: "dev-software",
    registration_tx: "",
    registration_mode: "local",
    status: "registered",
    created_at: dec(String(Math.floor(Date.now() / 1000) - 86400 * 8)),
  },
];

async function seed() {
  console.log("============================================================");
  console.log("Seeding VeriData Entities to Arkiv Rabdi Testnet");
  console.log("============================================================");

  // 1. Seed Requests
  console.log("\n[1/3] Seeding Buyer Requests (Demands with native TTL)...");
  for (const req of DEMO_REQUESTS) {
    const { days_duration, ...fields } = req;
    const res = await client.createEntity(schemas.RequestEntity, fields, {
      expiration: ExpirationTime.fromDays(days_duration),
    });
    console.log(`  * Created Request '${fields.title}'`);
    console.log(`    Key: ${res.entityKey} | Tx: ${res.txHash}`);
  }

  // 2. Seed Datasets
  console.log("\n[2/3] Seeding Published Datasets...");
  for (const ds of DEMO_DATASETS) {
    const res = await client.createEntity(schemas.DatasetEntity, ds, {
      expiration: ExpirationTime.max(),
    });
    console.log(`  * Created Dataset '${ds.title}'`);
    console.log(`    Key: ${res.entityKey} | Tx: ${res.txHash}`);
  }

  // 3. Seed Devices
  console.log("\n[3/3] Seeding Registered Devices...");
  for (const dev of DEMO_DEVICES) {
    const res = await client.createEntity(schemas.DeviceEntity, dev, {
      expiration: ExpirationTime.max(),
    });
    console.log(`  * Created Device '${dev.name}'`);
    console.log(`    Key: ${res.entityKey} | Tx: ${res.txHash}`);
  }

  console.log("\n============================================================");
  console.log("Arkiv Seeding Finished Successfully!");
  console.log("All entities are live on Rabdi Testnet.");
  console.log("============================================================");
}

seed().catch(console.error);

