"use client";

import { ShieldCheck } from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";

import { EvidenceItem } from "@/components/evidence";
import { useSession } from "@/components/session";
import { Empty, LoadError, Loading, PageHeader, Select, Tabs } from "@/components/ui";
import { useApi } from "@/lib/api";
import { fmtDate } from "@/lib/format";
import type { Evidence } from "@/lib/types";

type Row = Evidence & { control: { id: string; code: string; title: string }; acceptance_criteria?: string[]; warnings?: number };
interface Queue { pending: Row[]; recent: Row[]; require_review: boolean; ai_checks: boolean }

export default function EvidenceReviewPage() {
  const { canWrite, isAdmin } = useSession();
  const { data, error, loading, reload } = useApi<Queue>("/evidence/review-queue");
  const [tab, setTab] = useState<"pending" | "recent">("pending");
  const [filter, setFilter] = useState<"mine" | "all" | "warnings">("mine");

  const rows = useMemo(() => {
    const list = data?.pending ?? [];
    if (filter === "mine") return list.filter((e) => e.can_review);
    if (filter === "warnings") return list.filter((e) => (e.warnings ?? 0) > 0);
    return list;
  }, [data, filter]);

  if (loading && !data) return <Loading />;
  if (error || !data) return <LoadError error={error ?? "Could not load"} retry={reload} />;
  const mine = data.pending.filter((e) => e.can_review).length;

  return (
    <>
      <PageHeader
        title="Evidence review"
        description="Evidence uploaded by people counts only after someone else checks it. Automatic checks and, if turned on, the AI check flag likely problems; you make the call."
      />
      <div className="mb-4 flex flex-wrap gap-2 text-xs">
        <span className={`rounded-full px-2.5 py-1 ${data.require_review ? "bg-pass-50 text-pass" : "bg-warn-50 text-warn"}`}>
          Second-person review is {data.require_review ? "on" : "off"}
        </span>
        <span className={`rounded-full px-2.5 py-1 ${data.ai_checks ? "bg-pass-50 text-pass" : "bg-ink-50 text-muted"}`}>
          AI evidence checks {data.ai_checks ? "on" : "off"}
        </span>
        {isAdmin && <Link href="/settings#evidence" className="self-center font-medium text-ink hover:underline">Change in settings</Link>}
      </div>
      <Tabs tabs={[{ value: "pending", label: `Waiting (${data.pending.length})` }, { value: "recent", label: "Recently reviewed" }]} value={tab} onChange={setTab} />
      {tab === "pending" ? (
        <>
          <div className="mb-3 flex items-center gap-2">
            <Select aria-label="Show" value={filter} onChange={(e) => setFilter(e.target.value as typeof filter)} className="w-56">
              <option value="mine">For me to review ({mine})</option>
              <option value="warnings">With warnings</option>
              <option value="all">Everything waiting ({data.pending.length})</option>
            </Select>
          </div>
          {rows.length === 0 ? (
            <div className="rounded-lg border border-line bg-surface">
              <Empty title={filter === "mine" ? "Nothing for you to review" : "Nothing waiting"}>
                {filter === "mine" && data.pending.length > 0 ? "Other evidence is waiting for its control owner or another admin. You can't review evidence you added yourself." : "New uploads appear here for a second person to check."}
              </Empty>
            </div>
          ) : (
            <ul className="space-y-3">
              {rows.map((ev) => (
                <li key={ev.id} className="rounded-lg border border-line bg-surface">
                  <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line px-4 py-2 text-sm">
                    <Link href={`/controls/${ev.control.id}`} className="font-medium hover:underline">{ev.control.code} {ev.control.title}</Link>
                    <span className="text-xs text-muted">waiting since {fmtDate(ev.collected_at)}</span>
                  </div>
                  {!!ev.acceptance_criteria?.length && (
                    <details className="border-b border-line px-4 py-2 text-xs text-muted">
                      <summary className="cursor-pointer font-medium text-text">What the evidence must show ({ev.acceptance_criteria.length})</summary>
                      <ol className="mt-1 list-decimal space-y-0.5 pl-5">{ev.acceptance_criteria.map((c) => <li key={c}>{c}</li>)}</ol>
                    </details>
                  )}
                  <div className="px-4 py-3">
                    <EvidenceItem ev={ev} canWrite={canWrite} criteria={ev.acceptance_criteria} onChanged={reload} />
                  </div>
                </li>
              ))}
            </ul>
          )}
        </>
      ) : data.recent.length === 0 ? (
        <div className="rounded-lg border border-line bg-surface"><Empty title="No reviews yet" /></div>
      ) : (
        <ul className="divide-y divide-line rounded-lg border border-line bg-surface">
          {data.recent.map((ev) => (
            <li key={ev.id} className="px-4 py-3">
              <p className="mb-1 flex items-center gap-1.5 text-xs text-muted">
                <ShieldCheck size={13} aria-hidden /> {ev.control.code} · {ev.review_status === "approved" ? "approved" : "sent back"} by {ev.reviewed_by?.full_name} on {ev.reviewed_at ? fmtDate(ev.reviewed_at) : ""}
              </p>
              <EvidenceItem ev={ev} canWrite={false} onChanged={reload} />
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
