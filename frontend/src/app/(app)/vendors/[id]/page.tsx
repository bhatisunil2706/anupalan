"use client";

import { ArrowLeft, Download, FileUp, Send, Trash2 } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useRef, useState } from "react";

import { useSession } from "@/components/session";
import { Badge, Button, ButtonLink, Drawer, Empty, Field, FormError, Input, LoadError, Loading, PageHeader, Panel, Select, tbl, useToast } from "@/components/ui";
import { api, download, useApi } from "@/lib/api";
import { bytes, fmtDate } from "@/lib/format";
import type { Vendor } from "@/lib/types";
import { AssessmentDrawer, AssessmentsTable, SendDrawer, type Assessment } from "@/components/questionnaires";

interface Doc { id: string; kind: string; kind_label: string; title: string; file_name: string; size_bytes: number; valid_until: string | null; uploaded_via: string; created_at: string }
interface Detail { assessments: Assessment[]; documents: Doc[]; doc_kinds: Record<string, string> }

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
          <AssessmentsTable rows={d.assessments} onChanged={detail.reload} onOpen={(a) => setViewing(a.id)} />
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

      <SendDrawer open={sending} vendorId={id} tier={v.tier} isProcessor={v.is_processor} onClose={() => setSending(false)} onSent={() => detail.reload()} />
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
