"use client";

import { FileArchive, FileSpreadsheet, Plus } from "lucide-react";
import { useEffect, useState } from "react";

import { MemberSelect } from "@/components/pickers";
import { Sampling } from "@/components/sampling";
import { useSession } from "@/components/session";
import { Badge, Button, Checkbox, Drawer, Empty, Field, FormError, Input, LoadError, Loading, PageHeader, Panel, Select, Tabs, Textarea, tbl, useToast } from "@/components/ui";
import { api, download, useApi } from "@/lib/api";
import { fmtDate, fmtDateTime } from "@/lib/format";
import type { Control, Evidence, Readiness } from "@/lib/types";

interface Req {
  id: string; number: number; ref: string; title: string; description: string; framework_code: string; requirement_ref: string;
  status: "open" | "submitted" | "accepted" | "rejected"; control: { id: string; code: string; title: string } | null;
  requested_by: string | null; assignee_id: string | null; assignee: string | null; due_date: string | null; created_at: string; updated_at: string;
  evidence: { id: string; title: string; kind: string; file_name: string; collected_at: string; control_id: string }[];
  comments?: { id: string; author: string; body: string; created_at: string }[];
}

const STATUS = { open: { label: "Open", tone: "prog" }, submitted: { label: "Evidence submitted", tone: "warn" }, accepted: { label: "Accepted", tone: "pass" }, rejected: { label: "Rejected", tone: "fail" } } as const;
type Filter = "all" | "open" | "submitted" | "accepted";

