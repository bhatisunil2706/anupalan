"use client";

import Link from "next/link";
import { useState } from "react";

import { AuthFrame } from "@/components/auth-frame";
import { Button, Field, FormError, Input, Loading } from "@/components/ui";
import { api } from "@/lib/api";
import { useUrlToken } from "@/lib/token";

export default function ResetPasswordPage() {
  const token = useUrlToken();
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (password !== confirm) return setError("The two passwords don't match");
    setBusy(true);
    setError(null);
    try {
      await api("/auth/password/reset", { method: "POST", json: { token, password } });
      setDone(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setBusy(false);
    }
  }

  if (token === undefined) return <Loading />;
  if (!token) {
    return (
      <AuthFrame title="Link not valid">
        <p className="text-sm text-muted">This reset link is incomplete. <Link href="/forgot-password" className="font-medium text-ink underline">Request a new one</Link>.</p>
      </AuthFrame>
    );
  }
  if (done) {
    return (
      <AuthFrame title="Password changed">
        <p className="text-sm text-muted">You&apos;ve been signed out everywhere. Sign in with your new password.</p>
        <p className="mt-6"><Link href="/login" className="font-medium text-ink underline">Sign in</Link></p>
      </AuthFrame>
    );
  }
  return (
    <AuthFrame title="Choose a new password" subtitle="At least 12 characters. Avoid passwords you use elsewhere.">
      <form onSubmit={submit} className="space-y-4">
        <FormError error={error} />
        <Field label="New password">
          {(id) => <Input id={id} type="password" autoComplete="new-password" minLength={12} required value={password} onChange={(e) => setPassword(e.target.value)} />}
        </Field>
        <Field label="Confirm new password">
          {(id) => <Input id={id} type="password" autoComplete="new-password" minLength={12} required value={confirm} onChange={(e) => setConfirm(e.target.value)} />}
        </Field>
        <Button type="submit" busy={busy} className="w-full">Change password</Button>
      </form>
    </AuthFrame>
  );
}
