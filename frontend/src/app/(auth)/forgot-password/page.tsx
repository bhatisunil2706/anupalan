"use client";

import Link from "next/link";
import { useState } from "react";

import { AuthFrame } from "@/components/auth-frame";
import { Button, Field, FormError, Input } from "@/components/ui";
import { api } from "@/lib/api";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api("/auth/password/forgot", { method: "POST", json: { email } });
      setSent(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setBusy(false);
    }
  }

  if (sent) {
    return (
      <AuthFrame title="Check your email">
        <p className="text-sm leading-relaxed text-muted">
          If an account exists for <span className="font-medium text-text">{email}</span>, we&apos;ve sent a link to reset the password. It
          works once and expires in 30 minutes.
        </p>
        <p className="mt-6 text-sm">
          <Link href="/login" className="font-medium text-ink underline">Back to sign in</Link>
        </p>
      </AuthFrame>
    );
  }

  return (
    <AuthFrame title="Reset your password" subtitle="We'll email you a link to choose a new password.">
      <form onSubmit={submit} className="space-y-4">
        <FormError error={error} />
        <Field label="Work email">
          {(id) => <Input id={id} type="email" autoComplete="email" required autoFocus value={email} onChange={(e) => setEmail(e.target.value)} />}
        </Field>
        <Button type="submit" busy={busy} className="w-full">Send reset link</Button>
        <p className="text-sm"><Link href="/login" className="font-medium text-ink underline">Back to sign in</Link></p>
      </form>
    </AuthFrame>
  );
}
