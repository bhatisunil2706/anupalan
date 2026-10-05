"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { AuthFrame } from "@/components/auth-frame";
import { Button, Field, FormError, Input } from "@/components/ui";
import { api } from "@/lib/api";

export default function SignupPage() {
  const router = useRouter();
  const [form, setForm] = useState({ full_name: "", email: "", org_name: "", password: "" });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) => setForm({ ...form, [k]: e.target.value });

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api("/auth/signup", { method: "POST", json: form });
      router.replace("/onboarding");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Sign up failed");
      setBusy(false);
    }
  }

  return (
    <AuthFrame
      title="Create your workspace"
      subtitle={<>Already have an account? <Link href="/login" className="font-medium text-ink underline">Sign in</Link></>}
    >
      <form onSubmit={submit} className="space-y-4">
        <FormError error={error} />
        <Field label="Your name">{(id) => <Input id={id} autoComplete="name" required value={form.full_name} onChange={set("full_name")} />}</Field>
        <Field label="Work email">
          {(id) => <Input id={id} type="email" autoComplete="email" required value={form.email} onChange={set("email")} />}
        </Field>
        <Field label="Company name">
          {(id) => <Input id={id} autoComplete="organization" required value={form.org_name} onChange={set("org_name")} />}
        </Field>
        <Field label="Password" hint="At least 10 characters">
          {(id) => (
            <Input id={id} type="password" autoComplete="new-password" minLength={10} required value={form.password} onChange={set("password")} />
          )}
        </Field>
        <Button type="submit" busy={busy} className="w-full">
          Create workspace
        </Button>
      </form>
    </AuthFrame>
  );
}
