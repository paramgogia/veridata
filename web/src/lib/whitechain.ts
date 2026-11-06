"use client";
import { getAccount, signTypedData, switchChain } from "wagmi/actions";
import { API_BASE, ApiError } from "./api";
import { wagmiConfig, whitechainSepolia } from "./wagmi";

/**
 * Buy a dataset license with USDT on Whitechain, gaslessly, through the same x402 endpoint
 * an AI agent uses: GET -> 402 requirements -> sign EIP-3009 (no gas) -> GET with X-PAYMENT.
 */
export async function payWithUsdt(datasetId: number | string) {
  const url = `${API_BASE}/api/x402/datasets/${datasetId}/license`;
  const r1 = await fetch(url);
  if (r1.status !== 402) {
    const j = await r1.json().catch(() => ({}));
    throw new ApiError(r1.status, j.detail || `expected 402, got ${r1.status}`);
  }
  const req = (await r1.json()).accepts[0];
  const ex = req.extra;
  const acct = getAccount(wagmiConfig);
  if (!acct.address) throw new Error("Connect your wallet first");
  // MetaMask only signs EIP-712 for the active chain, so switch (or add) Whitechain. No gas is spent.
  if (acct.chainId !== whitechainSepolia.id) {
    await switchChain(wagmiConfig, { chainId: whitechainSepolia.id });
    // MetaMask's popup can crash if the signature request arrives while it is still
    // rendering the network switch, so give it a moment and confirm the switch took.
    await new Promise((r) => setTimeout(r, 1200));
    if (getAccount(wagmiConfig).chainId !== whitechainSepolia.id)
      throw new Error("Switch MetaMask to Whitechain Sepolia (1874) for this site, then click Pay again.");
  }
  const authorization = {
    from: acct.address,
    to: req.payTo as `0x${string}`,
    value: BigInt(req.maxAmountRequired),
    validAfter: BigInt(ex.validAfter),
    validBefore: BigInt(ex.validBefore),
    nonce: ex.nonce as `0x${string}`,
  };
  const signature = await signTypedData(wagmiConfig, {
    account: acct.address,
    domain: { name: ex.name, version: ex.version, chainId: whitechainSepolia.id, verifyingContract: req.asset },
    types: {
      ReceiveWithAuthorization: [
        { name: "from", type: "address" }, { name: "to", type: "address" }, { name: "value", type: "uint256" },
        { name: "validAfter", type: "uint256" }, { name: "validBefore", type: "uint256" }, { name: "nonce", type: "bytes32" },
      ],
    },
    primaryType: "ReceiveWithAuthorization",
    message: authorization,
  });
  const payment = {
    x402Version: 1, scheme: "exact", network: req.network,
    payload: { signature, salt: ex.salt, authorization: Object.fromEntries(Object.entries(authorization).map(([k, v]) => [k, String(v)])) },
  };
  const r2 = await fetch(url, { headers: { "X-PAYMENT": btoa(JSON.stringify(payment)), "X-Client": "web" } });
  const j = await r2.json().catch(() => ({}));
  if (!r2.ok) throw new ApiError(r2.status, j.detail || r2.statusText);
  return j as { payment: { tx_hash: string; explorer: string; usdt: number; gas_cost_wei: number; gas_paid_by: string }; license: any };
}
