"use client";

import { Copy, Download, Laptop, ShieldCheck } from "lucide-react";
import { useEffect, useState } from "react";

import { useSession } from "@/components/session";
import { Badge, Button, Drawer, Field, FormError, Input, LoadError, Loading, PageHeader, Panel, tbl, useToast } from "@/components/ui";
import { api, useApi } from "@/lib/api";
import { fmtDateTime } from "@/lib/format";

interface MfaStatus {
  enabled: boolean;
  enabled_at: string | null;
  recovery_codes_remaining: number;
}

interface SessionRow {
  id: string;
  current: boolean;
  ip: string;
  user_agent: string;
  created_at: string;
  last_seen_at: string;
  auth_method: string;
}

export default function AccountSecurityPage() {
  const { me } = useSession();
  return (
    <>
      <PageHeader title="Account security" description={`Signed in as ${me.user.email}${me.auth_method === "sso" ? " through single sign-on" : ""}.`} />
      <div className="grid max-w-3xl gap-6">
        <TwoStep />
        {me.auth_method !== "sso" && <ChangePassword />}
        <Sessions />
      </div>
    </>
  );
}

function deviceName(ua: string) {
  const browser = /Edg\//.test(ua) ? "Edge" : /Chrome\//.test(ua) ? "Chrome" : /Firefox\//.test(ua) ? "Firefox" : /Safari\//.test(ua) ? "Safari" : "Browser";
  const os = /Windows/.test(ua) ? "Windows" : /Mac OS X/.test(ua) ? "macOS" : /Android/.test(ua) ? "Android" : /iPhone|iPad/.test(ua) ? "iOS" : /Linux/.test(ua) ? "Linux" : "";
  return os ? `${browser} on ${os}` : browser;
}

// ------------------------------------------------------------------ two-step verification

function TwoStep() {
  const { me, refresh } = useSession();
  const toast = useToast();
  const status = useApi<MfaStatus>("/auth/mfa/status");
  const [setup, setSetup] = useState<{ secret: string; qr: string } | null>(null);
  const [code, setCode] = useState("");
  const [codes, setCodes] = useState<string[] | null>(null);
  const [confirm, setConfirm] = useState<"disable" | "regenerate" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (me.mfa_setup_required && status.data && !status.data.enabled && !setup) start();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [me.mfa_setup_required, status.data]);

  async function start() {
    setError(null);
    try {
      setSetup(await api<{ secret: string; qr: string }>("/auth/mfa/setup", { method: "POST" }));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed");
    }
  }

  async function enable(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const r = await api<{ recovery_codes: string[] }>("/auth/mfa/enable", { method: "POST", json: { code: code.trim() } });
      setCodes(r.recovery_codes);
      setSetup(null);
      setCode("");
      status.reload();
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed");
    } finally {
      setBusy(false);
    }
  }

  if (status.loading && !status.data) return <Panel title="Two-step verification"><Loading /></Panel>;
  if (status.error || !status.data) return <LoadError error={status.error ?? "Could not load"} retry={status.reload} />;
  const s = status.data;

  return (
    <Panel
      title="Two-step verification"
      actions={s.enabled ? <Badge tone="pass"><ShieldCheck size={12} aria-hidden /> On</Badge> : <Badge tone="warn">Off</Badge>}
    >
      <FormError error={error} />
      {codes && <RecoveryCodes codes={codes} onDone={() => setCodes(null)} />}
      {!codes && s.enabled && (
        <div className="space-y-3 text-sm">
          <p>
            You&apos;ll be asked for a code from your authenticator app when you sign in. {s.recovery_codes_remaining} of 10 recovery codes left.
          </p>
          <div className="flex flex-wrap gap-2">
            <Button variant="secondary" size="sm" onClick={() => setConfirm("regenerate")}>New recovery codes</Button>
            <Button variant="danger" size="sm" onClick={() => setConfirm("disable")}>Turn off</Button>
          </div>
        </div>
      )}
      {!codes && !s.enabled && !setup && (
        <div className="space-y-3 text-sm">
          <p>Protect your account with a code from an authenticator app such as Google Authenticator, Microsoft Authenticator or 1Password.</p>
          <Button onClick={start}>Set up two-step verification</Button>
        </div>
      )}
      {!codes && setup && (
        <form onSubmit={enable} className="grid gap-5 sm:grid-cols-[180px_1fr]">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={setup.qr} alt="QR code for your authenticator app" className="h-[180px] w-[180px] rounded border border-line bg-white p-2" />
          <div className="space-y-3 text-sm">
            <p>1. Scan the QR code with your authenticator app.</p>
            <p className="text-muted">
              Can&apos;t scan? Enter this key: <code className="break-all rounded bg-paper px-1 font-mono text-xs text-text">{setup.secret}</code>
            </p>
            <p>2. Enter the 6-digit code it shows.</p>
            <Field label="Code">
              {(id) => <Input id={id} inputMode="numeric" autoComplete="one-time-code" required value={code} onChange={(e) => setCode(e.target.value)} className="w-40 font-mono tracking-widest" />}
            </Field>
            <Button type="submit" busy={busy}>Turn on</Button>
          </div>
        </form>
      )}
      <ConfirmDrawer
        mode={confirm}
        onClose={() => setConfirm(null)}
        onDone={async (r) => {
          setConfirm(null);
          if (r?.recovery_codes) setCodes(r.recovery_codes);
          else toast("Two-step verification turned off");
          status.reload();
          await refresh();
        }}
      />
    </Panel>
  );
}

