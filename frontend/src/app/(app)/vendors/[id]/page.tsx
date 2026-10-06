"use client";

import { ArrowLeft, Copy, Download, FileUp, Send, Trash2 } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useRef, useState } from "react";

import { useSession } from "@/components/session";
import { Badge, Button, ButtonLink, Drawer, Empty, Field, FormError, Input, LoadError, Loading, PageHeader, Panel, Select, Textarea, tbl, useToast } from "@/components/ui";
import { api, download, useApi } from "@/lib/api";
import { bytes, fmtDate } from "@/lib/format";
import type { Vendor } from "@/lib/types";

interface Assessment {
  id: string; template_slug: string; sent_to_email: string; status: "sent" | "in_progress" | "submitted" | "reviewed";
  score: number | null; rating: string; expires_at: string; submitted_at: string | null; reviewed_at: string | null;
  reviewer_notes: string; respondent_name: string; created_at: string;
}
interface Doc { id: string; kind: string; kind_label: string; title: string; file_name: string; size_bytes: number; valid_until: string | null; uploaded_via: string; created_at: string }
interface Detail { assessments: Assessment[]; documents: Doc[]; doc_kinds: Record<string, string> }
interface Template { slug: string; title: string; description: string; questions: number }
interface Question { id: string; section: string; text: string; type: "yes_no" | "text"; weight?: number; good?: string }
interface FullAssessment extends Assessment {
  answers: Record<string, { answer: string; comment: string }>;
  template: { title: string; questions: Question[] };
  critical_issues: string[];
}

const STATUS = { sent: { label: "Sent", tone: "prog" }, in_progress: { label: "In progress", tone: "prog" }, submitted: { label: "Ready to review", tone: "warn" }, reviewed: { label: "Reviewed", tone: "pass" } } as const;
const RATING = { low: "pass", medium: "warn", high: "fail" } as const;

