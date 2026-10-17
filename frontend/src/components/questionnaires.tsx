"use client";

import { Bell, Copy, Download, XCircle } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { useSession } from "@/components/session";
import { Badge, Button, Checkbox, Drawer, Empty, Field, FormError, Input, LoadError, Loading, Textarea, tbl, useToast } from "@/components/ui";
import { api, download, useApi } from "@/lib/api";
import { fmtDate } from "@/lib/format";

export type AssessmentStatus = "sent" | "in_progress" | "submitted" | "reviewed" | "expired" | "cancelled";

export interface Assessment {
  id: string; vendor_id: string; template_slug: string; template_title: string; sent_to_email: string; status: AssessmentStatus;
  questions_total: number; answered: number; reminders_sent: number; last_reminded_at: string | null;
  score: number | null; rating: string; expires_at: string; submitted_at: string | null; reviewed_at: string | null;
  reviewer_notes: string; respondent_name: string; created_at: string;
  vendor_name?: string; vendor_tier?: string;
}
export interface TemplateSummary {
  slug: string; title: string; description: string; questions: number; scored: number; sections: string[];
  kind: "core" | "addon" | "custom"; recommended_for: string[]; source: "built_in" | "custom"; updated_at: string | null; based_on: string;
}
export interface Question {
  id: string; section: string; text: string; type: "yes_no" | "text" | "choice"; weight?: number; good?: "yes" | "no";
  evidence?: boolean; options?: string[]; guidance?: string; refs?: string;
}
interface FullAssessment extends Assessment {
  answers: Record<string, { answer: string; comment: string }>;
  template: { title: string; questions: Question[] };
  critical_issues: string[];
}

export const STATUS: Record<AssessmentStatus, { label: string; tone: "prog" | "warn" | "pass" | "fail" | "idle" }> = {
  sent: { label: "Sent", tone: "prog" },
  in_progress: { label: "In progress", tone: "prog" },
  submitted: { label: "Ready to review", tone: "warn" },
  reviewed: { label: "Reviewed", tone: "pass" },
  expired: { label: "Expired", tone: "fail" },
  cancelled: { label: "Cancelled", tone: "idle" },
};
const RATING = { low: "pass", medium: "warn", high: "fail" } as const;

