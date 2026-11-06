#!/usr/bin/env node
/**
 * Arkiv writer — called by the Python backend via subprocess.
 * Reads a JSON operation from stdin, writes to Arkiv testnet, outputs result.
 *
 * Usage: echo '{"op":"create","schema":"request","data":{...},"expiry_days":7}' | node writer.mjs
 */
import { createWalletClient, ExpirationTime } from "@arkiv-network/sdk";
import { dec } from "@arkiv-network/sdk/schema";
import { rabdi } from "@arkiv-network/sdk/chains";
import { http } from "viem";
import { privateKeyToAccount } from "viem/accounts";
import * as schemas from "./schemas.mjs";

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

  // Convert numeric fields to dec() values
  const converted = {};
  for (const [k, v] of Object.entries(data)) {
    converted[k] = typeof v === "number" ? dec(String(v)) : v;
  }

  let expires;
  if (expiry_date) {
    expires = ExpirationTime.atDate(new Date(expiry_date * 1000));
  } else {
    expires = ExpirationTime.fromDays(expiry_days || 3650);
  }

  try {
    if (op === "create") {
      const result = await client.createEntity(schemaObj, converted, { expires });
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
