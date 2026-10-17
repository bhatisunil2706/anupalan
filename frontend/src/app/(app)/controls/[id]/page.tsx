"use client";

import { CheckCircle2, CircleDashed, Circle, Pencil, Plug, Zap } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import { ChecksList, EvidenceItem } from "@/components/evidence";
import { TaskDrawer } from "@/components/task-drawer";

import { MemberSelect } from "@/components/pickers";
import { useSession } from "@/components/session";
import {
  Badge,
  Button,
  Checkbox,
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
import { fmtDate, fmtDateTime } from "@/lib/format";
import type { Control, Evidence, Task } from "@/lib/types";

interface Detail {
  control: Control;
  implementation_notes: string;
  na_justification: string;
  evidence_hint: string;
  acceptance_criteria: string[];
  acceptance_customised: boolean;
  criteria_coverage: { n: number; criterion: string; approved: string[]; pending: string[] }[];
  automation: { provider: string; name: string; connected: boolean; tests: string[] }[];
  requirements: { framework: string; framework_code: string; ref: string; title: string; guidance: string }[];
  evidence: Evidence[];
  tasks: Task[];
  tests: { key: string; title: string; status: string; run_at: string; summary: string }[];
}

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
  const shown = data.criteria_coverage.filter((x) => x.approved.length).length;

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
          {data.acceptance_criteria.length > 0 && (
            <Panel title="What the evidence must show" actions={<span className="text-xs text-muted">{shown} of {data.acceptance_criteria.length} shown by approved evidence</span>}>
              <ul className="space-y-1.5">
                {data.criteria_coverage.map((x) => (
                  <li key={x.n} className="flex items-start gap-2 text-sm">
                    {x.approved.length ? (
                      <CheckCircle2 size={16} className="mt-0.5 shrink-0 text-pass" aria-label="Shown by approved evidence" />
                    ) : x.pending.length ? (
                      <CircleDashed size={16} className="mt-0.5 shrink-0 text-warn" aria-label="Shown by evidence awaiting review" />
                    ) : (
                      <Circle size={16} className="mt-0.5 shrink-0 text-muted" aria-label="Not shown yet" />
                    )}
                    <span className={x.approved.length ? "" : "text-muted"}>{x.criterion}</span>
                  </li>
                ))}
              </ul>
              <p className="mt-3 text-xs text-muted">
                {data.acceptance_customised ? "Your company's own criteria. " : ""}A point counts as shown when the uploader confirms it or the AI check finds it, and a reviewer approves the evidence.
              </p>
            </Panel>
          )}

          <Panel
            title="Evidence"
            actions={canWrite && <Button size="sm" onClick={() => setAddingEvidence(true)}>Add evidence</Button>}
            flush
          >
            {c.pending_review > 0 && (
              <p className="border-b border-line bg-warn-50 px-4 py-2.5 text-xs text-warn">
                {c.pending_review} item{c.pending_review > 1 ? "s" : ""} awaiting review. Evidence counts only after someone other than the uploader approves it.
              </p>
            )}
            {data.evidence.length ? (
              <ul>
                {data.evidence.map((ev) => (
                  <li key={ev.id} className="border-b border-line px-4 py-3 last:border-0">
                    <EvidenceItem ev={ev} canWrite={canWrite} criteria={data.acceptance_criteria} onChanged={reload} onDelete={removeEvidence} />
                  </li>
                ))}
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

          {data.automation.length > 0 && (
            <Panel title="Collect automatically">
              <p className="mb-3 text-xs text-muted">Evidence collected from your systems can&apos;t be picked or edited by hand, so auditors trust it most.</p>
              <ul className="space-y-2.5">
                {data.automation.map((a) => (
                  <li key={a.provider} className="text-sm">
                    <div className="flex items-center justify-between gap-2">
                      <span className="flex items-center gap-1.5 font-medium">{a.connected ? <Zap size={14} className="text-pass" aria-hidden /> : <Plug size={14} className="text-muted" aria-hidden />}{a.name}</span>
                      {a.connected ? <Badge tone="pass">Connected</Badge> : <Link href={`/integrations?q=${encodeURIComponent(a.name)}`} className="text-xs font-medium text-ink hover:underline">Connect</Link>}
                    </div>
                    <p className="mt-0.5 text-xs text-muted">{a.tests.join(" · ")}</p>
                  </li>
                ))}
              </ul>
            </Panel>
          )}

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
        criteria={data.acceptance_criteria}
        customised={data.acceptance_customised}
        onClose={() => setEditingDetails(false)}
        onSaved={() => { setEditingDetails(false); toast("Control updated"); reload(); }}
      />
      <AddEvidence open={addingEvidence} controlId={id} criteria={data.acceptance_criteria} hint={data.evidence_hint} onClose={() => { setAddingEvidence(false); reload(); }} />
      <TaskDrawer open={addingTask} controlId={id} onClose={() => setAddingTask(false)} onDone={() => { setAddingTask(false); toast("Task added"); reload(); }} />
    </>
  );
}

function AddEvidence({ open, controlId, criteria, hint, onClose }: { open: boolean; controlId: string; criteria: string[]; hint: string; onClose: () => void }) {
  const [kind, setKind] = useState<"file" | "link" | "note">("file");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [url, setUrl] = useState("");
  const [validUntil, setValidUntil] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [picked, setPicked] = useState<number[]>([]);
  const [result, setResult] = useState<Evidence | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  function reset() {
    setTitle(""); setDescription(""); setUrl(""); setFile(null); setValidUntil(""); setPicked([]); setResult(null); setError(null);
  }
  function close() {
    reset();
    onClose();
  }

  async function save() {
    setBusy(true);
    setError(null);
    const fd = new FormData();
    fd.set("title", title);
    fd.set("kind", kind);
    fd.set("description", description);
    fd.set("criteria", picked.join(","));
    if (url) fd.set("url", url);
    if (validUntil) fd.set("valid_until", validUntil);
    if (file) fd.set("file", file);
    try {
      setResult(await api<Evidence>(`/controls/${controlId}/evidence`, { method: "POST", body: fd }));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Upload failed");
    } finally {
      setBusy(false);
    }
  }

  const needsCriteria = criteria.length > 0 && picked.length === 0;
  if (result) {
    const warnings = result.checks.filter((x) => x.severity === "warn");
    return (
      <Drawer open={open} onClose={close} title="Evidence added" footer={<><Button variant="secondary" onClick={() => reset()}>Add another</Button><Button onClick={close}>Done</Button></>}>
        <p className="text-sm">
          <span className="font-medium">{result.title}</span> was added
          {result.review_status === "pending" ? " and is awaiting review. It counts once someone other than you approves it." : " and counts as evidence now."}
        </p>
        {warnings.length > 0 ? (
          <div className="rounded-md border border-warn/30 bg-warn-50 px-3 py-2">
            <p className="text-sm font-medium text-warn">Automatic checks found {warnings.length} thing{warnings.length > 1 ? "s" : ""} to look at</p>
            <ChecksList checks={result.checks} compact />
            <p className="mt-2 text-xs text-muted">If the file is wrong, delete it and upload the right one. Otherwise the reviewer will see these notes.</p>
          </div>
        ) : (
          <p className="rounded-md border border-pass/30 bg-pass-50 px-3 py-2 text-sm text-pass">Automatic checks found no problems.</p>
        )}
        {result.ai_check?.status === "pending" && <p className="text-sm text-muted">The AI check is reading the file. Its verdict will appear on the evidence in a minute.</p>}
        {result.sha256?.length === 64 && <p className="text-xs text-muted">Fingerprint (SHA-256) recorded: <span className="font-mono">{result.sha256.slice(0, 16)}…</span> Any later change to the stored file will be detected.</p>}
      </Drawer>
    );
  }

  return (
    <Drawer open={open} onClose={close} title="Add evidence" footer={<><Button variant="ghost" onClick={close}>Cancel</Button><Button onClick={save} busy={busy} disabled={!title || needsCriteria}>Add evidence</Button></>}>
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
      {criteria.length > 0 ? (
        <fieldset className="rounded-md border border-line p-3">
          <legend className="px-1 text-[13px] font-medium">This evidence shows</legend>
          <p className="mb-2 text-xs text-muted">Tick every point it shows. Other evidence can cover the rest.</p>
          <div className="space-y-2">
            {criteria.map((c, i) => (
              <Checkbox key={c} label={c} checked={picked.includes(i + 1)} onChange={(v) => setPicked(v ? [...picked, i + 1] : picked.filter((n) => n !== i + 1))} />
            ))}
          </div>
        </fieldset>
      ) : hint ? <p className="text-xs text-muted">Auditors expect: {hint}</p> : null}
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

function EditControl({ open, control, criteria, customised, onClose, onSaved }: { open: boolean; control: Control; criteria: string[]; customised: boolean; onClose: () => void; onSaved: () => void }) {
  const [form, setForm] = useState({ title: "", description: "", category: "", frequency: "annual", owner: "", criteria: "" });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (open) {
      setForm({ title: control.title, description: control.description, category: control.category, frequency: control.frequency, owner: control.owner?.id ?? "", criteria: criteria.join("\n") });
      setError(null);
    }
  }, [open, control, criteria]);

  async function save() {
    setBusy(true);
    setError(null);
    const json: Record<string, unknown> = {};
    if (form.title !== control.title) json.title = form.title;
    if (form.description !== control.description) json.description = form.description;
    if (form.category !== control.category) json.category = form.category;
    if (form.frequency !== control.frequency) json.frequency = form.frequency;
    if (form.owner !== (control.owner?.id ?? "")) Object.assign(json, form.owner ? { owner_id: form.owner } : { clear_owner: true });
    if (form.criteria !== criteria.join("\n")) json.acceptance_criteria = form.criteria.split("\n").map((x) => x.trim()).filter(Boolean);
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
      <Field label="What the evidence must show" hint="One point per line. Uploaders tick these, reviewers and the AI check use them.">
        {(id) => <Textarea id={id} value={form.criteria} onChange={(e) => setForm({ ...form, criteria: e.target.value })} className="min-h-[120px]" />}
      </Field>
      {customised && (
        <button type="button" className="-mt-2 text-xs font-medium text-ink hover:underline" onClick={() => setForm({ ...form, criteria: "" })}>
          Reset to the standard criteria (save with the box empty)
        </button>
      )}
      <p className="text-xs text-muted">The control code ({control.code}) and its framework mappings don't change, so your readiness scores stay correct.</p>
    </Drawer>
  );
}
