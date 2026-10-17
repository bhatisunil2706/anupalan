"use client";

import { ExternalLink, RefreshCw } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { ControlCodesPicker, MemberSelect } from "@/components/pickers";
import { useSession } from "@/components/session";
import { Badge, Button, Drawer, Empty, Field, FormError, Input, LoadError, Loading, PageHeader, Panel, Select, Textarea, cx, tbl, useToast } from "@/components/ui";
import { api, useApi } from "@/lib/api";
import { fmtDate, fmtDateTime, humanize } from "@/lib/format";
import type { Risk } from "@/lib/types";

const LEVEL = (score: number) =>
  score >= 15 ? { label: "High", tone: "fail" as const } : score >= 8 ? { label: "Medium", tone: "warn" as const } : { label: "Low", tone: "pass" as const };

const CELL = (score: number) => (score >= 15 ? "bg-fail-50" : score >= 8 ? "bg-warn-50" : "bg-pass-50");

const EMPTY = {
  title: "", description: "", category: "", likelihood: 3, impact: 3, treatment: "mitigate", treatment_plan: "",
  status: "open", owner_id: "", control_codes: [] as string[], review_date: "",
};

interface JiraStatus {
  connected: boolean;
  auto_create?: boolean;
  project?: string;
  importing?: boolean;
  status?: string;
  last_synced_at?: string | null;
  last_error?: string;
}

