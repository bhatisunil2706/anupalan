"use client";

import { AlertTriangle, BadgeCheck, Bot, CheckCircle2, CircleDashed, Download, ExternalLink, FileText, Info, Link2, RefreshCw, StickyNote, Trash2, XCircle, Zap } from "lucide-react";
import { useState } from "react";

import { api } from "@/lib/api";
import { bytes, fmtDate } from "@/lib/format";
import type { AiCheck, Evidence } from "@/lib/types";

import { Badge, Button, Textarea, cx, useToast } from "./ui";

const KIND_ICON = { file: FileText, link: Link2, note: StickyNote, automated: Zap, policy: FileText };

export const VERDICT: Record<NonNullable<AiCheck["verdict"]>, { label: string; tone: "pass" | "warn" | "fail" }> = {
  looks_right: { label: "Looks right", tone: "pass" },
  needs_attention: { label: "Needs attention", tone: "warn" },
  wrong_evidence: { label: "Doesn't fit this control", tone: "fail" },
};

export function TrustBadge({ ev }: { ev: Evidence }) {
  if (ev.trust === "automated") return <Badge tone="pass"><Zap size={11} aria-hidden className="mr-0.5 inline" />Collected automatically</Badge>;
  if (ev.trust === "platform") return <Badge tone="ink">Generated in the platform</Badge>;
  return <Badge tone="idle">Uploaded</Badge>;
}

export function ReviewBadge({ ev }: { ev: Evidence }) {
  if (ev.review_status === "pending") return <Badge tone="warn"><CircleDashed size={11} aria-hidden className="mr-0.5 inline" />Awaiting review</Badge>;
  if (ev.review_status === "rejected") return <Badge tone="fail">Sent back</Badge>;
  if (ev.trust !== "uploaded" || !ev.reviewed_by) return null;
  return <Badge tone={ev.self_approved ? "warn" : "pass"}>{ev.self_approved ? "Self-approved" : `Approved by ${ev.reviewed_by.full_name}`}</Badge>;
}

export function ChecksList({ checks, compact }: { checks: Evidence["checks"]; compact?: boolean }) {
  const shown = compact ? checks.filter((c) => c.severity === "warn") : checks;
  if (!shown.length) return null;
  return (
    <ul className="mt-2 space-y-1">
      {shown.map((c) => (
        <li key={c.code + c.message} className={cx("flex items-start gap-1.5 text-xs", c.severity === "warn" ? "text-warn" : "text-muted")}>
          {c.severity === "warn" ? <AlertTriangle size={13} className="mt-px shrink-0" aria-hidden /> : <Info size={13} className="mt-px shrink-0" aria-hidden />}
          <span>{c.message}</span>
        </li>
      ))}
    </ul>
  );
}

export function AiResult({ ai }: { ai: AiCheck }) {
  if (!ai?.status) return null;
  if (ai.status === "pending") {
    return <p className="mt-2 flex items-center gap-1.5 text-xs text-muted"><Bot size={13} aria-hidden /> AI check in progress…</p>;
  }
  if (ai.status === "failed") {
    return <p className="mt-2 flex items-center gap-1.5 text-xs text-muted"><Bot size={13} aria-hidden /> AI check couldn&apos;t run: {ai.error || "try again later"}</p>;
  }
  const v = ai.verdict ? VERDICT[ai.verdict] : null;
  return (
    <div className={cx("mt-2 rounded-md border px-3 py-2 text-xs", v?.tone === "pass" ? "border-pass/30 bg-pass-50" : v?.tone === "fail" ? "border-fail/30 bg-fail-50" : "border-warn/30 bg-warn-50")}>
      <p className="flex flex-wrap items-center gap-1.5 font-medium">
        <Bot size={13} aria-hidden /> AI check: {v?.label}
        <span className="font-normal text-muted">· advice for the reviewer, not a decision</span>
      </p>
      {ai.summary && <p className="mt-1 text-text">{ai.summary}</p>}
      {!!ai.criteria?.length && (
        <ul className="mt-1.5 space-y-0.5">
          {ai.criteria.map((c) => (
            <li key={c.n} className="flex items-start gap-1.5">
              {c.met === "yes" ? <CheckCircle2 size={13} className="mt-px shrink-0 text-pass" aria-label="Shown" /> : c.met === "no" ? <XCircle size={13} className="mt-px shrink-0 text-fail" aria-label="Not shown" /> : <CircleDashed size={13} className="mt-px shrink-0 text-warn" aria-label="Unclear" />}
              <span><span className="text-text">{c.criterion}</span>{c.note && <span className="text-muted">: {c.note}</span>}</span>
            </li>
          ))}
        </ul>
      )}
      {!!ai.issues?.length && (
        <ul className="mt-1.5 list-disc space-y-0.5 pl-4 text-text">{ai.issues.map((i) => <li key={i}>{i}</li>)}</ul>
      )}
    </div>
  );
}

