"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { AuthFrame } from "@/components/auth-frame";
import { Button, Field, FormError, Input } from "@/components/ui";
import { api } from "@/lib/api";
import type { Me } from "@/lib/types";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const me = await api<Me>("/auth/login", { method: "POST", json: { email, password } });
      router.replace(me.onboarded ? "/dashboard" : "/onboarding");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Sign in failed");
      setBusy(false);
    }
  }

  return (
    <AuthFrame title="Sign in" subtitle={<>New here? <Link href="/signup" className="font-medium text-ink underline">Create an account</Link></>}>
      <form onSubmit={submit} className="space-y-4">
        <FormError error={error} />
        <Field label="Work email">
          {(id) => <Input id={id} type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} />}
        </Field>
        <Field label="Password">
          {(id) => (
            <Input id={id} type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} />
          )}
        </Field>
        <Button type="submit" busy={busy} className="w-full">
          Sign in
        </Button>
      </form>
    </AuthFrame>
  );
}
