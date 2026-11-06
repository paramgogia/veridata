import { http, createConfig } from "wagmi";
import { sepolia } from "wagmi/chains";
import { defineChain } from "viem";
import { injected } from "@wagmi/core";

/** Whitechain Sepolia: gasless USDT license checkout (VeridataPay). */
export const whitechainSepolia = defineChain({
  id: 1874,
  name: "Whitechain Sepolia",
  nativeCurrency: { name: "WhiteBIT Coin", symbol: "WBT", decimals: 18 },
  rpcUrls: { default: { http: [process.env.NEXT_PUBLIC_WHITECHAIN_RPC || "https://rpc.testnet.whitechain.io"] } },
  blockExplorers: { default: { name: "Whitechain Explorer", url: "https://explorer.testnet.whitechain.io" } },
  testnet: true,
});

export const wagmiConfig = createConfig({
  chains: [sepolia, whitechainSepolia],
  connectors: [injected()],
  transports: {
    [sepolia.id]: http(process.env.NEXT_PUBLIC_SEPOLIA_RPC || "https://ethereum-sepolia-rpc.publicnode.com"),
    [whitechainSepolia.id]: http(process.env.NEXT_PUBLIC_WHITECHAIN_RPC || "https://rpc.testnet.whitechain.io"),
  },
  ssr: true,
});