export default function AuditPage() {
  const { me, isAdmin } = useSession();
  const canRequest = isAdmin || me.role === "auditor";
  const [filter, setFilter] = useState<Filter>("all");
  const { data, error, loading, reload } = useApi<Req[]>("/audit/requests");
  const [creating, setCreating] = useState(false);
  const [openId, setOpenId] = useState<string | null>(null);
  const [view, setView] = useState<"requests" | "sampling">("requests");
  useEffect(() => {
    if (new URLSearchParams(window.location.search).get("view") === "sampling") setView("sampling");
  }, []);

  const rows = (data ?? []).filter((r) => filter === "all" || r.status === filter);
  return (
    <>
      <PageHeader
        title="Audit workspace"
        description="Auditors ask for evidence and test samples here; your team answers in one place. Every request, comment, test and download is in the audit log."
        actions={canRequest && view === "requests" && <Button onClick={() => setCreating(true)}><Plus size={14} aria-hidden /> New request</Button>}
      />
      <Exports />
      {canRequest && (
        <div role="group" aria-label="Workspace view" className="mb-4 inline-flex rounded-md border border-line bg-surface p-0.5">
          {(["requests", "sampling"] as const).map((v) => (
            <button key={v} type="button" aria-pressed={view === v} onClick={() => setView(v)}
              className={`rounded px-3 py-1.5 text-sm font-medium ${view === v ? "bg-ink text-white" : "text-muted hover:text-text"}`}>
              {v === "requests" ? "Evidence requests" : "Evidence sampling"}
            </button>
          ))}
        </div>
      )}
      {view === "sampling" && canRequest ? <Sampling /> : <>
      <Tabs<Filter>
        tabs={(["all", "open", "submitted", "accepted"] as Filter[]).map((f) => ({ value: f, label: `${f === "all" ? "All" : STATUS[f].label} (${(data ?? []).filter((r) => f === "all" || r.status === f).length})` }))}
        value={filter}
        onChange={setFilter}
      />
      <Panel flush>
        {loading && !data ? <Loading /> : error || !data ? <div className="p-4"><LoadError error={error ?? "Could not load"} retry={reload} /></div> : rows.length === 0 ? (
          <Empty title="No requests">{canRequest ? "Raise a request when you need specific evidence from the team." : "Your auditor's requests will appear here."}</Empty>
        ) : (
          <div className={tbl.wrap}>
            <table className={tbl.table}>
              <thead><tr><th className={tbl.th}>Request</th><th className={tbl.th}>Status</th><th className={tbl.th}>Assigned to</th><th className={tbl.th}>Due</th><th className={tbl.th}>Updated</th></tr></thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.id} className={`${tbl.row} cursor-pointer`} onClick={() => setOpenId(r.id)}>
                    <td className={tbl.td}><p className="font-medium"><span className="text-muted">{r.ref}</span> {r.title}</p><p className="text-xs text-muted">{[r.framework_code, r.requirement_ref, r.control?.code].filter(Boolean).join(" · ")}{r.requested_by && ` · from ${r.requested_by}`}</p></td>
                    <td className={tbl.td}><Badge tone={STATUS[r.status].tone}>{STATUS[r.status].label}</Badge></td>
                    <td className={tbl.td}>{r.assignee ?? <span className="text-muted">Unassigned</span>}</td>
                    <td className={tbl.td}>{fmtDate(r.due_date) || "—"}</td>
                    <td className={`${tbl.td} text-muted`}>{fmtDate(r.updated_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
      </>}
      <CreateDrawer open={creating} onClose={() => setCreating(false)} onCreated={() => { setCreating(false); reload(); }} />
      {openId && <RequestDrawer id={openId} onClose={() => setOpenId(null)} onChanged={reload} />}
    </>
  );
}

function Exports() {
  const { me, isAdmin } = useSession();
  const toast = useToast();
  const fws = useApi<Readiness[]>("/frameworks/readiness");
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  useEffect(() => {
    if (fws.data?.length && !code) setCode(fws.data.find((f) => f.code.startsWith("iso"))?.code ?? fws.data[0].code);
  }, [fws.data, code]);
  if (!fws.data?.length) return null;

  async function get(kind: "matrix" | "pack") {
    setBusy(kind);
    try {
      await download(kind === "matrix" ? `/audit/frameworks/${code}/matrix.xlsx` : `/audit/frameworks/${code}/evidence-pack.zip`, kind === "matrix" ? `${code}-matrix.xlsx` : `${code}-evidence.zip`);
    } catch (e) {
      toast(e instanceof Error ? e.message : "Download failed", "error");
    } finally {
      setBusy(null);
    }
  }

  return (
    <Panel className="mb-6">
      <div className="flex flex-wrap items-end gap-3">
        <Field label="Framework">
          {(id) => <Select id={id} value={code} onChange={(e) => setCode(e.target.value)} className="w-64">{fws.data!.map((f) => <option key={f.code} value={f.code}>{f.name}</option>)}</Select>}
        </Field>
        <Button variant="secondary" busy={busy === "matrix"} onClick={() => get("matrix")}><FileSpreadsheet size={14} aria-hidden /> {code.startsWith("iso") ? "Statement of Applicability" : "Requirements matrix"} (.xlsx)</Button>
        {(isAdmin || me.role === "auditor") && (
          <Button variant="secondary" busy={busy === "pack"} onClick={() => get("pack")}><FileArchive size={14} aria-hidden /> Evidence pack (.zip)</Button>
        )}
        <p className="basis-full text-xs text-muted">The evidence pack contains every current evidence item for the framework&apos;s controls, with a manifest of SHA-256 hashes recorded in the audit log.</p>
      </div>
    </Panel>
  );
}

function CreateDrawer({ open, onClose, onCreated }: { open: boolean; onClose: () => void; onCreated: () => void }) {
  const controls = useApi<Control[]>(open ? "/controls" : null);
  const fws = useApi<Readiness[]>(open ? "/frameworks/readiness" : null);
  const [form, setForm] = useState({ title: "", description: "", framework_code: "", requirement_ref: "", control_id: "", assignee_id: "", due_date: "" });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function save() {
    setBusy(true);
    setError(null);
    try {
      await api("/audit/requests", { method: "POST", json: { ...form, control_id: form.control_id || null, assignee_id: form.assignee_id || null, due_date: form.due_date || null } });
      setForm({ title: "", description: "", framework_code: "", requirement_ref: "", control_id: "", assignee_id: "", due_date: "" });
      onCreated();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Drawer open={open} onClose={onClose} title="Request evidence" footer={<><Button variant="secondary" onClick={onClose}>Cancel</Button><Button busy={busy} onClick={save}>Send request</Button></>}>
      <FormError error={error} />
      <Field label="What do you need?">{(id) => <Input id={id} required placeholder="Last two quarterly access reviews" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} />}</Field>
      <Field label="Details">{(id) => <Textarea id={id} placeholder="Period covered, format, sample size…" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />}</Field>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Framework">{(id) => <Select id={id} value={form.framework_code} onChange={(e) => setForm({ ...form, framework_code: e.target.value })}><option value="">Any</option>{(fws.data ?? []).map((f) => <option key={f.code} value={f.code}>{f.short_name || f.name}</option>)}</Select>}</Field>
        <Field label="Clause or requirement">{(id) => <Input id={id} placeholder="A.5.18" value={form.requirement_ref} onChange={(e) => setForm({ ...form, requirement_ref: e.target.value })} />}</Field>
      </div>
      <Field label="Related control">{(id) => <Select id={id} value={form.control_id} onChange={(e) => setForm({ ...form, control_id: e.target.value })}><option value="">None</option>{(controls.data ?? []).map((c) => <option key={c.id} value={c.id}>{c.code} {c.title}</option>)}</Select>}</Field>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Assign to">{(id) => <MemberSelect id={id} value={form.assignee_id} onChange={(v) => setForm({ ...form, assignee_id: v })} />}</Field>
        <Field label="Due">{(id) => <Input id={id} type="date" value={form.due_date} onChange={(e) => setForm({ ...form, due_date: e.target.value })} />}</Field>
      </div>
    </Drawer>
  );
}

function RequestDrawer({ id, onClose, onChanged }: { id: string; onClose: () => void; onChanged: () => void }) {
  const { me, isAdmin, canWrite } = useSession();
  const canDecide = isAdmin || me.role === "auditor";
  const { data, error, loading, reload, setData } = useApi<Req>(`/audit/requests/${id}`);
  const [comment, setComment] = useState("");
  const [picking, setPicking] = useState(false);
  const [rejectNote, setRejectNote] = useState("");
  const [formError, setFormError] = useState<string | null>(null);

  async function act(fn: () => Promise<Req>) {
    setFormError(null);
    try {
      setData(await fn());
      onChanged();
    } catch (e) {
      setFormError(e instanceof Error ? e.message : "Failed");
    }
  }

  return (
    <Drawer open onClose={onClose} title={data ? `${data.ref} ${data.title}` : "Request"} wide>
      {loading && !data ? <Loading /> : error || !data ? <LoadError error={error ?? "Could not load"} retry={reload} /> : (
        <>
          <FormError error={formError} />
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <Badge tone={STATUS[data.status].tone}>{STATUS[data.status].label}</Badge>
            {data.control && <Badge tone="ink">{data.control.code} {data.control.title}</Badge>}
            {data.due_date && <span className="text-muted">Due {fmtDate(data.due_date)}</span>}
          </div>
          {data.description && <p className="whitespace-pre-line text-sm">{data.description}</p>}

          <div>
            <p className="mb-2 text-[13px] font-semibold">Evidence</p>
            {data.evidence.length === 0 ? <p className="text-sm text-muted">Nothing attached yet.</p> : (
              <ul className="space-y-1 text-sm">
                {data.evidence.map((e) => (
                  <li key={e.id} className="flex items-center gap-2">
                    {e.kind === "file" ? (
                      <a className="underline" href={`/api/evidence/${e.id}/download`}>{e.title}</a>
                    ) : <span>{e.title}</span>}
                    <span className="text-xs text-muted">{e.kind} · {fmtDate(e.collected_at)}</span>
                  </li>
                ))}
              </ul>
            )}
            {canWrite && data.status !== "accepted" && <Button className="mt-2" size="sm" variant="secondary" onClick={() => setPicking(true)}>Attach evidence</Button>}
          </div>

          {canDecide && data.status === "submitted" && (
            <div className="space-y-2 rounded-md border border-line p-3">
              <p className="text-[13px] font-semibold">Decision</p>
              <Textarea placeholder="What's missing (required to reject)" value={rejectNote} onChange={(e) => setRejectNote(e.target.value)} aria-label="Decision comment" />
              <div className="flex gap-2">
                <Button size="sm" onClick={() => act(() => api(`/audit/requests/${id}/decision`, { method: "POST", json: { decision: "accepted", comment: rejectNote } }))}>Accept</Button>
                <Button size="sm" variant="danger" onClick={() => act(() => api(`/audit/requests/${id}/decision`, { method: "POST", json: { decision: "rejected", comment: rejectNote } }))}>Send back</Button>
              </div>
            </div>
          )}

          <div>
            <p className="mb-2 text-[13px] font-semibold">Conversation</p>
            <ul className="space-y-3">
              {(data.comments ?? []).map((c) => (
                <li key={c.id} className="rounded-md bg-paper px-3 py-2 text-sm">
                  <p className="text-xs text-muted"><span className="font-medium text-text">{c.author}</span> · {fmtDateTime(c.created_at)}</p>
                  <p className="mt-1 whitespace-pre-line">{c.body}</p>
                </li>
              ))}
            </ul>
            <form className="mt-3 space-y-2" onSubmit={(e) => { e.preventDefault(); if (comment.trim()) act(() => api(`/audit/requests/${id}/comments`, { method: "POST", json: { body: comment } })).then(() => setComment("")); }}>
              <Textarea placeholder="Write a comment" value={comment} onChange={(e) => setComment(e.target.value)} aria-label="Comment" />
              <Button type="submit" size="sm" variant="secondary">Comment</Button>
            </form>
          </div>
          {picking && <EvidencePicker request={data} onClose={() => setPicking(false)} onSubmit={(ids, note) => act(() => api(`/audit/requests/${id}/submit`, { method: "POST", json: { evidence_ids: ids, note } })).then(() => setPicking(false))} />}
        </>
      )}
    </Drawer>
  );
}

function EvidencePicker({ request, onClose, onSubmit }: { request: Req; onClose: () => void; onSubmit: (ids: string[], note: string) => void }) {
  const controls = useApi<Control[]>("/controls");
  const [controlId, setControlId] = useState(request.control?.id ?? "");
  const detail = useApi<{ evidence: Evidence[] }>(controlId ? `/controls/${controlId}` : null);
  const [chosen, setChosen] = useState<string[]>([]);
  const [note, setNote] = useState("");

  return (
    <div className="fixed inset-0 z-[55] flex items-center justify-center bg-text/30 p-4" role="dialog" aria-modal="true" aria-label="Attach evidence">
      <div className="w-full max-w-lg space-y-4 rounded-lg bg-surface p-5 shadow-xl">
        <h3 className="font-semibold">Attach evidence</h3>
        <Field label="Control">{(id) => <Select id={id} value={controlId} onChange={(e) => { setControlId(e.target.value); setChosen([]); }}><option value="">Choose a control</option>{(controls.data ?? []).map((c) => <option key={c.id} value={c.id}>{c.code} {c.title}</option>)}</Select>}</Field>
        <div className="max-h-64 space-y-2 overflow-y-auto">
          {controlId && detail.data?.evidence.length === 0 && <p className="text-sm text-muted">No evidence on this control yet. Add it on the control page first.</p>}
          {detail.data?.evidence.map((e) => (
            <Checkbox key={e.id} label={e.title} hint={`${e.kind} · ${fmtDate(e.collected_at)}`} checked={chosen.includes(e.id)} onChange={(v) => setChosen(v ? [...chosen, e.id] : chosen.filter((x) => x !== e.id))} />
          ))}
        </div>
        <Textarea placeholder="Note for the auditor (optional)" value={note} onChange={(e) => setNote(e.target.value)} aria-label="Note" />
        <div className="flex justify-end gap-2">
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
          <Button disabled={!chosen.length} onClick={() => onSubmit(chosen, note)}>Submit {chosen.length || ""}</Button>
        </div>
      </div>
    </div>
  );
}
