"use client";

import { Copy, KeyRound, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";

import { useSession } from "@/components/session";
import { Badge, Button, Checkbox, Field, FormError, Input, LoadError, Loading, Panel, Select, tbl, useToast } from "@/components/ui";
import { api, useApi } from "@/lib/api";
import { fmtDate, fmtDateTime } from "@/lib/format";

interface Policy {
  require_mfa: boolean;
  session_idle_minutes: number;
  members: { id: string; full_name: string; email: string; role: string; mfa_enabled: boolean; email_verified: boolean; last_login_at: string | null }[];
}
interface Domain {
  id: string;
  domain: string;
  verified_at: string | null;
  txt_record: string;
}
interface Sso {
  configured: boolean;
  redirect_uri: string;
  provider?: string;
  issuer?: string;
  client_id?: string;
  client_secret_set?: boolean;
  enabled?: boolean;
  enforced?: boolean;
  jit_provisioning?: boolean;
  default_role?: string;
}
interface ApiKey {
  id: string;
  name: string;
  prefix: string;
  scopes: string[];
  created_at: string;
  last_used_at: string | null;
  expires_at: string | null;
  revoked_at: string | null;
}

export function SecuritySettings() {
  const { me } = useSession();
  return (
    <div className="max-w-3xl space-y-6">
      <SignInPolicy />
      <Domains />
      {me.role === "owner" && <SsoSettings />}
      <ApiKeys />
      {me.role === "owner" && <AiSetting />}
      <EvidenceSettings />
    </div>
  );
}

function SignInPolicy() {
  const { me } = useSession();
  const toast = useToast();
  const { data, error, loading, reload } = useApi<Policy>("/org/security");
  const [idle, setIdle] = useState(120);
  const [formError, setFormError] = useState<string | null>(null);
  useEffect(() => {
    if (data) setIdle(data.session_idle_minutes);
  }, [data]);
  if (loading && !data) return <Panel title="Sign-in policy"><Loading /></Panel>;
  if (error || !data) return <LoadError error={error ?? "Could not load"} retry={reload} />;

  async function save(body: Partial<Policy>) {
    setFormError(null);
    try {
      await api("/org/security", { method: "PUT", json: body });
      toast("Security policy saved");
      reload();
    } catch (e) {
      setFormError(e instanceof Error ? e.message : "Failed");
    }
  }
  const withoutMfa = data.members.filter((m) => !m.mfa_enabled);

  return (
    <Panel title="Sign-in policy">
      <div className="space-y-5">
        <FormError error={formError} />
        <div>
          <Checkbox
            label="Require two-step verification for everyone"
            hint={
              me.mfa_enabled
                ? "People without it are asked to set it up before they can continue. SSO sign-ins rely on your identity provider's MFA."
                : "Turn on two-step verification for your own account first (Account security)."
            }
            checked={data.require_mfa}
            onChange={(v) => save({ require_mfa: v })}
          />
          {withoutMfa.length > 0 && (
            <p className="mt-2 text-xs text-warn">
              {withoutMfa.length} {withoutMfa.length === 1 ? "person hasn't" : "people haven't"} set it up yet: {withoutMfa.map((m) => m.full_name).join(", ")}
            </p>
          )}
        </div>
        <div className="flex flex-wrap items-end gap-3">
          <Field label="Sign out after inactivity (minutes)" hint="Between 5 minutes and 24 hours. Sessions also end after 12 hours regardless.">
            {(id) => <Input id={id} type="number" min={5} max={1440} value={idle} onChange={(e) => setIdle(Number(e.target.value))} className="w-32" />}
          </Field>
          <Button variant="secondary" onClick={() => save({ session_idle_minutes: idle })}>Save</Button>
        </div>
      </div>
    </Panel>
  );
}

function Domains() {
  const toast = useToast();
  const { data, error, loading, reload } = useApi<Domain[]>("/org/domains");
  const [domain, setDomain] = useState("");
  const [formError, setFormError] = useState<string | null>(null);

  async function act(fn: () => Promise<unknown>, msg: string) {
    setFormError(null);
    try {
      await fn();
      toast(msg);
      reload();
    } catch (e) {
      setFormError(e instanceof Error ? e.message : "Failed");
    }
  }

  return (
    <Panel title="Company domains">
      <div className="space-y-4">
        <p className="text-sm text-muted">Verify the email domains you own. Single sign-on only accepts people from verified domains.</p>
        <FormError error={formError} />
        {loading && !data ? (
          <Loading />
        ) : error || !data ? (
          <LoadError error={error ?? "Could not load"} retry={reload} />
        ) : (
          data.map((d) => (
            <div key={d.id} className="rounded-md border border-line p-3 text-sm">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-medium">{d.domain}</span>
                {d.verified_at ? <Badge tone="pass">Verified {fmtDate(d.verified_at)}</Badge> : <Badge tone="warn">Not verified</Badge>}
                <span className="flex-1" />
                {!d.verified_at && (
                  <Button size="sm" variant="secondary" onClick={() => act(() => api(`/org/domains/${d.id}/verify`, { method: "POST" }), "Domain verified")}>
                    Check DNS
                  </Button>
                )}
                <Button size="sm" variant="ghost" aria-label={`Remove ${d.domain}`} onClick={() => act(() => api(`/org/domains/${d.id}`, { method: "DELETE" }), "Domain removed")}>
                  <Trash2 size={14} />
                </Button>
              </div>
              {!d.verified_at && (
                <p className="mt-2 text-xs text-muted">
                  Add a DNS TXT record on <span className="font-mono">{d.domain}</span> with the value{" "}
                  <code className="break-all rounded bg-paper px-1 font-mono text-text">{d.txt_record}</code>, then click Check DNS.
                </p>
              )}
            </div>
          ))
        )}
        <form
          onSubmit={(e) => {
            e.preventDefault();
            act(() => api("/org/domains", { method: "POST", json: { domain } }).then(() => setDomain("")), "Domain added");
          }}
          className="flex flex-wrap items-end gap-3"
        >
          <Field label="Add a domain" className="min-w-[220px] flex-1">{(id) => <Input id={id} placeholder="acme.in" required value={domain} onChange={(e) => setDomain(e.target.value)} />}</Field>
          <Button type="submit" variant="secondary">Add</Button>
        </form>
      </div>
    </Panel>
  );
}

const PROVIDERS: Record<string, { label: string; issuerLabel: string; placeholder: string }> = {
  google: { label: "Google Workspace", issuerLabel: "", placeholder: "" },
  microsoft: { label: "Microsoft Entra ID", issuerLabel: "Directory (tenant) ID", placeholder: "00000000-0000-0000-0000-000000000000" },
  okta: { label: "Okta", issuerLabel: "Okta domain", placeholder: "acme.okta.com" },
  oidc: { label: "Other OpenID Connect", issuerLabel: "Issuer URL", placeholder: "https://login.example.com" },
};

function SsoSettings() {
  const toast = useToast();
  const { data, error, loading, reload } = useApi<Sso>("/org/sso");
  const [form, setForm] = useState({ provider: "google", issuer: "", client_id: "", client_secret: "", enabled: false, enforced: false, jit_provisioning: false, default_role: "member" });
  const [formError, setFormError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    if (data?.configured) {
      setForm((f) => ({ ...f, provider: data.provider!, issuer: data.issuer ?? "", client_id: data.client_id ?? "", enabled: !!data.enabled, enforced: !!data.enforced, jit_provisioning: !!data.jit_provisioning, default_role: data.default_role ?? "member" }));
    }
  }, [data]);
  if (loading && !data) return <Panel title="Single sign-on"><Loading /></Panel>;
  if (error || !data) return <LoadError error={error ?? "Could not load"} retry={reload} />;

  async function save() {
    setBusy(true);
    setFormError(null);
    try {
      await api("/org/sso", { method: "PUT", json: form });
      setForm((f) => ({ ...f, client_secret: "" }));
      toast("Single sign-on saved");
      reload();
    } catch (e) {
      setFormError(e instanceof Error ? e.message : "Failed");
    } finally {
      setBusy(false);
    }
  }
  const p = PROVIDERS[form.provider];

  return (
    <Panel title="Single sign-on" actions={data.enabled ? <Badge tone="pass">On</Badge> : <Badge>Off</Badge>}>
      <div className="space-y-4">
        <FormError error={formError} />
        <div className="rounded-md bg-paper p-3 text-xs text-muted">
          Register an OpenID Connect web app in your identity provider with this redirect URI:{" "}
          <code className="break-all font-mono text-text">{data.redirect_uri}</code>
          <button className="ml-2 align-middle" aria-label="Copy redirect URI" onClick={() => navigator.clipboard.writeText(data.redirect_uri).then(() => toast("Copied"))}>
            <Copy size={12} />
          </button>
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Identity provider">
            {(id) => (
              <Select id={id} value={form.provider} onChange={(e) => setForm({ ...form, provider: e.target.value })}>
                {Object.entries(PROVIDERS).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
              </Select>
            )}
          </Field>
          {p.issuerLabel && <Field label={p.issuerLabel}>{(id) => <Input id={id} placeholder={p.placeholder} value={form.issuer} onChange={(e) => setForm({ ...form, issuer: e.target.value })} />}</Field>}
          <Field label="Client ID">{(id) => <Input id={id} value={form.client_id} onChange={(e) => setForm({ ...form, client_id: e.target.value })} />}</Field>
          <Field label="Client secret" hint={data.client_secret_set ? "Saved. Leave blank to keep it." : undefined}>
            {(id) => <Input id={id} type="password" autoComplete="off" value={form.client_secret} onChange={(e) => setForm({ ...form, client_secret: e.target.value })} />}
          </Field>
        </div>
        <Checkbox label="Turn on SSO" hint="People from your verified domains can sign in through your identity provider." checked={form.enabled} onChange={(v) => setForm({ ...form, enabled: v })} />
        <Checkbox label="Require SSO" hint="Password sign-in is blocked for verified domains. Owners keep password access for emergencies." checked={form.enforced} onChange={(v) => setForm({ ...form, enforced: v })} />
        <Checkbox label="Create accounts on first sign-in" hint="Anyone in your verified domains who can sign in to your identity provider gets access." checked={form.jit_provisioning} onChange={(v) => setForm({ ...form, jit_provisioning: v })} />
        {form.jit_provisioning && (
          <Field label="Role for new people">
            {(id) => (
              <Select id={id} value={form.default_role} onChange={(e) => setForm({ ...form, default_role: e.target.value })} className="w-48">
                <option value="member">Member</option>
                <option value="auditor">Auditor (read-only)</option>
              </Select>
            )}
          </Field>
        )}
        <Button busy={busy} onClick={save}>Save</Button>
      </div>
    </Panel>
  );
}

function ApiKeys() {
  const toast = useToast();
  const { data, error, loading, reload } = useApi<{ keys: ApiKey[]; scopes: Record<string, string> }>("/org/api-keys");
  const [name, setName] = useState("");
  const [scopes, setScopes] = useState<string[]>(["consent:write"]);
  const [secret, setSecret] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);

  async function create(e: React.FormEvent) {
    e.preventDefault();
    setFormError(null);
    try {
      const r = await api<{ secret: string }>("/org/api-keys", { method: "POST", json: { name, scopes } });
      setSecret(r.secret);
      setName("");
      reload();
    } catch (err) {
      setFormError(err instanceof Error ? err.message : "Failed");
    }
  }

  return (
    <Panel title="API keys" flush>
      <div className="space-y-4 p-4">
        <p className="text-sm text-muted">For your website or app to send consent records, and for the self-hosted data scanner. Keys are stored hashed and shown once.</p>
        <FormError error={formError} />
        {secret && (
          <div className="rounded-md border border-pass/30 bg-pass-50 p-3 text-sm">
            <p className="font-medium text-pass">Copy this key now. You won&apos;t see it again.</p>
            <div className="mt-2 flex gap-2">
              <Input readOnly value={secret} aria-label="API key" className="font-mono" onFocus={(e) => e.target.select()} />
              <Button variant="secondary" onClick={() => navigator.clipboard.writeText(secret).then(() => toast("Copied"))}><Copy size={14} /></Button>
              <Button variant="ghost" onClick={() => setSecret(null)}>Done</Button>
            </div>
          </div>
        )}
        {data && (
          <form onSubmit={create} className="space-y-3">
            <div className="flex flex-wrap items-end gap-3">
              <Field label="Name" className="min-w-[200px] flex-1">{(id) => <Input id={id} required placeholder="Website consent banner" value={name} onChange={(e) => setName(e.target.value)} />}</Field>
              <Button type="submit"><KeyRound size={14} aria-hidden /> Create key</Button>
            </div>
            <div className="flex flex-wrap gap-x-5 gap-y-2">
              {Object.entries(data.scopes).map(([s, label]) => (
                <Checkbox key={s} label={s} hint={label} checked={scopes.includes(s)} onChange={(v) => setScopes(v ? [...scopes, s] : scopes.filter((x) => x !== s))} />
              ))}
            </div>
          </form>
        )}
      </div>
      {loading && !data ? (
        <Loading />
      ) : error || !data ? (
        <div className="p-4"><LoadError error={error ?? "Could not load"} retry={reload} /></div>
      ) : data.keys.length > 0 && (
        <div className={tbl.wrap}>
          <table className={tbl.table}>
            <thead><tr><th className={tbl.th}>Name</th><th className={tbl.th}>Key</th><th className={tbl.th}>Scopes</th><th className={tbl.th}>Last used</th><th className={tbl.th}><span className="sr-only">Actions</span></th></tr></thead>
            <tbody>
              {data.keys.map((k) => (
                <tr key={k.id} className={tbl.row}>
                  <td className={tbl.td}>{k.name}{k.revoked_at && <Badge className="ml-2">Revoked</Badge>}</td>
                  <td className={`${tbl.td} font-mono text-xs`}>{k.prefix}…</td>
                  <td className={`${tbl.td} text-xs`}>{k.scopes.join(", ")}</td>
                  <td className={tbl.td}>{k.last_used_at ? fmtDateTime(k.last_used_at) : "Never"}</td>
                  <td className={`${tbl.td} text-right`}>
                    {!k.revoked_at && (
                      <Button size="sm" variant="ghost" onClick={async () => { await api(`/org/api-keys/${k.id}`, { method: "DELETE" }); toast("Key revoked"); reload(); }}>Revoke</Button>
                    )}
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

function AiSetting() {
  const toast = useToast();
  const { data, reload } = useApi<{ enabled: boolean; available: boolean; model: string; used_24h: number; limit_24h: number }>("/ai/status");
  const [ack, setAck] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  if (!data) return null;

  async function toggle(enabled: boolean) {
    setFormError(null);
    try {
      await api("/org/ai", { method: "PUT", json: { enabled, acknowledge_data_sharing: ack } });
      toast(enabled ? "AI assistant turned on" : "AI assistant turned off");
      reload();
    } catch (e) {
      setFormError(e instanceof Error ? e.message : "Failed");
    }
  }

  return (
    <Panel title="AI assistant" actions={data.enabled ? <Badge tone="pass">On</Badge> : <Badge>Off</Badge>}>
      <div className="space-y-3 text-sm">
        <FormError error={formError} />
        <p className="text-muted">
          Drafts policies, suggests a remediation plan and answers security questionnaires from your own policies and controls. Text from your
          policies, controls and the questions you upload is sent to Anthropic&apos;s Claude API ({data.model}). People data and consent records
          are never sent. Evidence files are sent only if you also turn on AI evidence checks below.
        </p>
        {!data.available ? (
          <p className="text-warn">Not configured on this server (no API key).</p>
        ) : data.enabled ? (
          <Button variant="danger" onClick={() => toggle(false)}>Turn off</Button>
        ) : (
          <>
            <Checkbox label="I agree that policy and control text may be sent to the AI provider" checked={ack} onChange={setAck} />
            <Button disabled={!ack} onClick={() => toggle(true)}>Turn on</Button>
          </>
        )}
      </div>
    </Panel>
  );
}


function EvidenceSettings() {
  const { me } = useSession();
  const toast = useToast();
  const org = useApi<{ require_evidence_review: boolean; ai_evidence_checks: boolean }>("/org");
  const ai = useApi<{ enabled: boolean; available: boolean; model: string }>("/ai/status");
  const [ack, setAck] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  if (!org.data || !ai.data) return null;
  const isOwner = me.role === "owner";

  async function save(json: Record<string, unknown>, msg: string) {
    setFormError(null);
    try {
      await api("/org/evidence-settings", { method: "PUT", json });
      toast(msg);
      org.reload();
    } catch (e) {
      setFormError(e instanceof Error ? e.message : "Failed");
    }
  }

  return (
    <Panel title="Evidence checks">
      <div id="evidence" className="space-y-5 text-sm">
        <FormError error={formError} />
        <div>
          <div className="flex items-center justify-between gap-3">
            <p className="font-medium">Second-person review</p>
            {org.data.require_evidence_review ? <Badge tone="pass">On</Badge> : <Badge tone="warn">Off</Badge>}
          </div>
          <p className="mt-1 text-muted">
            Uploaded files, links and notes count only after someone other than the uploader (the control owner or an admin) approves them.
            Auditors expect this separation. Evidence collected by integrations is approved automatically.
          </p>
          <Button className="mt-2" size="sm" variant={org.data.require_evidence_review ? "danger" : "primary"}
            onClick={() => save({ require_evidence_review: !org.data!.require_evidence_review }, "Saved")}>
            {org.data.require_evidence_review ? "Turn off" : "Turn on"}
          </Button>
        </div>
        <div className="border-t border-line pt-4">
          <div className="flex items-center justify-between gap-3">
            <p className="font-medium">AI evidence checks</p>
            {org.data.ai_evidence_checks ? <Badge tone="pass">On</Badge> : <Badge>Off</Badge>}
          </div>
          <p className="mt-1 text-muted">
            Claude reads each new piece of evidence and compares it with what the control needs: right kind of document, current period,
            your company&apos;s name, completed rather than a blank template. Its verdict is advice for the reviewer and never approves anything.
            Turning this on sends uploaded evidence files to Anthropic&apos;s Claude API ({ai.data.model}).
          </p>
          {!isOwner ? (
            <p className="mt-2 text-xs text-muted">Only the owner can change this.</p>
          ) : !ai.data.available ? (
            <p className="mt-2 text-warn">Not configured on this server (no API key).</p>
          ) : !ai.data.enabled ? (
            <p className="mt-2 text-xs text-muted">Turn on the AI assistant above first.</p>
          ) : org.data.ai_evidence_checks ? (
            <Button className="mt-2" size="sm" variant="danger" onClick={() => save({ ai_evidence_checks: false }, "AI evidence checks turned off")}>Turn off</Button>
          ) : (
            <div className="mt-2 space-y-2">
              <Checkbox label="I agree that evidence files may be sent to the AI provider for checking" checked={ack} onChange={setAck} />
              <Button size="sm" disabled={!ack} onClick={() => save({ ai_evidence_checks: true, acknowledge_file_sharing: true }, "AI evidence checks turned on")}>Turn on</Button>
            </div>
          )}
        </div>
      </div>
    </Panel>
  );
}