function RecoveryCodes({ codes, onDone }: { codes: string[]; onDone: () => void }) {
  const toast = useToast();
  const text = codes.join("\n");
  return (
    <div className="space-y-3 text-sm">
      <p className="font-medium">Save your recovery codes</p>
      <p className="text-muted">Each code works once if you lose your phone. They won&apos;t be shown again.</p>
      <ul className="grid grid-cols-2 gap-2 rounded-md border border-line bg-paper p-3 font-mono text-sm">
        {codes.map((c) => <li key={c}>{c}</li>)}
      </ul>
      <div className="flex flex-wrap gap-2">
        <Button variant="secondary" size="sm" onClick={() => navigator.clipboard.writeText(text).then(() => toast("Copied"))}>
          <Copy size={14} aria-hidden /> Copy
        </Button>
        <Button
          variant="secondary"
          size="sm"
          onClick={() => {
            const url = URL.createObjectURL(new Blob([text + "\n"], { type: "text/plain" }));
            const a = Object.assign(document.createElement("a"), { href: url, download: "recovery-codes.txt" });
            a.click();
            URL.revokeObjectURL(url);
          }}
        >
          <Download size={14} aria-hidden /> Download
        </Button>
        <Button size="sm" onClick={onDone}>I&apos;ve saved them</Button>
      </div>
    </div>
  );
}

function ConfirmDrawer({
  mode,
  onClose,
  onDone,
}: {
  mode: "disable" | "regenerate" | null;
  onClose: () => void;
  onDone: (r: { recovery_codes?: string[] } | undefined) => void;
}) {
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    setPassword("");
    setCode("");
    setError(null);
  }, [mode]);

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      const r = await api<{ recovery_codes?: string[] } | undefined>(mode === "disable" ? "/auth/mfa/disable" : "/auth/mfa/recovery-codes", {
        method: "POST",
        json: { password, code: code.trim() },
      });
      onDone(r);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Drawer
      open={mode !== null}
      onClose={onClose}
      title={mode === "disable" ? "Turn off two-step verification" : "Create new recovery codes"}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
          <Button variant={mode === "disable" ? "danger" : "primary"} busy={busy} onClick={submit}>Confirm</Button>
        </>
      }
    >
      <FormError error={error} />
      <p className="text-sm text-muted">
        {mode === "disable" ? "Your account will be protected by your password only." : "Your old recovery codes will stop working."} Confirm it&apos;s you.
      </p>
      <Field label="Password">{(id) => <Input id={id} type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} />}</Field>
      <Field label="Authenticator code">{(id) => <Input id={id} inputMode="numeric" autoComplete="one-time-code" value={code} onChange={(e) => setCode(e.target.value)} className="w-40 font-mono" />}</Field>
    </Drawer>
  );
}

