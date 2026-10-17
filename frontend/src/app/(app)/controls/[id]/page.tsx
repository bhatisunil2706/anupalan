"use client";

import { Download, ExternalLink, FileText, Link2, Pencil, StickyNote, Trash2, Zap } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import { TaskDrawer } from "@/components/task-drawer";

import { MemberSelect } from "@/components/pickers";
import { useSession } from "@/components/session";
import {
  Badge,
  Button,
  Drawer,
  Field,
  FormError,
  HealthBadge,
  Input,
  LoadError,
  Loading,
  Panel,
  Select,
  Tabs,
  Textarea,
  useToast,
} from "@/components/ui";
import { api, useApi } from "@/lib/api";
import { bytes, fmtDate, fmtDateTime, humanize } from "@/lib/format";
import type { Control, Evidence, Task } from "@/lib/types";

interface Detail {
  control: Control;
  implementation_notes: string;
  na_justification: string;
  evidence_hint: string;
  requirements: { framework: string; framework_code: string; ref: string; title: string; guidance: string }[];
  evidence: Evidence[];
  tasks: Task[];
  tests: { key: string; title: string; status: string; run_at: string; summary: string }[];
}

const KIND_ICON = { file: FileText, link: Link2, note: StickyNote, automated: Zap, policy: FileText };

