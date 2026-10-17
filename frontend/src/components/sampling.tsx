"use client";

import { AlertTriangle, Bot, Download, FileSpreadsheet, Plus, Shuffle } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { api, download, useApi } from "@/lib/api";
import { fmtDate, fmtDateTime } from "@/lib/format";
import type { Readiness } from "@/lib/types";

import { VERDICT } from "./evidence";
import { Badge, Button, Drawer, Empty, Field, FormError, Input, LoadError, Loading, Panel, Select, Textarea, tbl, useToast } from "./ui";

interface SampleSummary {
  id: string; name: string; framework_code: string; period_start: string; period_end: string; seed: string;
  population: number; size: number; pending: number; pass: number; exception: number; created_at: string; created_by: string;
}
interface Item {
  id: string; control_code: string; evidence_title: string; result: "pending" | "pass" | "exception"; note: string;
  tested_by: string | null; tested_at: string | null;
  evidence: null | {
    id: string; control_id: string; kind: string; trust: string; file_name: string; url: string; description: string;
    collected_at: string; uploaded_by: string | null; reviewed_by: string | null; self_approved: boolean;
    changed_since_sampling: boolean; warnings: string[]; ai_verdict: keyof typeof VERDICT | null; ai_summary: string | null;
  };
}
type Sample = SampleSummary & { items: Item[] };

const RESULT = { pending: { label: "Not tested", tone: "idle" }, pass: { label: "Pass", tone: "pass" }, exception: { label: "Exception", tone: "fail" } } as const;
const TRUST = { automated: "Collected automatically", platform: "Generated in the platform", uploaded: "Uploaded" } as Record<string, string>;

