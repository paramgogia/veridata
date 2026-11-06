#!/usr/bin/env node
/**
 * Arkiv testnet query CLI.
 * Runs SQL-like queries against the Rabdi DB-chain.
 *
 * Usage:
 *   node query.mjs "arkiv.schema = str('veridata.request')"
 *   node query.mjs "arkiv.schema = str('veridata.dataset') AND status = str('listed')"
 */
import { createPublicClient } from "@arkiv-network/sdk";
import { rabdi } from "@arkiv-network/sdk/chains";
import { http } from "viem";
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";

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
if (!accessKey) {
  console.error("Error: ARKIV_ACCESS_KEY not found in .env");
  process.exit(1);
}

const client = createPublicClient({
  chain: rabdi({ accessKey }),
  transport: http(),
});

const queryStr = process.argv[2] || "arkiv.schema = str('veridata.request')";

async function main() {
  console.log("------------------------------------------------------------");
  console.log("Arkiv Rabdi Testnet Query");
  console.log("Query:", queryStr);
  console.log("------------------------------------------------------------");

  try {
    const start = Date.now();
    const result = await client.query(queryStr, {
      select: "*",
      limit: 50,
    });
    const elapsed = Date.now() - start;

    console.log(`Matched ${result.entities?.length || 0} entities (${elapsed}ms):\n`);
    for (const e of (result.entities || [])) {
      console.log(`[Entity] Key: ${e.$key || e.key}`);
      console.log(`  Owner:     ${e.$owner || e.owner || 'N/A'}`);
      console.log(`  ExpiresAt: Block #${e.$expiresAt || 'None'}`);
      console.log("  Attributes:");
      const attrs = e.$attributes || e.attributes || {};
      for (const [k, v] of Object.entries(attrs)) {
        console.log(`    ${k}: ${v?.value !== undefined ? v.value : v}`);
      }
      console.log("");
    }
  } catch (err) {
    console.error("Query failed:", err);
    process.exit(1);
  }
}

main();