export default function ControlDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { canWrite } = useSession();
  const toast = useToast();
  const { data, error, loading, reload } = useApi<Detail>(`/controls/${id}`);
  const [notes, setNotes] = useState("");
  const [naText, setNaText] = useState("");
  const [addingEvidence, setAddingEvidence] = useState(false);
  const [addingTask, setAddingTask] = useState(false);
  const [editingDetails, setEditingDetails] = useState(false);
  const [fwTab, setFwTab] = useState("");

  useEffect(() => {
    if (data) {
      setNotes(data.implementation_notes);
      setNaText(data.na_justification);
      setFwTab((t) => t || data.requirements[0]?.framework || "");
    }
  }, [data]);

  if (loading && !data) return <Loading />;
  if (error || !data) return <LoadError error={error ?? "Could not load"} retry={reload} />;
  const c = data.control;

  async function patch(body: Record<string, unknown>, msg = "Saved") {
    try {
      await api(`/controls/${id}`, { method: "PATCH", json: body });
      toast(msg);
      reload();
    } catch (e) {
      toast(e instanceof Error ? e.message : "Failed", "error");
    }
  }

  async function removeEvidence(ev: Evidence) {
    if (!confirm(`Delete "${ev.title}"?`)) return;
    await api(`/evidence/${ev.id}`, { method: "DELETE" });
    toast("Evidence deleted");
    reload();
  }

  const fwNames = [...new Set(data.requirements.map((r) => r.framework))];
  const today = new Date().toISOString().slice(0, 10);

  return (
    <>
      <nav className="mb-3 text-sm text-muted">
        <Link href="/controls" className="hover:underline">Controls</Link> / {c.code}
      </nav>
      <header className="mb-6 flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <p className="text-sm font-semibold text-muted">{c.code} · {c.category}</p>
          <h1 className="mt-0.5 text-[22px] font-bold tracking-[-0.01em]">{c.title}</h1>
          <p className="mt-2 max-w-[72ch] text-sm leading-relaxed text-muted">{c.description}</p>
        </div>
        <div className="flex items-center gap-2">
          {canWrite && (
            <Button size="sm" variant="secondary" onClick={() => setEditingDetails(true)}>
              <Pencil size={14} aria-hidden /> Edit
            </Button>
          )}
          <HealthBadge health={c.health} />
        </div>
      </header>

      <div className="grid grid-cols-1 gap-6 [&>*]:min-w-0 lg:grid-cols-[minmax(0,1fr)_320px]">
        <div className="space-y-6">
          <Panel
            title="Evidence"
            actions={canWrite && <Button size="sm" onClick={() => setAddingEvidence(true)}>Add evidence</Button>}
            flush
          >
            {data.evidence_hint && <p className="border-b border-line bg-paper/50 px-4 py-2.5 text-xs text-muted">Auditors expect: {data.evidence_hint}</p>}
            {data.evidence.length ? (
              <ul>
                {data.evidence.map((ev) => {
                  const Icon = KIND_ICON[ev.kind] ?? FileText;
                  const expired = ev.valid_until !== null && ev.valid_until < today;
                  return (
                    <li key={ev.id} className="flex items-start gap-3 border-b border-line px-4 py-3 last:border-0">
                      <Icon size={16} className="mt-0.5 shrink-0 text-muted" aria-hidden />
                      <div className="min-w-0 flex-1">
                        <p className="text-sm font-medium">{ev.title}</p>
                        {ev.description && <p className="mt-0.5 text-sm text-muted">{ev.description}</p>}
                        <p className="mt-1 text-xs text-muted">
                          {ev.kind === "automated" ? "Collected automatically" : ev.uploaded_by ? `Added by ${ev.uploaded_by.full_name}` : humanize(ev.kind)}
                          {" on "}{fmtDate(ev.collected_at)}
                          {ev.file_name && `, ${ev.file_name} (${bytes(ev.size_bytes)})`}
                        </p>
                      </div>
                      <div className="flex shrink-0 items-center gap-1">
                        <Badge tone={expired ? "fail" : "pass"}>{expired ? "Expired" : ev.valid_until ? `Valid to ${fmtDate(ev.valid_until)}` : "No expiry"}</Badge>
                        {ev.file_name && (
                          <a href={`/api/evidence/${ev.id}/download`} className="rounded p-1.5 text-muted hover:bg-ink-50 hover:text-text" aria-label="Download">
                            <Download size={15} />
                          </a>
                        )}
                        {ev.url && (
                          <a href={ev.url} target="_blank" rel="noreferrer" className="rounded p-1.5 text-muted hover:bg-ink-50 hover:text-text" aria-label="Open link">
                            <ExternalLink size={15} />
                          </a>
                        )}
                        {canWrite && !["automated", "policy"].includes(ev.kind) && (
                          <button onClick={() => removeEvidence(ev)} className="rounded p-1.5 text-muted hover:bg-fail-50 hover:text-fail" aria-label="Delete evidence">
                            <Trash2 size={15} />
                          </button>
                        )}
                      </div>
                    </li>
                  );
                })}
              </ul>
            ) : (
              <p className="px-4 py-6 text-sm text-muted">No evidence yet. Upload a file, add a link, or connect an integration that collects it.</p>
            )}
          </Panel>

          {data.tests.length > 0 && (
            <Panel title="Automated checks" flush>
              <ul>
                {data.tests.map((t) => (
                  <li key={t.key} className="flex items-start gap-3 border-b border-line px-4 py-3 last:border-0">
                    <Badge tone={t.status === "pass" ? "pass" : "fail"}>{t.status === "pass" ? "Pass" : t.status === "fail" ? "Fail" : "Error"}</Badge>
                    <div className="min-w-0 flex-1 text-sm">
                      <p className="font-medium">{t.title}</p>
                      <p className="text-muted">{t.summary}</p>
                    </div>
                    <span className="text-xs text-muted">{fmtDateTime(t.run_at)}</span>
                  </li>
                ))}
              </ul>
            </Panel>
          )}

          <Panel title="Framework requirements this control covers">
            {fwNames.length ? (
              <>
                <Tabs tabs={fwNames.map((f) => ({ value: f, label: f }))} value={fwTab} onChange={setFwTab} />
                <ul className="space-y-3">
                  {data.requirements.filter((r) => r.framework === fwTab).map((r) => (
                    <li key={r.ref} className="text-sm">
                      <Link href={`/frameworks/${r.framework_code}`} className="font-medium hover:underline">
                        {r.ref} {r.title}
                      </Link>
                      <p className="mt-0.5 max-w-[72ch] leading-relaxed text-muted">{r.guidance}</p>
                    </li>
                  ))}
                </ul>
              </>
            ) : (
              <p className="text-sm text-muted">Not mapped to any enabled framework.</p>
            )}
          </Panel>

          <Panel title="Implementation notes">
            <Textarea
              aria-label="Implementation notes"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              disabled={!canWrite}
              placeholder="How this control works in your company: tools, process, who does what."
              className="min-h-[120px]"
            />
            {canWrite && notes !== data.implementation_notes && (
              <div className="mt-2 flex justify-end">
                <Button size="sm" onClick={() => patch({ implementation_notes: notes }, "Notes saved")}>Save notes</Button>
              </div>
            )}
          </Panel>
        </div>

        <aside className="space-y-6">
          <Panel title="Details">
            <div className="space-y-4">
              <Field label="Implementation status">
                {(fid) => (
                  <Select
                    id={fid}
                    value={c.status}
                    disabled={!canWrite}
                    onChange={(e) => {
                      if (e.target.value === "not_applicable" && !naText.trim()) {
                        toast("Add a justification below first, then mark it not applicable", "error");
                        return;
                      }
                      patch({ status: e.target.value, na_justification: naText }, "Status updated");
                    }}
                  >
                    <option value="not_started">Not started</option>
                    <option value="in_progress">In progress</option>
                    <option value="implemented">Implemented</option>
                    <option value="not_applicable">Not applicable</option>
                  </Select>
                )}
              </Field>
              <Field label="Owner" hint={canWrite ? "The person responsible. They get an email when you assign them." : undefined}>
                {(fid) => (
                  <MemberSelect
                    id={fid}
                    value={c.owner?.id ?? ""}
                    disabled={!canWrite}
                    onChange={(v) => patch(v ? { owner_id: v } : { clear_owner: true }, "Owner updated")}
                  />
                )}
              </Field>
              <Field label="Next review">
                {(fid) => (
                  <Input
                    id={fid}
                    type="date"
                    disabled={!canWrite}
                    value={c.next_review_date ?? ""}
                    onChange={(e) => patch({ next_review_date: e.target.value || null }, "Review date updated")}
                  />
                )}
              </Field>
              <Field label="Not applicable justification" hint="Required by auditors if you mark this control not applicable.">
                {(fid) => (
                  <Textarea
                    id={fid}
                    value={naText}
                    disabled={!canWrite}
                    onChange={(e) => setNaText(e.target.value)}
                    onBlur={() => naText !== data.na_justification && patch({ na_justification: naText })}
                    className="min-h-[64px]"
                  />
                )}
              </Field>
              <p className="text-xs text-muted">Review frequency: {c.frequency}. New evidence stays valid for one review cycle unless you set a date.</p>
            </div>
          </Panel>

          <Panel title="Tasks" actions={canWrite && <Button size="sm" variant="secondary" onClick={() => setAddingTask(true)}>Add task</Button>} flush>
            {data.tasks.length ? (
              <ul>
                {data.tasks.map((t) => (
                  <li key={t.id} className="border-b border-line px-4 py-2.5 text-sm last:border-0">
                    <p className={t.status === "done" ? "text-muted line-through" : ""}>{t.title}</p>
                    <p className="text-xs text-muted">
                      {t.assignee?.full_name ?? "Unassigned"}{t.due_date ? `, due ${fmtDate(t.due_date)}` : ""}
                    </p>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="px-4 py-4 text-sm text-muted">No tasks for this control.</p>
            )}
          </Panel>
        </aside>
      </div>

      <EditControl
        open={editingDetails}
        control={c}
        onClose={() => setEditingDetails(false)}
        onSaved={() => { setEditingDetails(false); toast("Control updated"); reload(); }}
      />
      <AddEvidence open={addingEvidence} controlId={id} onClose={() => setAddingEvidence(false)} onDone={() => { setAddingEvidence(false); toast("Evidence added"); reload(); }} />
      <TaskDrawer open={addingTask} controlId={id} onClose={() => setAddingTask(false)} onDone={() => { setAddingTask(false); toast("Task added"); reload(); }} />
    </>
  );
}

function AddEvidence({ open, controlId, onClose, onDone }: { open: boolean; controlId: string; onClose: () => void; onDone: () => void }) {
  const [kind, setKind] = useState<"file" | "link" | "note">("file");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [url, setUrl] = useState("");
  const [validUntil, setValidUntil] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function save() {
    setBusy(true);
    setError(null);
    const fd = new FormData();
    fd.set("title", title);
    fd.set("kind", kind);
    fd.set("description", description);
    if (url) fd.set("url", url);
    if (validUntil) fd.set("valid_until", validUntil);
    if (file) fd.set("file", file);
    try {
      await api(`/controls/${controlId}/evidence`, { method: "POST", body: fd });
      setTitle(""); setDescription(""); setUrl(""); setFile(null); setValidUntil("");
      onDone();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Upload failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Drawer open={open} onClose={onClose} title="Add evidence" footer={<><Button variant="ghost" onClick={onClose}>Cancel</Button><Button onClick={save} busy={busy} disabled={!title}>Add evidence</Button></>}>
      <FormError error={error} />
      <Tabs tabs={[{ value: "file", label: "File" }, { value: "link", label: "Link" }, { value: "note", label: "Note" }]} value={kind} onChange={setKind} />
      <Field label="Title">{(id) => <Input id={id} value={title} onChange={(e) => setTitle(e.target.value)} placeholder="e.g. Q3 access review sign-off" />}</Field>
      {kind === "file" && (
        <Field label="File" hint="PDF, images, Office documents, CSV, JSON or ZIP. Up to 25 MB.">
          {(id) => <input id={id} type="file" onChange={(e) => setFile(e.target.files?.[0] ?? null)} className="block w-full text-sm file:mr-3 file:rounded-md file:border file:border-line file:bg-surface file:px-3 file:py-1.5 file:text-sm" />}
        </Field>
      )}
      {kind === "link" && <Field label="URL">{(id) => <Input id={id} type="url" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://" />}</Field>}
      <Field label={kind === "note" ? "Note" : "Description (optional)"}>{(id) => <Textarea id={id} value={description} onChange={(e) => setDescription(e.target.value)} />}</Field>
      <Field label="Valid until" hint="Leave empty to use the control's review frequency.">{(id) => <Input id={id} type="date" value={validUntil} onChange={(e) => setValidUntil(e.target.value)} />}</Field>
    </Drawer>
  );
}

const FREQUENCIES = [
  ["continuous", "Continuous"],
  ["monthly", "Monthly"],
  ["quarterly", "Quarterly"],
  ["semiannual", "Every 6 months"],
  ["annual", "Yearly"],
  ["once", "Once"],
] as const;

function EditControl({ open, control, onClose, onSaved }: { open: boolean; control: Control; onClose: () => void; onSaved: () => void }) {
  const [form, setForm] = useState({ title: "", description: "", category: "", frequency: "annual", owner: "" });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (open) {
      setForm({ title: control.title, description: control.description, category: control.category, frequency: control.frequency, owner: control.owner?.id ?? "" });
      setError(null);
    }
  }, [open, control]);

  async function save() {
    setBusy(true);
    setError(null);
    const json: Record<string, unknown> = {};
    if (form.title !== control.title) json.title = form.title;
    if (form.description !== control.description) json.description = form.description;
    if (form.category !== control.category) json.category = form.category;
    if (form.frequency !== control.frequency) json.frequency = form.frequency;
    if (form.owner !== (control.owner?.id ?? "")) Object.assign(json, form.owner ? { owner_id: form.owner } : { clear_owner: true });
    if (!Object.keys(json).length) return onClose();
    try {
      await api(`/controls/${control.id}`, { method: "PATCH", json });
      onSaved();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Drawer
      open={open}
      onClose={onClose}
      title={`Edit ${control.code}`}
      footer={<><Button variant="ghost" onClick={onClose}>Cancel</Button><Button onClick={save} busy={busy} disabled={!form.title.trim() || !form.category.trim()}>Save</Button></>}
    >
      <FormError error={error} />
      <Field label="Title">{(id) => <Input id={id} value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} />}</Field>
      <Field label="Description" hint="Describe the control the way it works in your company. Auditors read this.">
        {(id) => <Textarea id={id} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} className="min-h-[140px]" />}
      </Field>
      <Field label="Owner">{(id) => <MemberSelect id={id} value={form.owner} onChange={(v) => setForm({ ...form, owner: v })} />}</Field>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Category">{(id) => <Input id={id} value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })} />}</Field>
        <Field label="Review frequency">
          {(id) => (
            <Select id={id} value={form.frequency} onChange={(e) => setForm({ ...form, frequency: e.target.value })}>
              {FREQUENCIES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </Select>
          )}
        </Field>
      </div>
      <p className="text-xs text-muted">The control code ({control.code}) and its framework mappings don't change, so your readiness scores stay correct.</p>
    </Drawer>
  );
}
