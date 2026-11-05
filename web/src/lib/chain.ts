"use client";
import { getAccount, switchChain, waitForTransactionReceipt, writeContract } from "wagmi/actions";
import { sepolia } from "wagmi/chains";
import { VERIDATA_ABI } from "./abi";
import { wagmiConfig } from "./wagmi";

type Fn =
  | "registerDevice"
  | "publishDataset"
  | "purchaseLicense"
  | "createRequest"
  | "closeAndRefund"
  | "depositCredit";

/** Send a Veridata contract call from the connected wallet and wait for 1 confirmation. */
export async function sendVeridata(contract: string, functionName: Fn, args: readonly unknown[], value?: bigint): Promise<`0x${string}`> {
  const acct = getAccount(wagmiConfig);
  if (acct.chainId !== sepolia.id) await switchChain(wagmiConfig, { chainId: sepolia.id });
  const hash = await writeContract(wagmiConfig, {
    address: contract as `0x${string}`,
    abi: VERIDATA_ABI,
    functionName: functionName as any,
    args: args as any,
    value,
    chainId: sepolia.id,
  } as any);
  const rcpt = await waitForTransactionReceipt(wagmiConfig, { hash, chainId: sepolia.id });
  if (rcpt.status !== "success") throw new Error("transaction reverted");
  return hash;
}

export function txErr(e: any): string {
  const m = e?.shortMessage || e?.message || String(e);
  if (/User rejected|denied/i.test(m)) return "Transaction rejected in wallet";
  return m.length > 220 ? m.slice(0, 220) + "…" : m;
}
