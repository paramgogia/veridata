import { http, createConfig } from "wagmi";
import { sepolia } from "wagmi/chains";
import { injected } from "@wagmi/core";

export const wagmiConfig = createConfig({
  chains: [sepolia],
  connectors: [injected()],
  transports: { [sepolia.id]: http(process.env.NEXT_PUBLIC_SEPOLIA_RPC || "https://ethereum-sepolia-rpc.publicnode.com") },
  ssr: true,
});