export default function RisksPage() {
  const { canWrite } = useSession();
  const toast = useToast();
  const { data, error, loading, reload } = useApi<Risk[]>("/risks");
  const jira = useApi<JiraStatus>("/risks/jira");
  const [syncing, setSyncing] = useState(false);
  const [linking, setLinking] = useState<string | null>(null);

  async function syncJira() {
    setSyncing(true);
    try {
      const r = await api<{ pushed: number; updated: number; imported: number }>("/risks/jira/sync", { method: "POST" });
      const parts = [r.pushed && `${r.pushed} sent to Jira`, r.updated && `${r.updated} status updates`, r.imported && `${r.imported} imported`].filter(Boolean);
      toast(parts.length ? `Jira sync: ${parts.join(", ")}` : "Jira sync: everything is up to date");
      reload();
      jira.reload();
    } catch (e) {
      toast(e instanceof Error ? e.message : "Sync failed", "error");
    } finally {
      setSyncing(false);
    }
  }

  async function createIssue(r: Risk) {
    setLinking(r.id);
    try {
      const out = await api<Risk>(`/risks/${r.id}/jira`, { method: "POST" });
      toast(`Created ${out.external_ref} in Jira`);
      reload();
    } catch (e) {
      toast(e instanceof Error ? e.message : "Failed", "error");
    } finally {
      setLinking(null);
    }
  }
  const [editing, setEditing] = useState<Risk | "new" | null>(null);
  const [form, setForm] = useState(EMPTY);
  const [formError, setFormError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  function open(r: Risk | "new") {
    setFormError(null);
    setForm(
      r === "new"
        ? EMPTY
        : { ...r, owner_id: r.owner?.id ?? "", control_codes: r.control_codes, review_date: r.review_date ?? "" },
    );
    setEditing(r);
  }

  async function save() {
    setBusy(true);
    setFormError(null);
    const body = {
      title: form.title, description: form.description, category: form.category, likelihood: form.likelihood, impact: form.impact,
      treatment: form.treatment, treatment_plan: form.treatment_plan, status: form.status, control_codes: form.control_codes,
      owner_id: form.owner_id || null, review_date: form.review_date || null,
    };
    try {
      let saved: Risk | null = null;
      if (editing === "new") saved = await api<Risk>("/risks", { method: "POST", json: body });
      else if (editing) saved = await api<Risk>(`/risks/${editing.id}`, { method: "PUT", json: body });
      if (editing === "new" && jira.data?.connected && jira.data.auto_create && saved && !saved.external_ref) {
        toast("Risk saved. Jira didn't respond; the issue will be created on the next sync.", "error");
      } else {
        toast(saved?.external_ref && editing === "new" ? `Risk saved and ${saved.external_ref} created in Jira` : "Risk saved");
      }
      setEditing(null);
      reload();
    } catch (e) {
      setFormError(e instanceof Error ? e.message : "Failed");
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    if (!editing || editing === "new" || !confirm("Delete this risk?")) return;
    await api(`/risks/${editing.id}`, { method: "DELETE" });
    toast("Risk deleted");
    setEditing(null);
    reload();
  }

  if (loading && !data) return <Loading />;
  if (error || !data) return <LoadError error={error ?? "Could not load"} retry={reload} />;
  const active = data.filter((r) => r.status !== "closed");
  const showJira = !!jira.data?.connected || data.some((r) => r.external_ref);

  return (
    <>
      <PageHeader
        title="Risk register"
        description="Score each risk by likelihood and impact from 1 to 5, decide how to treat it, and link the controls that reduce it."
        actions={
          canWrite && (
            <div className="flex gap-2">
              {jira.data?.connected && (
                <Button variant="secondary" busy={syncing} onClick={syncJira}>
                  <RefreshCw size={14} aria-hidden /> Sync with Jira
                </Button>
              )}
              <Button onClick={() => open("new")}>Add risk</Button>
            </div>
          )
        }
      />
      {jira.data && (
        <div className="mb-4 flex flex-wrap items-center gap-x-3 gap-y-1 rounded-lg border border-line bg-surface px-4 py-2.5 text-sm">
          {jira.data.connected ? (
            <>
              <Badge tone={jira.data.status === "error" ? "fail" : "pass"}>Jira {jira.data.status === "error" ? "error" : "connected"}</Badge>
              <span className="text-muted">
                {jira.data.auto_create ? `New risks get an issue in ${jira.data.project} automatically.` : "Automatic issue creation is off."}{" "}
                Status changes in Jira come back here (Done marks a risk treated).
                {jira.data.importing ? " Risks logged in Jira are imported." : ""}
              </span>
              {jira.data.last_synced_at && <span className="text-xs text-muted">Last sync {fmtDateTime(jira.data.last_synced_at)}</span>}
              {jira.data.last_error && <span className="w-full text-xs text-fail">{jira.data.last_error}</span>}
            </>
          ) : (
            <span className="text-muted">
              Track risk treatment in Jira: <Link href="/integrations?q=jira" className="font-medium text-ink underline">connect Jira</Link> and every new risk gets an issue, with status synced back.
            </span>
          )}
        </div>
      )}
      <div className="grid grid-cols-1 gap-6 [&>*]:min-w-0 lg:grid-cols-[280px_minmax(0,1fr)]">
        <Panel title="Open risks by score">
          <div className="flex gap-2">
            <span className="flex items-center text-xs text-muted [writing-mode:vertical-rl] rotate-180">Impact</span>
            <div className="flex-1">
              <div className="grid grid-cols-5 gap-1">
                {[5, 4, 3, 2, 1].flatMap((imp) =>
                  [1, 2, 3, 4, 5].map((lik) => {
                    const n = active.filter((r) => r.impact === imp && r.likelihood === lik).length;
                    return (
                      <div key={`${imp}-${lik}`} className={cx("flex aspect-square items-center justify-center rounded-sm text-xs font-semibold", CELL(imp * lik))} title={`Likelihood ${lik}, impact ${imp}`}>
                        {n || ""}
                      </div>
                    );
                  }),
                )}
              </div>
              <p className="mt-1.5 text-center text-xs text-muted">Likelihood</p>
            </div>
          </div>
        </Panel>

        <div className="rounded-lg border border-line bg-surface">
          {data.length ? (
            <div className={tbl.wrap}>
              <table className={tbl.table}>
                <thead>
                  <tr>
                    <th className={tbl.th}>Risk</th>
                    <th className={tbl.th}>Score</th>
                    <th className={tbl.th}>Treatment</th>
                    <th className={tbl.th}>Owner</th>
                    <th className={tbl.th}>Status</th>
                    {showJira && <th className={tbl.th}>Jira</th>}
                  </tr>
                </thead>
                <tbody>
                  {data.map((r) => {
                    const lvl = LEVEL(r.score);
                    return (
                      <tr key={r.id} className={`${tbl.row} cursor-pointer`} onClick={() => open(r)}>
                        <td className={tbl.td}>
                          <p className="font-medium">{r.title}</p>
                          {r.category && <p className="text-xs text-muted">{r.category}</p>}
                        </td>
                        <td className={tbl.td}><Badge tone={lvl.tone}>{r.score} {lvl.label}</Badge></td>
                        <td className={`${tbl.td} text-muted`}>{humanize(r.treatment)}</td>
                        <td className={`${tbl.td} text-muted`}>{r.owner?.full_name ?? "—"}</td>
                        <td className={`${tbl.td} text-muted`}>{humanize(r.status)}{r.review_date ? `, review ${fmtDate(r.review_date)}` : ""}</td>
                        {showJira && (
                          <td className={`${tbl.td} whitespace-nowrap`} onClick={(e) => e.stopPropagation()}>
                            {r.external_ref ? (
                              <a href={r.external_url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 font-medium text-ink hover:underline">
                                {r.external_ref} <ExternalLink size={12} aria-hidden />
                                {r.external_status && <span className="ml-1 font-normal text-muted">{r.external_status}</span>}
                              </a>
                            ) : canWrite && r.status !== "closed" && jira.data?.connected ? (
                              <Button size="sm" variant="ghost" busy={linking === r.id} onClick={() => createIssue(r)}>Create issue</Button>
                            ) : (
                              <span className="text-muted">—</span>
                            )}
                          </td>
                        )}
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          ) : (
            <Empty title="No risks recorded" action={canWrite && <Button onClick={() => open("new")}>Add risk</Button>}>
              ISO 27001 and SOC 2 both expect a documented risk assessment at least once a year.
            </Empty>
          )}
        </div>
      </div>

      <Drawer
        open={editing !== null}
        onClose={() => setEditing(null)}
        title={editing === "new" ? "Add risk" : "Edit risk"}
        footer={
          canWrite && (
            <>
              {editing !== "new" && <Button variant="danger" onClick={remove} className="mr-auto">Delete</Button>}
              <Button variant="ghost" onClick={() => setEditing(null)}>Cancel</Button>
              <Button onClick={save} busy={busy} disabled={!form.title}>Save risk</Button>
            </>
          )
        }
      >
        <FormError error={formError} />
        {editing && editing !== "new" && editing.external_ref && (
          <p className="rounded-md border border-line bg-paper px-3 py-2 text-sm">
            {editing.source === "jira" ? "Imported from" : "Tracked in"} Jira as{" "}
            <a href={editing.external_url} target="_blank" rel="noreferrer" className="font-medium text-ink underline">{editing.external_ref}</a>
            {editing.external_status && <> · {editing.external_status}</>}
            {editing.external_synced_at && <span className="text-muted">, checked {fmtDateTime(editing.external_synced_at)}</span>}
          </p>
        )}
        <Field label="Risk">{(id) => <Input id={id} value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} placeholder="e.g. Customer data exposed through misconfigured storage" />}</Field>
        <Field label="Description">{(id) => <Textarea id={id} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />}</Field>
        <Field label="Category">{(id) => <Input id={id} value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })} placeholder="e.g. Privacy, Cloud, People, Vendor" />}</Field>
        <div className="grid grid-cols-2 gap-3">
          {(["likelihood", "impact"] as const).map((k) => (
            <Field key={k} label={humanize(k)}>
              {(id) => (
                <Select id={id} value={form[k]} onChange={(e) => setForm({ ...form, [k]: Number(e.target.value) })}>
                  {[1, 2, 3, 4, 5].map((n) => <option key={n} value={n}>{n}</option>)}
                </Select>
              )}
            </Field>
          ))}
        </div>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Treatment">
            {(id) => (
              <Select id={id} value={form.treatment} onChange={(e) => setForm({ ...form, treatment: e.target.value })}>
                {["mitigate", "accept", "transfer", "avoid"].map((t) => <option key={t} value={t}>{humanize(t)}</option>)}
              </Select>
            )}
          </Field>
          <Field label="Status">
            {(id) => (
              <Select id={id} value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value })}>
                {["open", "treated", "closed"].map((t) => <option key={t} value={t}>{humanize(t)}</option>)}
              </Select>
            )}
          </Field>
        </div>
        <Field label="Treatment plan">{(id) => <Textarea id={id} value={form.treatment_plan} onChange={(e) => setForm({ ...form, treatment_plan: e.target.value })} />}</Field>
        <Field label="Linked controls" hint="Controls that reduce this risk.">{() => <ControlCodesPicker value={form.control_codes} onChange={(v) => setForm({ ...form, control_codes: v })} />}</Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Owner">{(id) => <MemberSelect id={id} value={form.owner_id} onChange={(v) => setForm({ ...form, owner_id: v })} />}</Field>
          <Field label="Review date">{(id) => <Input id={id} type="date" value={form.review_date} onChange={(e) => setForm({ ...form, review_date: e.target.value })} />}</Field>
        </div>
      </Drawer>
    </>
  );
}
