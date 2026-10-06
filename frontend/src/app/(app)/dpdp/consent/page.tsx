"use client";

import { Download, Plus } from "lucide-react";
import { useState } from "react";

import { useSession } from "@/components/session";
import { Badge, Button, Checkbox, Drawer, Empty, Field, FormError, Input, LoadError, Loading, PageHeader, Panel, Tabs, Textarea, tbl, useToast } from "@/components/ui";
import { api, download, useApi } from "@/lib/api";
import { fmtDate, fmtDateTime } from "@/lib/format";

interface Purpose { id: string; label: string; description?: string; required: boolean }
interface Notice {
  id: string; key: string; version: number; title: string; body_md: string; purposes: Purpose[];
  languages: string[]; status: "draft" | "published" | "retired"; published_at: string | null;
}
interface ConsentEvent {
  id: string; event_id: string; principal_id: string; notice_key: string; notice_version: number;
  action: "granted" | "withdrawn"; purposes: string[]; source: string; language: string; occurred_at: string; received_at: string;
}
interface Summary { granted_30d: number; withdrawn_30d: number; principals: number; by_source_30d: Record<string, number>; last_event_at: string | null }

type Tab = "log" | "notices" | "connect";

export default function ConsentPage() {
  const [tab, setTab] = useState<Tab>("log");
  const summary = useApi<Summary>("/consent/summary");
  const s = summary.data;
  return (
    <>
      <PageHeader
        title="Consent records"
        description="An append-only record of what each person agreed to, against which notice version, and when they withdrew (DPDP s.6). Your website and app send records through the API."
        actions={<Button variant="secondary" onClick={() => download("/consent/export", "consent-log.csv")}><Download size={14} aria-hidden /> Export CSV</Button>}
      />
      {s && (
        <div className="mb-6 grid gap-3 sm:grid-cols-4">
          <Stat label="Consents in 30 days" value={s.granted_30d} />
          <Stat label="Withdrawals in 30 days" value={s.withdrawn_30d} />
          <Stat label="People on record" value={s.principals} />
          <Stat label="Last record" value={s.last_event_at ? fmtDateTime(s.last_event_at) : "None yet"} small />
        </div>
      )}
      <Tabs<Tab> tabs={[{ value: "log", label: "Records" }, { value: "notices", label: "Consent notices" }, { value: "connect", label: "Connect your app" }]} value={tab} onChange={setTab} />
      {tab === "log" && <Log />}
      {tab === "notices" && <Notices />}
      {tab === "connect" && <Connect />}
    </>
  );
}

function Stat({ label, value, small }: { label: string; value: string | number; small?: boolean }) {
  return (
    <div className="rounded-lg border border-line bg-surface p-4">
      <p className="text-xs text-muted">{label}</p>
      <p className={small ? "mt-1 text-sm font-medium" : "mt-1 text-2xl font-bold"}>{value}</p>
    </div>
  );
}

