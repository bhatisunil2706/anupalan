"use client";

import { createContext, useContext, type ReactNode } from "react";

import type { Me, Member } from "@/lib/types";

export interface Session {
  me: Me;
  members: Member[];
  canWrite: boolean;
  isAdmin: boolean;
  refresh: () => Promise<void>;
}

const SessionCtx = createContext<Session | null>(null);

export function SessionProvider({ value, children }: { value: Session; children: ReactNode }) {
  return <SessionCtx.Provider value={value}>{children}</SessionCtx.Provider>;
}

export function useSession(): Session {
  const s = useContext(SessionCtx);
  if (!s) throw new Error("useSession must be used inside the app shell");
  return s;
}