export function Sampling() {
  const { data, error, loading, reload } = useApi<SampleSummary[]>("/audit/samples");
  const [creating, setCreating] = useState(false);
  const [open, setOpen] = useState<string | null>(null);

  return (
    <>
      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <p className="max-w-[72ch] text-sm text-muted">
          Pick a random sample of approved evidence to test in depth, the way auditors work. The selection is reproducible from its seed, and
          each result is recorded with who tested it and when.
        </p>
        <Button onClick={() => setCreating(true)}><Plus size={14} aria-hidden /> New sample</Button>
      </div>
      <Panel flush>
        {loading && !data ? <Loading /> : error || !data ? <div className="p-4"><LoadError error={error ?? "Could not load"} retry={reload} /></div> : data.length === 0 ? (
          <Empty title="No samples yet" action={<Button onClick={() => setCreating(true)}><Shuffle size={14} aria-hidden /> Draw a sample</Button>}>
            Sampling 25 items across controls is a common starting point for a period.
          </Empty>
        ) : (
          <div className={tbl.wrap}>
            <table className={tbl.table}>
              <thead><tr><th className={tbl.th}>Sample</th><th className={tbl.th}>Period</th><th className={tbl.th}>Size</th><th className={tbl.th}>Results</th></tr></thead>
              <tbody>
                {data.map((s) => (
                  <tr key={s.id} className={`${tbl.row} cursor-pointer`} onClick={() => setOpen(s.id)}>
                    <td className={tbl.td}><p className="font-medium">{s.name}</p><p className="text-xs text-muted">{s.framework_code || "All frameworks"} · by {s.created_by} on {fmtDate(s.created_at)}</p></td>
                    <td className={`${tbl.td} text-sm`}>{fmtDate(s.period_start)} to {fmtDate(s.period_end)}</td>
                    <td className={`${tbl.td} text-sm`}>{s.size} of {s.population}</td>
                    <td className={tbl.td}>
                      <div className="flex flex-wrap gap-1">
                        {s.pass > 0 && <Badge tone="pass">{s.pass} pass</Badge>}
                        {s.exception > 0 && <Badge tone="fail">{s.exception} exceptions</Badge>}
                        {s.pending > 0 && <Badge>{s.pending} to test</Badge>}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
      {creating && <NewSample onClose={() => setCreating(false)} onCreated={(id) => { setCreating(false); reload(); setOpen(id); }} />}
      {open && <SampleDrawer id={open} onClose={() => setOpen(null)} onChanged={reload} />}
    </>
  );
}

function NewSample({ onClose, onCreated }: { onClose: () => void; onCreated: (id: string) => void }) {
  const fws = useApi<Readiness[]>("/frameworks/readiness");
  const today = new Date();
  const iso = (d: Date) => d.toISOString().slice(0, 10);
  const [form, setForm] = useState({
    name: `Sample ${today.toLocaleDateString("en-IN", { month: "short", year: "numeric" })}`, framework_code: "",
    period_start: iso(new Date(today.getTime() - 90 * 864e5)), period_end: iso(today), size: 25, method: "per_control",
  });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function save() {
    setBusy(true);
    setError(null);
    try {
      const s = await api<Sample>("/audit/samples", { method: "POST", json: form });
      onCreated(s.id);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed");
      setBusy(false);
    }
  }

  return (
    <Drawer open onClose={onClose} title="Draw an evidence sample" footer={<><Button variant="ghost" onClick={onClose}>Cancel</Button><Button busy={busy} onClick={save}><Shuffle size={14} aria-hidden /> Draw sample</Button></>}>
      <FormError error={error} />
      <Field label="Name">{(id) => <Input id={id} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />}</Field>
      <Field label="Framework">
        {(id) => (
          <Select id={id} value={form.framework_code} onChange={(e) => setForm({ ...form, framework_code: e.target.value })}>
            <option value="">All frameworks</option>
            {(fws.data ?? []).map((f) => <option key={f.code} value={f.code}>{f.short_name}</option>)}
          </Select>
        )}
      </Field>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Evidence collected from">{(id) => <Input id={id} type="date" value={form.period_start} onChange={(e) => setForm({ ...form, period_start: e.target.value })} />}</Field>
        <Field label="to">{(id) => <Input id={id} type="date" value={form.period_end} onChange={(e) => setForm({ ...form, period_end: e.target.value })} />}</Field>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Sample size">{(id) => <Input id={id} type="number" min={1} max={200} value={form.size} onChange={(e) => setForm({ ...form, size: Number(e.target.value) })} />}</Field>
        <Field label="Method">
          {(id) => (
            <Select id={id} value={form.method} onChange={(e) => setForm({ ...form, method: e.target.value })}>
              <option value="per_control">At least one per control</option>
              <option value="random">Simple random</option>
            </Select>
          )}
        </Field>
      </div>
      <p className="text-xs text-muted">Only approved evidence is sampled. The random seed is saved with the sample so anyone can re-perform the selection.</p>
    </Drawer>
  );
}

function SampleDrawer({ id, onClose, onChanged }: { id: string; onClose: () => void; onChanged: () => void }) {
  const toast = useToast();
  const { data: s, error, loading, reload } = useApi<Sample>(`/audit/samples/${id}`);
  const [editing, setEditing] = useState<string | null>(null);
  const [note, setNote] = useState("");

  async function record(item: Item, result: Item["result"], text = "") {
    try {
      await api(`/audit/samples/${id}/items/${item.id}`, { method: "PUT", json: { result, note: text } });
      setEditing(null);
      setNote("");
      reload();
      onChanged();
    } catch (e) {
      toast(e instanceof Error ? e.message : "Failed", "error");
    }
  }

  return (
    <Drawer open onClose={onClose} title={s?.name ?? "Sample"} wide
      footer={s && <Button variant="secondary" onClick={() => download(`/audit/samples/${id}/export.xlsx`, `sample-${s.name}.xlsx`).catch((e) => toast(e.message, "error"))}><FileSpreadsheet size={14} aria-hidden /> Export to Excel</Button>}>
      {loading && !s ? <Loading /> : error || !s ? <LoadError error={error ?? "Could not load"} /> : (
        <>
          <div className="grid gap-3 sm:grid-cols-3">
            <div className="rounded-lg border border-line p-3"><p className="text-xl font-bold">{s.size}<span className="text-sm font-normal text-muted"> of {s.population}</span></p><p className="text-xs text-muted">Items sampled</p></div>
            <div className="rounded-lg border border-line p-3"><p className="text-xl font-bold text-pass">{s.pass}</p><p className="text-xs text-muted">Passed</p></div>
            <div className="rounded-lg border border-line p-3"><p className={`text-xl font-bold ${s.exception ? "text-fail" : ""}`}>{s.exception}</p><p className="text-xs text-muted">Exceptions</p></div>
          </div>
          <p className="text-xs text-muted">Evidence collected {fmtDate(s.period_start)} to {fmtDate(s.period_end)} · seed <span className="font-mono">{s.seed}</span></p>
          <ul className="space-y-3">
            {s.items.map((i) => {
              const e = i.evidence;
              return (
                <li key={i.id} className="rounded-lg border border-line p-3 text-sm">
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <div className="min-w-0">
                      <p className="font-medium"><span className="text-muted">{i.control_code}</span> {i.evidence_title}</p>
                      {e ? (
                        <p className="mt-0.5 text-xs text-muted">
                          {TRUST[e.trust]} · {fmtDate(e.collected_at)}{e.uploaded_by ? ` · added by ${e.uploaded_by}` : ""}
                          {e.reviewed_by ? ` · approved by ${e.reviewed_by}${e.self_approved ? " (self-approved)" : ""}` : ""}
                        </p>
                      ) : <p className="mt-0.5 text-xs text-fail">The evidence was deleted after sampling.</p>}
                    </div>
                    <Badge tone={RESULT[i.result].tone}>{RESULT[i.result].label}</Badge>
                  </div>
                  {e?.changed_since_sampling && <p className="mt-1 flex items-center gap-1 text-xs text-fail"><AlertTriangle size={13} aria-hidden /> The file changed after it was sampled.</p>}
                  {e?.warnings.map((w) => <p key={w} className="mt-1 flex items-start gap-1 text-xs text-warn"><AlertTriangle size={13} className="mt-px shrink-0" aria-hidden /> {w}</p>)}
                  {e?.ai_verdict && <p className="mt-1 flex items-start gap-1 text-xs text-muted"><Bot size={13} className="mt-px shrink-0" aria-hidden /> AI check: {VERDICT[e.ai_verdict].label}{e.ai_summary ? `. ${e.ai_summary}` : ""}</p>}
                  <div className="mt-2 flex flex-wrap items-center gap-2">
                    {e?.file_name && <a href={`/api/evidence/${e.id}/download`} className="inline-flex items-center gap-1 text-xs font-medium text-ink hover:underline"><Download size={13} aria-hidden /> Open file</a>}
                    {e?.url && <a href={e.url} target="_blank" rel="noreferrer" className="text-xs font-medium text-ink hover:underline">Open link</a>}
                    {e && <Link href={`/controls/${e.control_id}`} className="text-xs font-medium text-ink hover:underline">Control</Link>}
                    <span className="flex-1" />
                    {editing === i.id ? null : (
                      <>
                        <Button size="sm" variant="secondary" onClick={() => record(i, "pass")}>Pass</Button>
                        <Button size="sm" variant="danger" onClick={() => { setEditing(i.id); setNote(i.note); }}>Exception</Button>
                      </>
                    )}
                  </div>
                  {editing === i.id && (
                    <div className="mt-2 space-y-2">
                      <Textarea aria-label="Describe the exception" placeholder="What's wrong with this evidence?" value={note} onChange={(ev) => setNote(ev.target.value)} className="min-h-[60px]" />
                      <div className="flex gap-2">
                        <Button size="sm" variant="danger" disabled={!note.trim()} onClick={() => record(i, "exception", note)}>Record exception</Button>
                        <Button size="sm" variant="ghost" onClick={() => setEditing(null)}>Cancel</Button>
                      </div>
                    </div>
                  )}
                  {i.note && editing !== i.id && <p className="mt-2 rounded bg-paper px-2 py-1 text-xs"><span className="text-muted">Tester notes:</span> {i.note}</p>}
                  {i.tested_by && <p className="mt-1 text-xs text-muted">Tested by {i.tested_by} on {i.tested_at ? fmtDateTime(i.tested_at) : ""}</p>}
                </li>
              );
            })}
          </ul>
        </>
      )}
    </Drawer>
  );
}