// ------------------------------------------------------------------ password

function ChangePassword() {
  const toast = useToast();
  const [form, setForm] = useState({ current_password: "", new_password: "", confirm: "" });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (form.new_password !== form.confirm) return setError("The new passwords don't match");
    setBusy(true);
    setError(null);
    try {
      await api("/auth/password/change", { method: "POST", json: { current_password: form.current_password, new_password: form.new_password } });
      setForm({ current_password: "", new_password: "", confirm: "" });
      toast("Password changed. Other devices were signed out.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Panel title="Password">
      <form onSubmit={submit} className="max-w-sm space-y-4">
        <FormError error={error} />
        <Field label="Current password">{(id) => <Input id={id} type="password" autoComplete="current-password" required value={form.current_password} onChange={(e) => setForm({ ...form, current_password: e.target.value })} />}</Field>
        <Field label="New password" hint="At least 12 characters. Changing it signs out your other devices.">
          {(id) => <Input id={id} type="password" autoComplete="new-password" minLength={12} required value={form.new_password} onChange={(e) => setForm({ ...form, new_password: e.target.value })} />}
        </Field>
        <Field label="Confirm new password">{(id) => <Input id={id} type="password" autoComplete="new-password" minLength={12} required value={form.confirm} onChange={(e) => setForm({ ...form, confirm: e.target.value })} />}</Field>
        <Button type="submit" busy={busy}>Change password</Button>
      </form>
    </Panel>
  );
}

// ------------------------------------------------------------------ sessions

function Sessions() {
  const toast = useToast();
  const { data, error, loading, reload } = useApi<SessionRow[]>("/auth/sessions");

  async function revoke(id: string) {
    await api(`/auth/sessions/${id}`, { method: "DELETE" });
    toast("Signed out that device");
    reload();
  }
  async function revokeOthers() {
    const r = await api<{ revoked: number }>("/auth/sessions/revoke-others", { method: "POST" });
    toast(`Signed out ${r.revoked} other ${r.revoked === 1 ? "device" : "devices"}`);
    reload();
  }

  return (
    <Panel
      title="Where you're signed in"
      flush
      actions={data && data.length > 1 ? <Button variant="secondary" size="sm" onClick={revokeOthers}>Sign out other devices</Button> : undefined}
    >
      {loading && !data ? (
        <Loading />
      ) : error || !data ? (
        <div className="p-4"><LoadError error={error ?? "Could not load"} retry={reload} /></div>
      ) : (
        <div className={tbl.wrap}>
          <table className={tbl.table}>
            <thead>
              <tr>
                <th className={tbl.th}>Device</th>
                <th className={tbl.th}>IP address</th>
                <th className={tbl.th}>Last active</th>
                <th className={tbl.th}><span className="sr-only">Actions</span></th>
              </tr>
            </thead>
            <tbody>
              {data.map((s) => (
                <tr key={s.id} className={tbl.row}>
                  <td className={tbl.td}>
                    <span className="flex items-center gap-2">
                      <Laptop size={15} className="text-muted" aria-hidden />
                      {deviceName(s.user_agent)}
                      {s.current && <Badge tone="pass">This device</Badge>}
                      {s.auth_method === "sso" && <Badge tone="ink">SSO</Badge>}
                    </span>
                  </td>
                  <td className={`${tbl.td} font-mono text-xs`}>{s.ip || "Unknown"}</td>
                  <td className={tbl.td}>{fmtDateTime(s.last_seen_at)}</td>
                  <td className={`${tbl.td} text-right`}>
                    {!s.current && <Button variant="ghost" size="sm" onClick={() => revoke(s.id)}>Sign out</Button>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Panel>
  );
}