export function EvidenceItem({ ev, canWrite, criteria, onChanged, onDelete }: {
  ev: Evidence;
  canWrite: boolean;
  criteria?: string[];
  onChanged: () => void;
  onDelete?: (ev: Evidence) => void;
}) {
  const toast = useToast();
  const [rejecting, setRejecting] = useState(false);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const Icon = KIND_ICON[ev.kind] ?? FileText;
  const today = new Date().toISOString().slice(0, 10);
  const expired = ev.valid_until !== null && ev.valid_until < today;

  async function decide(decision: "approve" | "reject") {
    setBusy(true);
    try {
      await api(`/evidence/${ev.id}/review`, { method: "POST", json: { decision, note } });
      toast(decision === "approve" ? "Evidence approved" : "Sent back to the uploader");
      setRejecting(false);
      setNote("");
      onChanged();
    } catch (e) {
      toast(e instanceof Error ? e.message : "Failed", "error");
    } finally {
      setBusy(false);
    }
  }

  async function recheck() {
    setBusy(true);
    try {
      await api(`/evidence/${ev.id}/recheck`, { method: "POST" });
      toast("Checks run again");
      onChanged();
    } catch (e) {
      toast(e instanceof Error ? e.message : "Failed", "error");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className={cx("flex items-start gap-3", ev.review_status === "rejected" && "opacity-70")}>
      <Icon size={16} className="mt-0.5 shrink-0 text-muted" aria-hidden />
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-1.5">
          <p className="mr-1 text-sm font-medium">{ev.title}</p>
          <TrustBadge ev={ev} />
          <ReviewBadge ev={ev} />
          {ev.review_status !== "rejected" && <Badge tone={expired ? "fail" : "idle"}>{expired ? "Expired" : ev.valid_until ? `Valid to ${fmtDate(ev.valid_until)}` : "No expiry"}</Badge>}
        </div>
        {ev.description && <p className="mt-0.5 text-sm text-muted">{ev.description}</p>}
        <p className="mt-1 text-xs text-muted">
          {ev.trust === "automated" ? "Collected" : ev.uploaded_by ? `Added by ${ev.uploaded_by.full_name}` : "Added"} on {fmtDate(ev.collected_at)}
          {ev.file_name && ` · ${ev.file_name} (${bytes(ev.size_bytes)})`}
          {ev.document_date && ` · document dated ${fmtDate(ev.document_date)}`}
          {ev.sha256 && ev.sha256.length === 64 && <span title={`SHA-256 ${ev.sha256}`}> · fingerprint {ev.sha256.slice(0, 10)}…</span>}
        </p>
        {!!criteria?.length && !!ev.criteria_confirmed.length && (
          <p className="mt-1 text-xs text-muted">Uploader says it shows: {ev.criteria_confirmed.map((n) => criteria[n - 1]).filter(Boolean).join("; ")}</p>
        )}
        {ev.review_status === "rejected" && ev.review_note && (
          <p className="mt-1 text-xs text-fail">Sent back by {ev.reviewed_by?.full_name}: {ev.review_note}</p>
        )}
        {ev.review_status === "approved" && ev.review_note && <p className="mt-1 text-xs text-muted">Reviewer&apos;s note: {ev.review_note}</p>}
        <ChecksList checks={ev.checks} />
        <AiResult ai={ev.ai_check} />
        {ev.can_review && (
          rejecting ? (
            <div className="mt-2 space-y-2">
              <Textarea aria-label="Why are you sending it back?" placeholder="What's missing or wrong? The uploader sees this." value={note} onChange={(e) => setNote(e.target.value)} className="min-h-[60px]" />
              <div className="flex gap-2">
                <Button size="sm" variant="danger" busy={busy} disabled={!note.trim()} onClick={() => decide("reject")}>Send back</Button>
                <Button size="sm" variant="ghost" onClick={() => setRejecting(false)}>Cancel</Button>
              </div>
            </div>
          ) : (
            <div className="mt-2 flex flex-wrap gap-2">
              <Button size="sm" busy={busy} onClick={() => decide("approve")}><BadgeCheck size={14} aria-hidden /> Approve</Button>
              <Button size="sm" variant="secondary" onClick={() => setRejecting(true)}>Send back</Button>
            </div>
          )
        )}
      </div>
      <div className="flex shrink-0 items-center gap-1">
        {ev.file_name && (
          <a href={`/api/evidence/${ev.id}/download`} className="rounded p-1.5 text-muted hover:bg-ink-50 hover:text-text" aria-label="Download" title="Download">
            <Download size={15} />
          </a>
        )}
        {ev.url && (
          <a href={ev.url} target="_blank" rel="noreferrer" className="rounded p-1.5 text-muted hover:bg-ink-50 hover:text-text" aria-label="Open link" title="Open link">
            <ExternalLink size={15} />
          </a>
        )}
        {canWrite && ev.trust === "uploaded" && (
          <button onClick={recheck} disabled={busy} className="rounded p-1.5 text-muted hover:bg-ink-50 hover:text-text" aria-label="Run checks again" title="Run checks again">
            <RefreshCw size={15} />
          </button>
        )}
        {canWrite && onDelete && !["automated", "policy"].includes(ev.kind) && (
          <button onClick={() => onDelete(ev)} className="rounded p-1.5 text-muted hover:bg-fail-50 hover:text-fail" aria-label="Delete evidence" title="Delete">
            <Trash2 size={15} />
          </button>
        )}
      </div>
    </div>
  );
}
