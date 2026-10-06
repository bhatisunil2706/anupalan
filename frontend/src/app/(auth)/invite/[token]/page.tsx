"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useState } from "react";

import { AuthFrame } from "@/components/auth-frame";
import { Button, Field, FormError, Input, Loading } from "@/components/ui";
import { api, useApi } from "@/lib/api";

interface InviteInfo {
  email: string;
  org_name: string;
  role: string;
  has_account: boolean;
}

export default function InvitePage() {
  const { token } = useParams<{ token: string }>();
  const router = useRouter();
  const { data, error: loadError, loading } = useApi<InviteInfo>(`/auth/invitations/${token}`);
  const [fullName, setFullName] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function accept(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api("/auth/invitations/accept", {
        method: "POST",
        json: data?.has_account ? { token } : { token, full_name: fullName, password },
      });
      router.replace("/dashboard");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not accept the invitation");
      setBusy(false);
    }
  }

  if (loading) return <Loading />;
  if (loadError || !data)
    return (
      <AuthFrame title="Invitation not valid" subtitle="It may have expired or already been used. Ask your admin to send a new one.">
        <Link href="/login" className="text-sm font-medium text-ink underline">Go to sign in</Link>
      </AuthFrame>
    );

  return (
    <AuthFrame title={`Join ${data.org_name}`} subtitle={`You were invited as ${data.role} with ${data.email}.`}>
      <form onSubmit={accept} className="space-y-4">
        <FormError error={error} />
        {data.has_account ? (
          <p className="text-sm text-muted">
            You already have an account. <Link href="/login" className="font-medium text-ink underline">Sign in</Link> as{" "}
            {data.email} first, then open this link again and accept.
          </p>
        ) : (
          <>
            <Field label="Your name">{(id) => <Input id={id} required value={fullName} onChange={(e) => setFullName(e.target.value)} />}</Field>
            <Field label="Choose a password" hint="At least 12 characters. A short phrase of unrelated words works well.">
              {(id) => (
                <Input id={id} type="password" minLength={12} required autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} />
              )}
            </Field>
          </>
        )}
        <Button type="submit" busy={busy} className="w-full">
          Accept invitation
        </Button>
      </form>
    </AuthFrame>
  );
}
