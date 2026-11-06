#!/usr/bin/env node
/**
 * Arkiv writer — called by the Python backend via subprocess.
 * Reads a JSON operation from stdin, writes to Arkiv testnet, outputs result.
 *
 * Usage: echo '{"op":"create","schema":"request","data":{...},"expiry_days":7}' | node writer.mjs
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

const SCHEMA_MAP = {
  contributor: schemas.Contributor,
  device: schemas.DeviceEntity,
  request: schemas.RequestEntity,
  sample: schemas.SampleEntity,
  dataset: schemas.DatasetEntity,
  submission: schemas.SubmissionEntity,
  audit_event: schemas.AuditEntity,
};

async function main() {
  const input = await new Promise((resolve) => {
    let data = "";
    process.stdin.setEncoding("utf8");
    process.stdin.on("data", (chunk) => (data += chunk));
    process.stdin.on("end", () => resolve(data));
  });

  const { op, schema, data, expiry_days, expiry_date, entity_key } = JSON.parse(input);
  const accessKey = process.env.ARKIV_ACCESS_KEY;
  const privateKey = process.env.ARKIV_PRIVATE_KEY;
  if (!accessKey || !privateKey) {
    console.log(JSON.stringify({ ok: false, error: "ARKIV_ACCESS_KEY or ARKIV_PRIVATE_KEY not set" }));
    process.exit(0);
  }

  const client = createWalletClient({
    chain: rabdi({ accessKey }),
    transport: http(),
    account: privateKeyToAccount(privateKey.startsWith("0x") ? privateKey : `0x${privateKey}`),
  });

  const schemaObj = SCHEMA_MAP[schema];
  if (!schemaObj) {
    console.log(JSON.stringify({ ok: false, error: `unknown schema: ${schema}` }));
    process.exit(0);
  }

  // Convert fields according to schema column types
  const converted = {};
  for (const [k, v] of Object.entries(data)) {
    const col = schemaObj.columns?.[k];
    const colType = col?.type;
    if (colType === "addr") {
      converted[k] = addr(String(v || "0x0000000000000000000000000000000000000000").toLowerCase());
    } else if (colType === "dec") {
      converted[k] = dec(String(v ?? 0));
    } else if (colType === "str") {
      // Arkiv str column max is 128 bytes
      converted[k] = String(v ?? "").slice(0, 128);
    } else {
      converted[k] = typeof v === "number" ? dec(String(v)) : v;
    }
  }

  let expiration;
  if (expiry_date) {
    expiration = ExpirationTime.atDate(new Date(expiry_date * 1000));
  } else if (expiry_days && expiry_days <= 180) {
    expiration = ExpirationTime.fromDays(expiry_days);
  } else {
    expiration = ExpirationTime.max();
  }

  try {
    if (op === "create") {
      const result = await client.createEntity(schemaObj, converted, { expiration });
      console.log(JSON.stringify({ ok: true, entityKey: result.entityKey, txHash: result.txHash }));
    } else if (op === "patch") {
      if (!entity_key) {
        console.log(JSON.stringify({ ok: false, error: "entity_key required for patch" }));
        process.exit(0);
      }
      await client.patchEntity(schemaObj, entity_key, { set: converted });
      console.log(JSON.stringify({ ok: true, entityKey: entity_key }));
    } else {
      console.log(JSON.stringify({ ok: false, error: `unknown op: ${op}` }));
    }
  } catch (e) {
    console.log(JSON.stringify({ ok: false, error: e.message || String(e) }));
  }
}

main();
