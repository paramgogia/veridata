import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const API = process.env.VERIDATA_API_URL || "http://127.0.0.1:8000";

/** One source of truth: expose NEXT_PUBLIC_* values from the repo-root .env (web/.env.local still wins). */
function rootPublicEnv() {
  const out = {};
  try {
    const text = readFileSync(fileURLToPath(new URL("../.env", import.meta.url)), "utf8");
    for (const raw of text.split(/\r?\n/)) {
      const line = raw.trim();
      const eq = line.indexOf("=");
      if (!line.startsWith("NEXT_PUBLIC_") || eq < 0) continue;
      const key = line.slice(0, eq).trim();
      const value = line.slice(eq + 1).trim();
      if (value && !process.env[key]) out[key] = value;
    }
  } catch {
    // no root .env: rely on web/.env.local
  }
  return out;
}

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  env: rootPublicEnv(),
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API}/api/:path*` }];
  },
  webpack: (config) => {
    config.externals.push("pino-pretty", "lokijs", "encoding");
    return config;
  },
};
export default nextConfig;