function Log() {
  const [q, setQ] = useState("");
  const [principal, setPrincipal] = useState<string | null>(null);
  const events = useApi<ConsentEvent[]>(principal ? `/consent/events?principal_id=${encodeURIComponent(principal)}` : "/consent/events?limit=200");
  const state = useApi<{ consents: Record<string, { version: number; purposes: string[]; updated_at: string }> }>(principal ? `/consent/principals/${encodeURIComponent(principal)}` : null);

  return (
    <div className="space-y-4">
      <form onSubmit={(e) => { e.preventDefault(); setPrincipal(q.trim() || null); }} className="flex flex-wrap items-end gap-2">
        <Field label="Look up a person by your user ID" className="min-w-[260px]">{(id) => <Input id={id} placeholder="cust-10042" value={q} onChange={(e) => setQ(e.target.value)} />}</Field>
        <Button type="submit" variant="secondary">Look up</Button>
        {principal && <Button type="button" variant="ghost" onClick={() => { setQ(""); setPrincipal(null); }}>Clear</Button>}
      </form>
      {principal && state.data && (
        <Panel title={`Current consent for ${principal}`}>
          {Object.keys(state.data.consents).length === 0 ? <p className="text-sm text-muted">No consent on record.</p> : (
            <ul className="space-y-1 text-sm">
              {Object.entries(state.data.consents).map(([k, v]) => (
                <li key={k}><span className="font-medium">{k}</span> v{v.version}: {v.purposes.length ? v.purposes.join(", ") : <span className="text-fail">all withdrawn</span>} <span className="text-muted">(since {fmtDate(v.updated_at)})</span></li>
              ))}
            </ul>
          )}
        </Panel>
      )}
      <Panel flush>
        {events.loading && !events.data ? <Loading /> : events.error || !events.data ? <div className="p-4"><LoadError error={events.error ?? "Could not load"} retry={events.reload} /></div> : events.data.length === 0 ? (
          <Empty title="No consent records yet">Create a consent notice, then connect your website or app to start recording consent.</Empty>
        ) : (
          <div className={tbl.wrap}>
            <table className={tbl.table}>
              <thead><tr><th className={tbl.th}>When</th><th className={tbl.th}>Person</th><th className={tbl.th}>Action</th><th className={tbl.th}>Purposes</th><th className={tbl.th}>Notice</th><th className={tbl.th}>Source</th></tr></thead>
              <tbody>
                {events.data.map((e) => (
                  <tr key={e.id} className={tbl.row}>
                    <td className={`${tbl.td} whitespace-nowrap text-muted`}>{fmtDateTime(e.occurred_at)}</td>
                    <td className={`${tbl.td} font-mono text-xs`}><button className="underline" onClick={() => { setQ(e.principal_id); setPrincipal(e.principal_id); }}>{e.principal_id}</button></td>
                    <td className={tbl.td}><Badge tone={e.action === "granted" ? "pass" : "warn"}>{e.action === "granted" ? "Granted" : "Withdrawn"}</Badge></td>
                    <td className={`${tbl.td} text-xs`}>{e.purposes.join(", ") || "All"}</td>
                    <td className={`${tbl.td} text-xs`}>{e.notice_key} v{e.notice_version}</td>
                    <td className={`${tbl.td} text-xs`}><span className="capitalize">{e.source.replace("_", " ")}</span> · {e.language.toUpperCase()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
    </div>
  );
}

const EMPTY_NOTICE = { key: "", title: "", body_md: "", languages: "en", purposes: [{ id: "", label: "", required: true }] as Purpose[] };

function Notices() {
  const { canWrite } = useSession();
  const toast = useToast();
  const { data, error, loading, reload } = useApi<Notice[]>("/consent/notices");
  const [editing, setEditing] = useState<{ id?: string; form: typeof EMPTY_NOTICE } | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function save() {
    if (!editing) return;
    setBusy(true);
    setFormError(null);
    const f = editing.form;
    const body = { key: f.key, title: f.title, body_md: f.body_md, languages: f.languages.split(",").map((s) => s.trim()).filter(Boolean), purposes: f.purposes };
    try {
      await api(editing.id ? `/consent/notices/${editing.id}` : "/consent/notices", { method: editing.id ? "PUT" : "POST", json: body });
      toast("Notice saved as a draft");
      setEditing(null);
      reload();
    } catch (e) {
      setFormError(e instanceof Error ? e.message : "Failed");
    } finally {
      setBusy(false);
    }
  }

  async function publish(n: Notice) {
    if (!confirm(`Publish ${n.title} v${n.version}? It can't be edited after publishing, and any older version will be retired.`)) return;
    try {
      await api(`/consent/notices/${n.id}/publish`, { method: "POST" });
      toast("Notice published");
      reload();
    } catch (e) {
      toast(e instanceof Error ? e.message : "Failed", "error");
    }
  }

  if (loading && !data) return <Loading />;
  if (error || !data) return <LoadError error={error ?? "Could not load"} retry={reload} />;
  const f = editing?.form;

  return (
    <>
      <div className="mb-4 flex justify-end">
        {canWrite && <Button onClick={() => { setFormError(null); setEditing({ form: structuredClone(EMPTY_NOTICE) }); }}><Plus size={14} aria-hidden /> New notice</Button>}
      </div>
      {data.length === 0 ? <Panel><Empty title="No consent notices">A notice describes what you collect and why. Each purpose can be consented to separately.</Empty></Panel> : (
        <div className="space-y-3">
          {data.map((n) => (
            <Panel key={n.id} title={<span className="flex items-center gap-2">{n.title} <span className="font-normal text-muted">({n.key} v{n.version})</span></span>}
              actions={
                <div className="flex items-center gap-2">
                  <Badge tone={n.status === "published" ? "pass" : n.status === "draft" ? "prog" : "idle"}>{n.status === "published" ? `Published ${fmtDate(n.published_at)}` : n.status === "draft" ? "Draft" : "Retired"}</Badge>
                  {canWrite && n.status === "draft" && (
                    <>
                      <Button size="sm" variant="secondary" onClick={() => setEditing({ id: n.id, form: { key: n.key, title: n.title, body_md: n.body_md, languages: n.languages.join(", "), purposes: n.purposes } })}>Edit</Button>
                      <Button size="sm" onClick={() => publish(n)}>Publish</Button>
                    </>
                  )}
                  {canWrite && n.status === "published" && (
                    <Button size="sm" variant="secondary" onClick={() => setEditing({ form: { key: n.key, title: n.title, body_md: n.body_md, languages: n.languages.join(", "), purposes: n.purposes } })}>New version</Button>
                  )}
                </div>
              }>
              <p className="whitespace-pre-line text-sm text-muted">{n.body_md}</p>
              <ul className="mt-3 flex flex-wrap gap-2 text-xs">
                {n.purposes.map((p) => <li key={p.id}><Badge tone="ink">{p.label}{p.required && " (required)"}</Badge></li>)}
              </ul>
            </Panel>
          ))}
        </div>
      )}
      <Drawer open={!!editing} onClose={() => setEditing(null)} title={editing?.id ? "Edit notice" : "New consent notice"} wide
        footer={<><Button variant="secondary" onClick={() => setEditing(null)}>Cancel</Button><Button busy={busy} onClick={save}>Save draft</Button></>}>
        {f && editing && (
          <>
            <FormError error={formError} />
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="Key" hint="Your app sends this, e.g. signup">{(id) => <Input id={id} pattern="[a-z0-9_-]{2,60}" disabled={!!editing.id} value={f.key} onChange={(e) => setEditing({ ...editing, form: { ...f, key: e.target.value } })} />}</Field>
              <Field label="Languages" hint="Comma-separated, e.g. en, hi">{(id) => <Input id={id} value={f.languages} onChange={(e) => setEditing({ ...editing, form: { ...f, languages: e.target.value } })} />}</Field>
            </div>
            <Field label="Title">{(id) => <Input id={id} value={f.title} onChange={(e) => setEditing({ ...editing, form: { ...f, title: e.target.value } })} />}</Field>
            <Field label="Notice text" hint="Plain language: what data, for what purpose, how to withdraw and how to complain to the Board.">{(id) => <Textarea id={id} rows={6} value={f.body_md} onChange={(e) => setEditing({ ...editing, form: { ...f, body_md: e.target.value } })} />}</Field>
            <div className="space-y-3">
              <p className="text-[13px] font-medium">Purposes</p>
              {f.purposes.map((p, i) => (
                <div key={i} className="grid gap-2 rounded-md border border-line p-3 sm:grid-cols-[140px_1fr_auto]">
                  <Input aria-label="Purpose id" placeholder="marketing" value={p.id} onChange={(e) => setEditing({ ...editing, form: { ...f, purposes: f.purposes.map((x, j) => (j === i ? { ...x, id: e.target.value } : x)) } })} />
                  <Input aria-label="Purpose label" placeholder="Offers by email and SMS" value={p.label} onChange={(e) => setEditing({ ...editing, form: { ...f, purposes: f.purposes.map((x, j) => (j === i ? { ...x, label: e.target.value } : x)) } })} />
                  <div className="flex items-center gap-3">
                    <Checkbox label="Required" checked={p.required} onChange={(v) => setEditing({ ...editing, form: { ...f, purposes: f.purposes.map((x, j) => (j === i ? { ...x, required: v } : x)) } })} />
                    {f.purposes.length > 1 && <Button variant="ghost" size="sm" onClick={() => setEditing({ ...editing, form: { ...f, purposes: f.purposes.filter((_, j) => j !== i) } })}>Remove</Button>}
                  </div>
                </div>
              ))}
              <Button variant="secondary" size="sm" onClick={() => setEditing({ ...editing, form: { ...f, purposes: [...f.purposes, { id: "", label: "", required: false }] } })}><Plus size={14} aria-hidden /> Add purpose</Button>
            </div>
          </>
        )}
      </Drawer>
    </>
  );
}

function Connect() {
  const origin = typeof window !== "undefined" ? window.location.origin : "https://app.example.com";
  const example = `curl -X POST ${origin}/api/v1/consent/events \\
  -H "Authorization: Bearer $ANUPALAN_API_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{
    "event_id": "8f2c0b6e-signup-42",
    "principal_id": "cust-10042",
    "notice_key": "signup",
    "action": "granted",
    "purposes": ["account", "marketing"],
    "source": "web",
    "language": "en"
  }'`;
  return (
    <div className="max-w-3xl space-y-4 text-sm">
      <Panel title="1. Create an API key">
        <p>In Settings &gt; Security, create a key with the <code className="font-mono">consent:write</code> scope (and <code className="font-mono">consent:read</code> if your systems need to look up consent). Keep it on your server, never in browser code.</p>
      </Panel>
      <Panel title="2. Send a record when someone agrees or withdraws">
        <pre className="overflow-x-auto rounded-md bg-ink p-3 font-mono text-xs leading-relaxed text-white">{example}</pre>
        <p className="mt-3 text-muted"><code className="font-mono">event_id</code> makes retries safe: sending the same ID twice records it once. For a withdrawal use <code className="font-mono">&quot;action&quot;: &quot;withdrawn&quot;</code>; an empty purposes list withdraws everything.</p>
      </Panel>
      <Panel title="3. Act on withdrawals">
        <p>Poll <code className="font-mono">GET /api/v1/consent/events?action=withdrawn&amp;since=…</code> from your back end and stop the related processing, including at your processors (DPDP s.6(6)). Check a person&apos;s current consent with <code className="font-mono">GET /api/v1/consent/principals/&#123;id&#125;</code>.</p>
      </Panel>
    </div>
  );
}