/** Sent questionnaires with progress, reminders and cancel. Used per vendor and across all vendors. */
export function AssessmentsTable({ rows, showVendor, onChanged, onOpen }: { rows: Assessment[]; showVendor?: boolean; onChanged: () => void; onOpen: (a: Assessment) => void }) {
  const { canWrite } = useSession();
  const toast = useToast();
  const [busy, setBusy] = useState<string | null>(null);

  async function act(a: Assessment, what: "remind" | "cancel") {
    if (what === "cancel" && !confirm(`Cancel the questionnaire sent to ${a.sent_to_email}? Their link stops working.`)) return;
    setBusy(a.id);
    try {
      await api(`/assessments/${a.id}/${what}`, { method: "POST" });
      toast(what === "remind" ? `Reminder sent to ${a.sent_to_email} with a fresh link` : "Questionnaire cancelled");
      onChanged();
    } catch (e) {
      toast(e instanceof Error ? e.message : "Failed", "error");
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className={tbl.wrap}>
      <table className={tbl.table}>
        <thead>
          <tr>
            {showVendor && <th className={tbl.th}>Vendor</th>}
            <th className={tbl.th}>Questionnaire</th>
            <th className={tbl.th}>Sent to</th>
            <th className={tbl.th}>Status</th>
            <th className={tbl.th}>Progress / score</th>
            <th className={tbl.th}>Dates</th>
            {canWrite && <th className={tbl.th}><span className="sr-only">Actions</span></th>}
          </tr>
        </thead>
        <tbody>
          {rows.map((a) => {
            const done = a.status === "submitted" || a.status === "reviewed";
            const open = a.status === "sent" || a.status === "in_progress" || a.status === "expired";
            const pct = a.questions_total ? Math.round((100 * a.answered) / a.questions_total) : 0;
            return (
              <tr key={a.id} className={`${tbl.row} ${done ? "cursor-pointer" : ""}`} onClick={() => done && onOpen(a)}>
                {showVendor && (
                  <td className={tbl.td}>
                    <Link href={`/vendors/${a.vendor_id}`} className="font-medium hover:underline" onClick={(e) => e.stopPropagation()}>{a.vendor_name}</Link>
                    {a.vendor_tier && <p className="text-xs text-muted">{a.vendor_tier[0].toUpperCase() + a.vendor_tier.slice(1)} risk</p>}
                  </td>
                )}
                <td className={tbl.td}>{a.template_title}</td>
                <td className={`${tbl.td} text-muted`}>{a.sent_to_email}</td>
                <td className={tbl.td}><Badge tone={STATUS[a.status].tone}>{STATUS[a.status].label}</Badge></td>
                <td className={tbl.td}>
                  {a.score !== null ? (
                    <span className="flex items-center gap-2 whitespace-nowrap">{a.score}/100 <Badge tone={RATING[a.rating as keyof typeof RATING] ?? "idle"}>{a.rating} risk</Badge></span>
                  ) : a.status === "cancelled" ? "—" : (
                    <div className="w-28">
                      <p className="text-xs text-muted">{a.answered} of {a.questions_total} answered</p>
                      <div className="mt-1 h-1.5 overflow-hidden rounded bg-line"><div className="h-full bg-ink" style={{ width: `${pct}%` }} /></div>
                    </div>
                  )}
                </td>
                <td className={`${tbl.td} whitespace-nowrap text-xs text-muted`}>
                  Sent {fmtDate(a.created_at)}
                  <br />
                  {a.submitted_at ? `Submitted ${fmtDate(a.submitted_at)}` : a.status === "cancelled" ? "" : `${a.status === "expired" ? "Expired" : "Due"} ${fmtDate(a.expires_at)}`}
                  {a.reminders_sent > 0 && !done && <><br />{a.reminders_sent} reminder{a.reminders_sent > 1 ? "s" : ""}</>}
                </td>
                {canWrite && (
                  <td className={`${tbl.td} whitespace-nowrap text-right`} onClick={(e) => e.stopPropagation()}>
                    {open && <Button size="sm" variant="ghost" busy={busy === a.id} onClick={() => act(a, "remind")} title="Email a reminder with a fresh link"><Bell size={14} aria-hidden /> Remind</Button>}
                    {open && <Button size="sm" variant="ghost" aria-label="Cancel" title="Cancel" onClick={() => act(a, "cancel")}><XCircle size={14} /></Button>}
                    {done && <Button size="sm" variant="ghost" aria-label="Download answers" title="Download answers (.xlsx)" onClick={() => download(`/vendors/${a.vendor_id}/assessments/${a.id}/export`, `${a.template_title}.xlsx`).catch((e) => toast(e.message, "error"))}><Download size={14} /></Button>}
                  </td>
                )}
              </tr>
            );
          })}
        </tbody>
      </table>
      {!rows.length && <Empty title="No questionnaires sent yet">Open a vendor and choose Send questionnaire. They answer by link without an account.</Empty>}
    </div>
  );
}

/** Choose a core questionnaire (recommended by tier) plus optional add-ons, and send them in one email. */
export function SendDrawer({ open, vendorId, tier, isProcessor, onClose, onSent }: { open: boolean; vendorId: string; tier: string; isProcessor?: boolean; onClose: () => void; onSent: () => void }) {
  const toast = useToast();
  const templates = useApi<TemplateSummary[]>(open ? "/questionnaires" : null);
  const [core, setCore] = useState("");
  const [addons, setAddons] = useState<string[]>([]);
  const [email, setEmail] = useState("");
  const [days, setDays] = useState(21);
  const [links, setLinks] = useState<{ title: string; link: string }[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const all = templates.data ?? [];
  const cores = all.filter((t) => t.kind === "core" || t.source === "custom");
  const addonList = all.filter((t) => t.kind === "addon");
  useEffect(() => {
    if (!templates.data || core) return;
    const rec = templates.data.find((t) => t.kind === "core" && t.recommended_for.includes(tier));
    setCore(rec?.slug ?? templates.data[0]?.slug ?? "");
    if (isProcessor) setAddons(templates.data.filter((t) => t.slug === "dpdp-processor").map((t) => t.slug));
  }, [templates.data, tier, isProcessor, core]);

  async function send() {
    setBusy(true);
    setError(null);
    try {
      const r = await api<{ sent: { template_title: string; link: string }[] }>(`/vendors/${vendorId}/assessments`, {
        method: "POST", json: { template_slugs: [core, ...addons].filter(Boolean), email, expires_days: days },
      });
      setLinks(r.sent.map((s) => ({ title: s.template_title, link: s.link })));
      onSent();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed");
    } finally {
      setBusy(false);
    }
  }
  function close() {
    setLinks(null);
    setEmail("");
    setCore("");
    setAddons([]);
    onClose();
  }

  const total = [core, ...addons].map((s) => all.find((t) => t.slug === s)?.questions ?? 0).reduce((a, b) => a + b, 0);
  return (
    <Drawer open={open} onClose={close} title="Send security questionnaires" wide
      footer={links ? <Button onClick={close}>Done</Button> : <><Button variant="secondary" onClick={close}>Cancel</Button><Button busy={busy} disabled={!core || !email} onClick={send}>Send {total ? `(${total} questions)` : ""}</Button></>}>
      <FormError error={error} />
      {links ? (
        <div className="space-y-3 text-sm">
          <p className="font-medium text-pass">Sent. We emailed {links.length > 1 ? "these links" : "this link"} to {email}.</p>
          {links.map((l) => (
            <div key={l.link}>
              <p className="mb-1 text-xs text-muted">{l.title}</p>
              <div className="flex gap-2">
                <Input readOnly value={l.link} aria-label={`${l.title} link`} onFocus={(e) => e.target.select()} />
                <Button variant="secondary" aria-label="Copy link" onClick={() => navigator.clipboard.writeText(l.link).then(() => toast("Copied"))}><Copy size={14} /></Button>
              </div>
            </div>
          ))}
          <p className="text-muted">Anyone with a link can answer, so only share it with the vendor&apos;s security contact. You can send a reminder from the questionnaire list; it issues a fresh link.</p>
        </div>
      ) : templates.loading && !templates.data ? <Loading /> : (
        <>
          <fieldset>
            <legend className="mb-2 text-[13px] font-medium">Questionnaire</legend>
            <div className="space-y-2">
              {cores.map((t) => (
                <label key={t.slug} className={`flex cursor-pointer items-start gap-3 rounded-md border px-3 py-2.5 ${core === t.slug ? "border-ink bg-ink-50/60" : "border-line hover:border-ink/40"}`}>
                  <input type="radio" name="core" className="mt-1 accent-ink" checked={core === t.slug} onChange={() => setCore(t.slug)} />
                  <span className="min-w-0">
                    <span className="flex flex-wrap items-center gap-2 text-sm font-medium">
                      {t.title} <span className="font-normal text-muted">{t.questions} questions</span>
                      {t.recommended_for.includes(tier) && <Badge tone="pass">Recommended for {tier} risk</Badge>}
                      {t.source === "custom" && <Badge tone="ink">Yours</Badge>}
                    </span>
                    <span className="mt-0.5 block text-xs leading-relaxed text-muted">{t.description}</span>
                  </span>
                </label>
              ))}
            </div>
          </fieldset>
          {addonList.length > 0 && (
            <fieldset>
              <legend className="mb-2 text-[13px] font-medium">Add-ons (optional)</legend>
              <div className="space-y-2">
                {addonList.map((t) => (
                  <Checkbox key={t.slug} label={`${t.title.replace(/^Add-on: /, "")} (${t.questions} questions)`} hint={t.description}
                    checked={addons.includes(t.slug)} onChange={(v) => setAddons(v ? [...addons, t.slug] : addons.filter((s) => s !== t.slug))} />
                ))}
              </div>
            </fieldset>
          )}
          <Field label="Vendor contact email">{(id) => <Input id={id} type="email" required value={email} onChange={(e) => setEmail(e.target.value)} placeholder="security@vendor.com" />}</Field>
          <Field label="Due in (days)" hint="The link stops working after this. A reminder goes out 3 days before.">{(id) => <Input id={id} type="number" min={3} max={60} value={days} onChange={(e) => setDays(Number(e.target.value))} className="w-28" />}</Field>
          <p className="text-xs text-muted"><Link href="/vendors/questionnaires?tab=library" className="font-medium text-ink underline">See every question</Link> or build your own questionnaire.</p>
        </>
      )}
    </Drawer>
  );
}

/** Read a submitted questionnaire, see the critical gaps, download it and mark it reviewed. */
export function AssessmentDrawer({ vendorId, assessmentId, onClose, onReviewed }: { vendorId: string; assessmentId: string; onClose: () => void; onReviewed: () => void }) {
  const { canWrite } = useSession();
  const toast = useToast();
  const { data, error, loading } = useApi<FullAssessment>(`/vendors/${vendorId}/assessments/${assessmentId}`);
  const [notes, setNotes] = useState("");
  const [onlyGaps, setOnlyGaps] = useState(false);
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

  const isGap = (q: Question) => {
    const a = data?.answers[q.id];
    return q.type === "yes_no" && !!q.weight && !!a && a.answer !== "na" && a.answer !== q.good;
  };
  const questions = (data?.template.questions ?? []).filter((q) => !onlyGaps || isGap(q));
  const sections = Array.from(new Set(questions.map((q) => q.section)));
  const gaps = (data?.template.questions ?? []).filter(isGap).length;

  return (
    <Drawer open onClose={onClose} title={data ? `${data.template.title}: ${data.respondent_name}` : "Questionnaire"} wide
      footer={data?.status === "submitted" && canWrite ? <><Button variant="secondary" onClick={onClose}>Close</Button><Button busy={busy} onClick={review}>Mark reviewed</Button></> : undefined}>
      {loading && !data ? <Loading /> : error || !data ? <LoadError error={error ?? "Could not load"} /> : (
        <>
          <FormError error={formError} />
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <span className="text-2xl font-bold">{data.score ?? "—"}/100</span>
            {data.rating && <Badge tone={RATING[data.rating as keyof typeof RATING] ?? "idle"}>{data.rating} risk</Badge>}
            {data.critical_issues.length > 0 && <Badge tone="fail">{data.critical_issues.length} critical gaps</Badge>}
            {gaps > 0 && <Badge tone="warn">{gaps} answers below expectation</Badge>}
            <span className="ml-auto flex gap-2">
              <Button size="sm" variant="secondary" onClick={() => download(`/vendors/${vendorId}/assessments/${assessmentId}/export`, `${data.template.title}.xlsx`).catch((e) => toast(e.message, "error"))}>
                <Download size={14} aria-hidden /> Excel
              </Button>
            </span>
          </div>
          {gaps > 0 && <Checkbox label="Show only gaps" checked={onlyGaps} onChange={setOnlyGaps} />}
          {sections.map((s) => (
            <div key={s}>
              <p className="mb-2 mt-2 text-xs font-semibold uppercase tracking-wide text-muted">{s}</p>
              <ul className="space-y-2">
                {questions.filter((q) => q.section === s).map((q) => {
                  const a = data.answers[q.id];
                  const bad = isGap(q);
                  return (
                    <li key={q.id} className={`rounded-md border p-3 text-sm ${bad ? (data.critical_issues.includes(q.id) ? "border-fail/40 bg-fail-50" : "border-warn/30 bg-warn-50") : "border-line"}`}>
                      <p>{q.text}</p>
                      <p className="mt-1 font-medium">
                        {q.type === "yes_no" ? (a?.answer === "na" ? "Not applicable" : a?.answer === "yes" ? "Yes" : a?.answer === "no" ? "No" : "No answer") : a?.answer || "No answer"}
                        {bad && <span className="ml-2 text-xs font-normal text-muted">expected {q.good === "yes" ? "Yes" : "No"}</span>}
                      </p>
                      {a?.comment && <p className="mt-1 text-muted">{a.comment}</p>}
                      {q.refs && <p className="mt-1 text-xs text-muted">{q.refs}</p>}
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