export default function VendorDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { canWrite } = useSession();
  const vendors = useApi<Vendor[]>("/vendors");
  const detail = useApi<Detail>(`/vendors/${id}/detail`);
  const [sending, setSending] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [viewing, setViewing] = useState<string | null>(null);
  const toast = useToast();

  if ((vendors.loading && !vendors.data) || (detail.loading && !detail.data)) return <Loading />;
  const v = vendors.data?.find((x) => x.id === id);
  if (detail.error || !detail.data || !v) return <LoadError error={detail.error ?? "Vendor not found"} retry={detail.reload} />;
  const d = detail.data;
  const today = new Date().toISOString().slice(0, 10);

  return (
    <>
      <Link href="/vendors" className="mb-3 inline-flex items-center gap-1 text-sm text-muted hover:text-text"><ArrowLeft size={14} /> Vendors</Link>
      <PageHeader
        title={v.name}
        description={v.services}
        actions={
          canWrite && (
            <>
              <ButtonLink href={`/vendors?edit=${v.id}`}>Edit details</ButtonLink>
              <Button variant="secondary" onClick={() => setUploading(true)}><FileUp size={14} aria-hidden /> Add document</Button>
              <Button onClick={() => setSending(true)}><Send size={14} aria-hidden /> Send questionnaire</Button>
            </>
          )
        }
      />
      <div className="mb-6 grid gap-3 sm:grid-cols-4">
        <Fact label="Risk tier" value={<Badge tone={v.tier === "critical" ? "fail" : v.tier === "high" ? "warn" : "prog"}>{v.tier[0].toUpperCase() + v.tier.slice(1)}</Badge>} />
        <Fact label="Processes personal data" value={v.is_processor ? (v.dpa_signed ? "Yes, DPA signed" : <span className="text-fail">Yes, no DPA</span>) : "No"} />
        <Fact label="Last assessed" value={fmtDate(v.last_assessed_at) || "Never"} />
        <Fact label="Next review" value={v.next_review_date ? <span className={v.next_review_date < today ? "text-fail" : ""}>{fmtDate(v.next_review_date)}</span> : "Not scheduled"} />
      </div>

      <div className="space-y-6">
        <Panel title="Security questionnaires" flush>
          {d.assessments.length === 0 ? (
            <Empty title="No questionnaires yet">Send the vendor a link. They answer without an account, and you get a score and the critical gaps.</Empty>
          ) : (
            <div className={tbl.wrap}>
              <table className={tbl.table}>
                <thead><tr><th className={tbl.th}>Questionnaire</th><th className={tbl.th}>Sent to</th><th className={tbl.th}>Status</th><th className={tbl.th}>Score</th><th className={tbl.th}>Date</th></tr></thead>
                <tbody>
                  {d.assessments.map((a) => (
                    <tr key={a.id} className={`${tbl.row} cursor-pointer`} onClick={() => a.status === "submitted" || a.status === "reviewed" ? setViewing(a.id) : undefined}>
                      <td className={tbl.td}>{a.template_slug === "dpdp-processor" ? "DPDP processor" : "Security baseline"}</td>
                      <td className={tbl.td}>{a.sent_to_email}</td>
                      <td className={tbl.td}><Badge tone={STATUS[a.status].tone}>{STATUS[a.status].label}</Badge></td>
                      <td className={tbl.td}>{a.score !== null ? <span className="flex items-center gap-2">{a.score}/100 <Badge tone={RATING[a.rating as keyof typeof RATING] ?? "idle"}>{a.rating} risk</Badge></span> : "—"}</td>
                      <td className={`${tbl.td} text-muted`}>{a.submitted_at ? `Submitted ${fmtDate(a.submitted_at)}` : `Link expires ${fmtDate(a.expires_at)}`}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Panel>

        <Panel title="Certificates and documents" flush>
          {d.documents.length === 0 ? (
            <Empty title="No documents">Upload the vendor&apos;s ISO 27001 certificate, SOC 2 report or DPA. You&apos;ll be reminded 30 days before they expire.</Empty>
          ) : (
            <div className={tbl.wrap}>
              <table className={tbl.table}>
                <thead><tr><th className={tbl.th}>Document</th><th className={tbl.th}>Valid until</th><th className={tbl.th}>Added</th><th className={tbl.th}><span className="sr-only">Actions</span></th></tr></thead>
                <tbody>
                  {d.documents.map((doc) => (
                    <tr key={doc.id} className={tbl.row}>
                      <td className={tbl.td}><p className="font-medium">{doc.title}</p><p className="text-xs text-muted">{doc.file_name} · {bytes(doc.size_bytes)}</p></td>
                      <td className={tbl.td}>{doc.valid_until ? <span className={doc.valid_until < today ? "font-medium text-fail" : ""}>{fmtDate(doc.valid_until)}{doc.valid_until < today && " (expired)"}</span> : "—"}</td>
                      <td className={`${tbl.td} text-muted`}>{fmtDate(doc.created_at)}{doc.uploaded_via === "vendor_portal" && <Badge className="ml-2" tone="ink">From vendor</Badge>}</td>
                      <td className={`${tbl.td} whitespace-nowrap text-right`}>
                        <Button size="sm" variant="ghost" aria-label="Download" onClick={() => download(`/vendors/${id}/documents/${doc.id}/download`, doc.file_name).catch((e) => toast(e.message, "error"))}><Download size={14} /></Button>
                        {canWrite && <Button size="sm" variant="ghost" aria-label="Delete" onClick={async () => { if (!confirm(`Delete ${doc.title}?`)) return; await api(`/vendors/${id}/documents/${doc.id}`, { method: "DELETE" }); detail.reload(); }}><Trash2 size={14} /></Button>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Panel>
      </div>

      <SendDrawer open={sending} vendorId={id} onClose={() => setSending(false)} onSent={() => detail.reload()} />
      <UploadDrawer open={uploading} vendorId={id} kinds={d.doc_kinds} onClose={() => setUploading(false)} onDone={() => { setUploading(false); detail.reload(); vendors.reload(); }} />
      {viewing && <AssessmentDrawer vendorId={id} assessmentId={viewing} onClose={() => setViewing(null)} onReviewed={() => { setViewing(null); detail.reload(); vendors.reload(); }} />}
    </>
  );
}

function Fact({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="rounded-lg border border-line bg-surface p-3">
      <p className="text-xs text-muted">{label}</p>
      <div className="mt-1 text-sm font-medium">{value}</div>
    </div>
  );
}

function SendDrawer({ open, vendorId, onClose, onSent }: { open: boolean; vendorId: string; onClose: () => void; onSent: () => void }) {
  const toast = useToast();
  const templates = useApi<Template[]>(open ? "/questionnaires" : null);
  const [form, setForm] = useState({ template_slug: "vendor-security-baseline", email: "", expires_days: 21 });
  const [link, setLink] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function send() {
    setBusy(true);
    setError(null);
    try {
      const r = await api<{ link: string }>(`/vendors/${vendorId}/assessments`, { method: "POST", json: form });
      setLink(r.link);
      onSent();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed");
    } finally {
      setBusy(false);
    }
  }
  function close() {
    setLink(null);
    setForm({ ...form, email: "" });
    onClose();
  }

  return (
    <Drawer open={open} onClose={close} title="Send a security questionnaire"
      footer={link ? <Button onClick={close}>Done</Button> : <><Button variant="secondary" onClick={close}>Cancel</Button><Button busy={busy} onClick={send}>Send</Button></>}>
      <FormError error={error} />
      {link ? (
        <div className="space-y-2 text-sm">
          <p className="font-medium text-pass">Sent. We emailed this link to {form.email}.</p>
          <div className="flex gap-2">
            <Input readOnly value={link} aria-label="Questionnaire link" onFocus={(e) => e.target.select()} />
            <Button variant="secondary" onClick={() => navigator.clipboard.writeText(link).then(() => toast("Copied"))}><Copy size={14} /></Button>
          </div>
          <p className="text-muted">Anyone with the link can answer, so only share it with the vendor&apos;s security contact.</p>
        </div>
      ) : (
        <>
          <Field label="Questionnaire">
            {(id) => (
              <Select id={id} value={form.template_slug} onChange={(e) => setForm({ ...form, template_slug: e.target.value })}>
                {(templates.data ?? []).map((t) => <option key={t.slug} value={t.slug}>{t.title} ({t.questions} questions)</option>)}
              </Select>
            )}
          </Field>
          <p className="text-xs text-muted">{templates.data?.find((t) => t.slug === form.template_slug)?.description}</p>
          <Field label="Vendor contact email">{(id) => <Input id={id} type="email" required value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />}</Field>
          <Field label="Link valid for (days)">{(id) => <Input id={id} type="number" min={3} max={60} value={form.expires_days} onChange={(e) => setForm({ ...form, expires_days: Number(e.target.value) })} className="w-28" />}</Field>
        </>
      )}
    </Drawer>
  );
}

function UploadDrawer({ open, vendorId, kinds, onClose, onDone }: { open: boolean; vendorId: string; kinds: Record<string, string>; onClose: () => void; onDone: () => void }) {
  const file = useRef<HTMLInputElement>(null);
  const [kind, setKind] = useState("iso27001");
  const [validUntil, setValidUntil] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function upload() {
    const f = file.current?.files?.[0];
    if (!f) return setError("Choose a file");
    setBusy(true);
    setError(null);
    const form = new FormData();
    form.append("kind", kind);
    if (validUntil) form.append("valid_until", validUntil);
    form.append("file", f);
    try {
      await api(`/vendors/${vendorId}/documents`, { method: "POST", body: form });
      setValidUntil("");
      onDone();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Upload failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Drawer open={open} onClose={onClose} title="Add a vendor document" footer={<><Button variant="secondary" onClick={onClose}>Cancel</Button><Button busy={busy} onClick={upload}>Upload</Button></>}>
      <FormError error={error} />
      <Field label="Type">{(id) => <Select id={id} value={kind} onChange={(e) => setKind(e.target.value)}>{Object.entries(kinds).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</Select>}</Field>
      <Field label="Valid until" hint="We'll remind the vendor owner 30 days before it expires.">{(id) => <Input id={id} type="date" value={validUntil} onChange={(e) => setValidUntil(e.target.value)} className="w-48" />}</Field>
      <Field label="File" hint="PDF, image or Office document. Files are encrypted at rest.">{(id) => <input id={id} ref={file} type="file" className="text-sm" />}</Field>
    </Drawer>
  );
}

function AssessmentDrawer({ vendorId, assessmentId, onClose, onReviewed }: { vendorId: string; assessmentId: string; onClose: () => void; onReviewed: () => void }) {
  const { canWrite } = useSession();
  const { data, error, loading } = useApi<FullAssessment>(`/vendors/${vendorId}/assessments/${assessmentId}`);
  const [notes, setNotes] = useState("");
  const [formError, setFormError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function review() {
    setBusy(true);
    setFormError(null);
    try {
      await api(`/vendors/${vendorId}/assessments/${assessmentId}/review`, { method: "POST", json: { notes } });
      onReviewed();
    } catch (e) {
      setFormError(e instanceof Error ? e.message : "Failed");
    } finally {
      setBusy(false);
    }
  }

  const sections = data ? Array.from(new Set(data.template.questions.map((q) => q.section))) : [];
  return (
    <Drawer open onClose={onClose} title={data ? `${data.template.title}: ${data.respondent_name}` : "Questionnaire"} wide
      footer={data?.status === "submitted" && canWrite ? <><Button variant="secondary" onClick={onClose}>Close</Button><Button busy={busy} onClick={review}>Mark reviewed</Button></> : undefined}>
      {loading && !data ? <Loading /> : error || !data ? <LoadError error={error ?? "Could not load"} /> : (
        <>
          <FormError error={formError} />
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <span className="text-2xl font-bold">{data.score}/100</span>
            <Badge tone={RATING[data.rating as keyof typeof RATING] ?? "idle"}>{data.rating} risk</Badge>
            {data.critical_issues.length > 0 && <Badge tone="fail">{data.critical_issues.length} critical gaps</Badge>}
          </div>
          {sections.map((s) => (
            <div key={s}>
              <p className="mb-2 mt-2 text-xs font-semibold uppercase tracking-wide text-muted">{s}</p>
              <ul className="space-y-2">
                {data.template.questions.filter((q) => q.section === s).map((q) => {
                  const a = data.answers[q.id];
                  const bad = q.type === "yes_no" && a && a.answer !== "na" && a.answer !== q.good;
                  return (
                    <li key={q.id} className={`rounded-md border p-3 text-sm ${bad ? (data.critical_issues.includes(q.id) ? "border-fail/40 bg-fail-50" : "border-warn/30 bg-warn-50") : "border-line"}`}>
                      <p>{q.text}</p>
                      <p className="mt-1 font-medium">{q.type === "yes_no" ? (a?.answer === "na" ? "Not applicable" : a?.answer === "yes" ? "Yes" : a?.answer === "no" ? "No" : "No answer") : a?.answer || "No answer"}</p>
                      {a?.comment && <p className="mt-1 text-muted">{a.comment}</p>}
                    </li>
                  );
                })}
              </ul>
            </div>
          ))}
          {data.status === "submitted" && canWrite && (
            <Field label="Review notes" hint="Saved with the VEN-01 evidence, e.g. accepted risks and follow-ups.">{(id) => <Textarea id={id} value={notes} onChange={(e) => setNotes(e.target.value)} />}</Field>
          )}
          {data.status === "reviewed" && data.reviewer_notes && <p className="text-sm"><span className="font-medium">Review notes:</span> {data.reviewer_notes}</p>}
        </>
      )}
    </Drawer>
  );
}
