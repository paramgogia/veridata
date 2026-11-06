"use client";
import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { useAccount, useConnect, useDisconnect } from "wagmi";
import { signMessage } from "wagmi/actions";
import { api, getToken, setToken } from "./api";
import { wagmiConfig } from "./wagmi";

export type Me = {
  id: number;
  address: string;
  name: string;
  bio: string;
  demo: boolean;
  persona: string;
  roles: string[];
  reputation: number;
  balances: { earned: number; spent: number; demo_balance: number };
};

export type ChainCfg = {
  enabled: boolean;
  reachable?: boolean;
  chainId: number;
  contract: string;
  explorer: string;
  uploadFeeWei?: string;
  treasury?: string;
};

type Ctx = {
  me: Me | null;
  loading: boolean;
  chain: ChainCfg | null;
  uploadFee: number;
  refresh: () => Promise<void>;
  loginWallet: () => Promise<void>;
  loginDemo: (p: "contributor" | "buyer") => Promise<void>;
  logout: () => void;
  canOnchain: boolean;
};

const SessionCtx = createContext<Ctx | null>(null);

export function SessionProvider({ children }: { children: React.ReactNode }) {
  const [me, setMe] = useState<Me | null>(null);
  const [loading, setLoading] = useState(true);
  const [chain, setChain] = useState<ChainCfg | null>(null);
  const [uploadFee, setUploadFee] = useState(100000);
  const { address, isConnected } = useAccount();
  const { connectAsync, connectors } = useConnect();
  const { disconnect } = useDisconnect();

  const refresh = useCallback(async () => {
    if (!getToken()) {
      setMe(null);
      setLoading(false);
      return;
    }
    try {
      setMe(await api<Me>("/api/me"));
    } catch {
      setToken(null);
      setMe(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
    api("/api/config")
      .then((c) => {
        setChain(c.chain);
        setUploadFee(c.uploadFee);
      })
      .catch(() => setChain(null));
  }, [refresh]);

  const loginWallet = useCallback(async () => {
    let addr = address;
    if (!isConnected || !addr) {
      const res = await connectAsync({ connector: connectors[0] });
      addr = res.accounts[0];
    }
    const { message } = await api<{ message: string }>(`/api/auth/nonce?address=${addr}`);
    const signature = await signMessage(wagmiConfig, { message, account: addr });
    const r = await api<{ token: string; user: Me }>("/api/auth/verify", { method: "POST", json: { address: addr, signature } });
    setToken(r.token);
    setMe(r.user);
  }, [address, isConnected, connectAsync, connectors]);

  const loginDemo = useCallback(async (p: "contributor" | "buyer") => {
    const r = await api<{ token: string; user: Me }>(`/api/auth/demo?persona=${p}`, { method: "POST" });
    setToken(r.token);
    setMe(r.user);
  }, []);

  const logout = useCallback(() => {
    setToken(null);
    setMe(null);
    disconnect();
  }, [disconnect]);

  const canOnchain = !!(
    me && !me.demo && chain?.enabled && isConnected && address && address.toLowerCase() === me.address
  );

  return (
    <SessionCtx.Provider value={{ me, loading, chain, uploadFee, refresh, loginWallet, loginDemo, logout, canOnchain }}>
      {children}
    </SessionCtx.Provider>
  );
}

export function useSession() {
  const c = useContext(SessionCtx);
  if (!c) throw new Error("SessionProvider missing");
  return c;
}
