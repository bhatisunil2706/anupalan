"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { AuthFrame } from "@/components/auth-frame";
import { Loading } from "@/components/ui";
import { api } from "@/lib/api";
import { useUrlToken } from "@/lib/token";

export default function VerifyEmailPage() {
  const token = useUrlToken();
  const [state, setState] = useState<{ ok: boolean; message: string } | null>(null);

  useEffect(() => {
    if (token === undefined) return;
    if (!token) return setState({ ok: false, message: "This link is incomplete." });
    api<{ email: string }>("/auth/email/verify", { method: "POST", json: { token } })
      .then((r) => setState({ ok: true, message: `${r.email} is confirmed.` }))
      .catch((e) => setState({ ok: false, message: e instanceof Error ? e.message : "Something went wrong" }));
  }, [token]);

  if (!state) return <Loading label="Confirming your email" />;
  return (
    <AuthFrame title={state.ok ? "Email confirmed" : "Couldn't confirm your email"}>
      <p className="text-sm text-muted">{state.message}</p>
      <p className="mt-6"><Link href="/dashboard" className="font-medium text-ink underline">Continue to {process.env.NEXT_PUBLIC_APP_NAME ?? "Pramaanly"}</Link></p>
    </AuthFrame>
  );
}
