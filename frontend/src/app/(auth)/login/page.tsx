"use client";

import { KeyRound } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";

import { AuthFrame } from "@/components/auth-frame";
import { Button, Field, FormError, Input } from "@/components/ui";
import { api } from "@/lib/api";
import type { LoginResult, Me } from "@/lib/types";

type Step = "password" | "mfa" | "sso";

export default function LoginPage() {
  return (
    <Suspense>
      <Login />
    </Suspense>
  );
}

function Login() {
  const router = useRouter();
  const params = useSearchParams();
  const [step, setStep] = useState<Step>("password");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [useRecovery, setUseRecovery] = useState(false);
  const [error, setError] = useState<string | null>(params.get("sso_error") ? ssoMessage(params.get("sso_error")!) : null);
  const [busy, setBusy] = useState(false);

  function done(me: Me) {
    if (me.mfa_setup_required) router.replace("/account/security?setup=mfa");
    else router.replace(me.onboarded ? "/dashboard" : "/onboarding");
  }

  async function run(fn: () => Promise<void>) {
    setBusy(true);
    setError(null);
    try {
      await fn();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Sign in failed");
    } finally {
      setBusy(false);
    }
  }

  const submitPassword = (e: React.FormEvent) => {
    e.preventDefault();
    run(async () => {
      const r = await api<LoginResult>("/auth/login", { method: "POST", json: { email, password } });
      setPassword("");
      if (r.mfa_required) setStep("mfa");
      else if (r.me) done(r.me);
    });
  };

  const submitCode = (e: React.FormEvent) => {
    e.preventDefault();
    run(async () => {
      const r = await api<LoginResult>("/auth/mfa/verify", { method: "POST", json: { code: code.trim() } });
      if (r.me) done(r.me);
    });
  };

  const submitSso = (e: React.FormEvent) => {
    e.preventDefault();
    run(async () => {
      const r = await api<{ redirect_url: string }>("/auth/sso/start", { method: "POST", json: { email } });
      window.location.href = r.redirect_url;
    });
  };

  if (step === "mfa") {
    return (
      <AuthFrame title="Two-step verification" subtitle={useRecovery ? "Enter one of your recovery codes." : "Enter the 6-digit code from your authenticator app."}>
        <form onSubmit={submitCode} className="space-y-4">
          <FormError error={error} />
          <Field label={useRecovery ? "Recovery code" : "Authentication code"}>
            {(id) => (
              <Input
                id={id}
                autoFocus
                required
                autoComplete="one-time-code"
                inputMode={useRecovery ? "text" : "numeric"}
                placeholder={useRecovery ? "XXXXX-XXXXX" : "123456"}
                value={code}
                onChange={(e) => setCode(e.target.value)}
                className="w-full font-mono tracking-widest"
              />
            )}
          </Field>
          <Button type="submit" busy={busy} className="w-full">
            Verify
          </Button>
          <button type="button" onClick={() => { setUseRecovery(!useRecovery); setCode(""); }} className="text-sm font-medium text-ink underline">
            {useRecovery ? "Use authenticator app instead" : "Use a recovery code"}
          </button>
        </form>
      </AuthFrame>
    );
  }

  if (step === "sso") {
    return (
      <AuthFrame title="Sign in with SSO" subtitle="We'll send you to your company's identity provider.">
        <form onSubmit={submitSso} className="space-y-4">
          <FormError error={error} />
          <Field label="Work email">
            {(id) => <Input id={id} type="email" autoComplete="email" required autoFocus value={email} onChange={(e) => setEmail(e.target.value)} />}
          </Field>
          <Button type="submit" busy={busy} className="w-full">
            Continue
          </Button>
          <button type="button" onClick={() => setStep("password")} className="text-sm font-medium text-ink underline">
            Sign in with a password instead
          </button>
        </form>
      </AuthFrame>
    );
  }

  return (
    <AuthFrame title="Sign in" subtitle={<>New here? <Link href="/signup" className="font-medium text-ink underline">Create an account</Link></>}>
      <form onSubmit={submitPassword} className="space-y-4">
        <FormError error={error} />
        <Field label="Work email">
          {(id) => <Input id={id} type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} />}
        </Field>
        <Field label="Password" hint={<Link href="/forgot-password" className="font-medium text-ink underline">Forgot your password?</Link>}>
          {(id) => (
            <Input id={id} type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} />
          )}
        </Field>
        <Button type="submit" busy={busy} className="w-full">
          Sign in
        </Button>
      </form>
      <div className="my-5 flex items-center gap-3 text-xs text-muted">
        <span className="h-px flex-1 bg-line" />
        or
        <span className="h-px flex-1 bg-line" />
      </div>
      <Button variant="secondary" className="w-full" onClick={() => { setError(null); setStep("sso"); }}>
        <KeyRound size={15} aria-hidden />
        Sign in with SSO
      </Button>
    </AuthFrame>
  );
}

function ssoMessage(code: string) {
  return code === "cancelled" ? "Single sign-on was cancelled." : code;
}
