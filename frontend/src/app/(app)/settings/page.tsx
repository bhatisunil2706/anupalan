"use client";

import { useEffect, useState } from "react";

import { useSession } from "@/components/session";
import { Badge, Button, Checkbox, Field, FormError, Input, LoadError, Loading, PageHeader, Panel, Select, Tabs, tbl, useToast } from "@/components/ui";
import { api, useApi } from "@/lib/api";
import { fmtDate, fmtDateTime, humanize } from "@/lib/format";
import type { Org, Role } from "@/lib/types";

type Tab = "org" | "team" | "audit";

export default function SettingsPage() {
  const { isAdmin } = useSession();
  const [tab, setTab] = useState<Tab>("org");
  return (
    <>
      <PageHeader title="Settings" />
      <Tabs<Tab>
        tabs={[
          { value: "org", label: "Organisation" },
          { value: "team", label: "Team" },
          ...(isAdmin ? [{ value: "audit" as Tab, label: "Audit log" }] : []),
        ]}
        value={tab}
        onChange={setTab}
      />
      {tab === "org" && <OrgSettings />}
      {tab === "team" && <Team />}
      {tab === "audit" && isAdmin && <AuditLog />}
    </>
  );
}

function OrgSettings() {
  const { isAdmin, refresh } = useSession();
  const toast = useToast();
  const { data: org, error, loading, reload } = useApi<Org>("/org");
  const flags = useApi<{ key: string; label: string }[]>("/org/profile-flags");
  const [form, setForm] = useState({ name: "", sector: "", employee_count: "", rights_request_sla_days: 30, profile: {} as Record<string, boolean> });
  const [formError, setFormError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (org) setForm({ name: org.name, sector: org.sector, employee_count: org.employee_count, rights_request_sla_days: org.rights_request_sla_days, profile: org.profile });
  }, [org]);

  if (loading && !org) return <Loading />;
  if (error || !org) return <LoadError error={error ?? "Could not load"} retry={reload} />;

  async function save() {
    setBusy(true);
    setFormError(null);
    try {
      await api("/org", { method: "PATCH", json: form });
      toast("Settings saved");
      await refresh();
      reload();
    } catch (e) {
      setFormError(e instanceof Error ? e.message : "Failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="max-w-2xl space-y-6">
      <Panel title="Company">
        <div className="space-y-4">
          <FormError error={formError} />
          <Field label="Company name">{(id) => <Input id={id} value={form.name} disabled={!isAdmin} onChange={(e) => setForm({ ...form, name: e.target.value })} />}</Field>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Sector">{(id) => <Input id={id} value={form.sector} disabled={!isAdmin} onChange={(e) => setForm({ ...form, sector: e.target.value })} />}</Field>
            <Field label="Employees">{(id) => <Input id={id} value={form.employee_count} disabled={!isAdmin} onChange={(e) => setForm({ ...form, employee_count: e.target.value })} />}</Field>
          </div>
          <Field label="Target days to answer rights requests" hint="Your internal deadline. The law allows at most 90 days for grievances.">
            {(id) => (
              <Input id={id} type="number" min={1} max={90} value={form.rights_request_sla_days} disabled={!isAdmin}
                onChange={(e) => setForm({ ...form, rights_request_sla_days: Number(e.target.value) })} className="w-28" />
            )}
          </Field>
        </div>
      </Panel>
      <Panel title="What applies to you">
        <p className="mb-4 text-sm text-muted">Turning one of these on adds the matching DPDP or CERT-In requirements and controls.</p>
        <div className="space-y-3">
          {(flags.data ?? []).map((f) => (
            <Checkbox key={f.key} label={f.label} checked={!!form.profile[f.key]} onChange={(v) => isAdmin && setForm({ ...form, profile: { ...form.profile, [f.key]: v } })} />
          ))}
        </div>
      </Panel>
      {isAdmin && <div className="flex justify-end"><Button onClick={save} busy={busy}>Save settings</Button></div>}
    </div>
  );
}

function Team() {
  const { me, members, isAdmin, refresh } = useSession();
  const toast = useToast();
  const invites = useApi<{ id: string; email: string; role: Role; expires_at: string }[]>(isAdmin ? "/org/invitations" : null);
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<Role>("member");
  const [link, setLink] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function invite(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setFormError(null);
    try {
      const r = await api<{ invite_url: string }>("/org/invitations", { method: "POST", json: { email, role } });
      setLink(r.invite_url);
      setEmail("");
      invites.reload();
    } catch (err) {
      setFormError(err instanceof Error ? err.message : "Failed");
    } finally {
      setBusy(false);
    }
  }

  async function changeRole(userId: string, newRole: string) {
    try {
      await api(`/org/members/${userId}`, { method: "PATCH", json: { role: newRole } });
      toast("Role updated");
      refresh();
    } catch (e) {
      toast(e instanceof Error ? e.message : "Failed", "error");
    }
  }

  async function remove(userId: string, name: string) {
    if (!confirm(`Remove ${name} from this workspace?`)) return;
    try {
      await api(`/org/members/${userId}`, { method: "DELETE" });
      toast("Member removed");
      refresh();
    } catch (e) {
      toast(e instanceof Error ? e.message : "Failed", "error");
    }
  }

  return (
    <div className="space-y-6">
      {isAdmin && (
        <Panel title="Invite someone">
          <form onSubmit={invite} className="flex flex-wrap items-end gap-3">
            <Field label="Email" className="min-w-[240px] flex-1">{(id) => <Input id={id} type="email" required value={email} onChange={(e) => setEmail(e.target.value)} />}</Field>
            <Field label="Role">
              {(id) => (
                <Select id={id} value={role} onChange={(e) => setRole(e.target.value as Role)}>
                  <option value="member">Member: works on controls and tasks</option>
                  <option value="admin">Admin: also manages settings and team</option>
                  <option value="auditor">Auditor: read-only</option>
                  {me.role === "owner" && <option value="owner">Owner</option>}
                </Select>
              )}
            </Field>
            <Button type="submit" busy={busy}>Create invite link</Button>
          </form>
          <FormError error={formError} />
          {link && (
            <div className="mt-4 rounded-md border border-pass/30 bg-pass-50 p-3 text-sm">
              <p className="font-medium text-pass">Invite link created. Send it to them; it works once and expires in 7 days.</p>
              <div className="mt-2 flex gap-2">
                <Input readOnly value={link} aria-label="Invite link" onFocus={(e) => e.target.select()} />
                <Button type="button" variant="secondary" onClick={() => { navigator.clipboard.writeText(link); toast("Link copied"); }}>Copy</Button>
              </div>
            </div>
          )}
        </Panel>
      )}

      <Panel title={`Members (${members.length})`} flush>
        <div className={tbl.wrap}>
          <table className={tbl.table}>
            <thead><tr><th className={tbl.th}>Name</th><th className={tbl.th}>Role</th><th className={tbl.th}>Joined</th><th className={tbl.th} /></tr></thead>
            <tbody>
              {members.map((m) => (
                <tr key={m.user.id}>
                  <td className={tbl.td}>{m.user.full_name}<span className="block text-xs text-muted">{m.user.email}</span></td>
                  <td className={tbl.td}>
                    {isAdmin && m.user.id !== me.user.id ? (
                      <Select value={m.role} onChange={(e) => changeRole(m.user.id, e.target.value)} className="w-32" aria-label={`Role for ${m.user.full_name}`}>
                        {["owner", "admin", "member", "auditor"].map((r) => <option key={r} value={r}>{humanize(r)}</option>)}
                      </Select>
                    ) : (
                      <Badge tone="ink">{humanize(m.role)}</Badge>
                    )}
                  </td>
                  <td className={`${tbl.td} text-muted`}>{fmtDate(m.joined_at)}</td>
                  <td className={`${tbl.td} text-right`}>
                    {isAdmin && m.user.id !== me.user.id && <Button size="sm" variant="ghost" onClick={() => remove(m.user.id, m.user.full_name)}>Remove</Button>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>

      {isAdmin && (invites.data?.length ?? 0) > 0 && (
        <Panel title="Pending invitations" flush>
          <ul>
            {invites.data!.map((i) => (
              <li key={i.id} className="flex items-center justify-between border-b border-line px-4 py-2.5 text-sm last:border-0">
                <span>{i.email} <span className="text-muted">as {i.role}, expires {fmtDate(i.expires_at)}</span></span>
                <Button size="sm" variant="ghost" onClick={async () => { await api(`/org/invitations/${i.id}`, { method: "DELETE" }); invites.reload(); }}>Revoke</Button>
              </li>
            ))}
          </ul>
        </Panel>
      )}
    </div>
  );
}

function AuditLog() {
  const { data, error, loading, reload } = useApi<{ id: string; at: string; action: string; user: string; entity_type: string; detail: Record<string, unknown> }[]>("/org/audit-log?limit=200");
  if (loading && !data) return <Loading />;
  if (error || !data) return <LoadError error={error ?? "Could not load"} retry={reload} />;
  return (
    <div className="rounded-lg border border-line bg-surface">
      <div className={tbl.wrap}>
        <table className={tbl.table}>
          <thead><tr><th className={tbl.th}>When</th><th className={tbl.th}>Who</th><th className={tbl.th}>Action</th><th className={tbl.th}>Details</th></tr></thead>
          <tbody>
            {data.map((e) => (
              <tr key={e.id}>
                <td className={`${tbl.td} whitespace-nowrap text-muted`}>{fmtDateTime(e.at)}</td>
                <td className={tbl.td}>{e.user}</td>
                <td className={tbl.td}>{e.action}</td>
                <td className={`${tbl.td} max-w-[40ch] truncate text-xs text-muted`} title={JSON.stringify(e.detail)}>
                  {Object.entries(e.detail).map(([k, v]) => `${k}: ${Array.isArray(v) ? v.join(", ") : String(v)}`).join("; ")}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
