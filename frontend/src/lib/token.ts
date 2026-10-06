"use client";

import { useEffect, useState } from "react";

/** Read a one-time token from the URL once, then remove it from the address bar and history. */
export function useUrlToken(name = "token"): string | null | undefined {
  const [token, setToken] = useState<string | null | undefined>(undefined);
  useEffect(() => {
    const url = new URL(window.location.href);
    const t = url.searchParams.get(name);
    if (t) {
      url.searchParams.delete(name);
      window.history.replaceState(null, "", url.pathname + url.search);
    }
    setToken(t);
  }, [name]);
  return token;
}
