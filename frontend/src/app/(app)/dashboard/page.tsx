"use client";

import { Siren } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { OpenIncidents, ReportIncidentDrawer } from "@/components/incidents";
import { Seal } from "@/components/seal";
import { useSession } from "@/components/session";
import { Badge, Button, HEALTH, HealthBadge, LoadError, Loading, PageHeader, Panel, cx } from "@/components/ui";
import { useApi } from "@/lib/api";
import { countdown, fmtDate, fmtDateTime, humanize } from "@/lib/format";
import type { Health, Readiness } from "@/lib/types";

interface Dashboard {
  readiness: Readiness[];
  control_counts: Record<Health, number>;
  total_controls: number;
  attention: { id: string; code: string; title: string; health: Health }[];
  open_tasks: number;
  overdue_tasks: number;
  my_tasks: { id: string; title: string; due_date: string | null; priority: string }[];
  deadlines: { kind: string; label: string; due_at: string; link: string; overdue: boolean }[];
  open_incidents: { id: string; number: number; title: string; severity: string; status: string; detected_at: string }[];
  policies_to_acknowledge: { id: string; title: string; version: number }[];
  vendor_reviews_due: { id: string; name: string; next_review_date: string }[];
  activity: { at: string; action: string; user: string }[];
}

const DEADLINE_KIND: Record<string, string> = {
  certin: "CERT-In 6h",
  dpb: "DPDP 72h",
  principals: "Notify users",
  regulator: "Regulator",
  request: "Rights request",
  task: "Task",
};

const BAR_ORDER: Health[] = ["passing", "needs_evidence", "failing", "in_progress", "not_started", "not_applicable"];
const BAR_COLOR: Record<Health, string> = {
  passing: "bg-pass",
  needs_evidence: "bg-warn",
  failing: "bg-fail",
  in_progress: "bg-prog",
  not_started: "bg-line",
  not_applicable: "bg-idle/40",
};

export default function DashboardPage() {
  const { me, canWrite } = useSession();
  const { data, error, loading, reload } = useApi<Dashboard>("/dashboard");
  const [reporting, setReporting] = useState(false);

  if (loading && !data) return <Loading />;
  if (error || !data) return <LoadError error={error ?? "Could not load"} retry={reload} />;

  const orgName = me.memberships.find((m) => m.org_id === me.org_id)?.org_name;

  return (
    <>
      <PageHeader
        title="Dashboard"
        description={`Compliance status for ${orgName}`}
        actions={canWrite && (
          <Button variant="danger" onClick={() => setReporting(true)}>
            <Siren className="h-4 w-4" aria-hidden /> Report incident
          </Button>
        )}
      />
      <ReportIncidentDrawer open={reporting} onClose={() => { setReporting(false); reload(); }} />

      <Panel className="mb-6">
        <div className="grid grid-cols-2 gap-6 py-2 sm:grid-cols-4">
          {data.readiness.map((r) => (
            <Link key={r.code} href={`/frameworks/${r.code}`} className="rounded-md py-2 hover:bg-ink-50/50">
              <Seal percent={r.percent} label={r.short_name} sublabel={`${r.met} of ${r.total} requirements met`} />
            </Link>
          ))}
          {!data.readiness.length && (
            <p className="col-span-full text-sm text-muted">
              No frameworks enabled. <Link href="/frameworks" className="text-ink underline">Choose frameworks</Link>
            </p>
          )}
        </div>
      </Panel>

      <div className="grid grid-cols-1 gap-6 [&>*]:min-w-0 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
        <div className="space-y-6">
          {data.open_incidents.length > 0 && (
            <Panel
              title="Open incidents"
              actions={<Link href="/incidents" className="text-xs font-medium text-ink hover:underline">All incidents</Link>}
              flush
            >
              <OpenIncidents items={data.open_incidents} />
            </Panel>
          )}
          <Panel title="Deadlines" flush>
            {data.deadlines.length ? (
              <ul>
                {data.deadlines.map((d, i) => {
                  const cd = d.kind === "principals" ? { text: "Without delay", overdue: true } : countdown(d.due_at);
                  return (
                    <li key={i} className="flex items-center gap-3 border-b border-line px-4 py-3 last:border-0">
                      <Badge tone={d.kind === "certin" || d.kind === "dpb" || d.kind === "regulator" ? "fail" : d.kind === "request" ? "ink" : "idle"}>
                        {DEADLINE_KIND[d.kind] ?? d.kind}
                      </Badge>
                      <Link href={d.link} className="min-w-0 flex-1 truncate text-sm hover:underline">
                        {d.label}
                      </Link>
                      <span className={cx("whitespace-nowrap text-xs font-medium", cd.overdue ? "text-fail" : "text-muted")} title={fmtDateTime(d.due_at)}>
                        {cd.text}
                      </span>
                    </li>
                  );
                })}
              </ul>
            ) : (
              <p className="px-4 py-6 text-sm text-muted">Nothing due in the next 7 days.</p>
            )}
          </Panel>

          <Panel title="Controls that need attention" actions={<Link href="/controls" className="text-xs font-medium text-ink hover:underline">All controls</Link>} flush>
            {data.attention.length ? (
              <ul>
                {data.attention.map((c) => (
                  <li key={c.id} className="border-b border-line last:border-0">
                    <Link href={`/controls/${c.id}`} className="flex items-center gap-3 px-4 py-3 hover:bg-ink-50/40">
                      <span className="w-16 shrink-0 text-xs font-semibold text-muted">{c.code}</span>
                      <span className="min-w-0 flex-1 truncate text-sm">{c.title}</span>
                      <HealthBadge health={c.health} />
                    </Link>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="px-4 py-6 text-sm text-muted">No failing checks or missing evidence on implemented controls.</p>
            )}
          </Panel>

          <Panel title="Recent activity" flush>
            <ul className="text-sm">
              {data.activity.map((a, i) => (
                <li key={i} className="flex gap-3 border-b border-line px-4 py-2.5 last:border-0">
                  <span className="w-28 shrink-0 text-xs text-muted">{fmtDateTime(a.at)}</span>
                  <span>
                    <span className="font-medium">{a.user}</span> <span className="text-muted">{humanize(a.action.replace(".", " "))}</span>
                  </span>
                </li>
              ))}
            </ul>
          </Panel>
        </div>

        <div className="space-y-6">
          <Panel title={`Controls (${data.total_controls})`}>
            <div className="flex h-3 overflow-hidden rounded-sm bg-paper" aria-hidden>
              {BAR_ORDER.map((h) =>
                data.control_counts[h] ? (
                  <div key={h} className={BAR_COLOR[h]} style={{ width: `${(100 * data.control_counts[h]) / Math.max(1, data.total_controls)}%` }} />
                ) : null,
              )}
            </div>
            <dl className="mt-4 grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
              {BAR_ORDER.map((h) => (
                <div key={h} className="flex items-center justify-between gap-2">
                  <dt className="flex items-center gap-2 text-muted">
                    <span className={cx("h-2.5 w-2.5 rounded-sm", BAR_COLOR[h])} aria-hidden />
                    {HEALTH[h].label}
                  </dt>
                  <dd className="font-semibold">{data.control_counts[h]}</dd>
                </div>
              ))}
            </dl>
          </Panel>

          <Panel
            title="My tasks"
            actions={
              <Link href="/tasks" className="text-xs font-medium text-ink hover:underline">
                {data.open_tasks} open{data.overdue_tasks ? `, ${data.overdue_tasks} overdue` : ""}
              </Link>
            }
            flush
          >
            {data.my_tasks.length ? (
              <ul>
                {data.my_tasks.map((t) => (
                  <li key={t.id} className="flex items-center justify-between gap-3 border-b border-line px-4 py-2.5 text-sm last:border-0">
                    <span className="min-w-0 truncate">{t.title}</span>
                    <span className="whitespace-nowrap text-xs text-muted">{t.due_date ? fmtDate(t.due_date) : "No due date"}</span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="px-4 py-5 text-sm text-muted">Nothing assigned to you.</p>
            )}
          </Panel>

          {data.policies_to_acknowledge.length > 0 && (
            <Panel title="Policies to read and acknowledge" flush>
              <ul>
                {data.policies_to_acknowledge.map((p) => (
                  <li key={p.id} className="border-b border-line last:border-0">
                    <Link href={`/policies/${p.id}`} className="flex justify-between px-4 py-2.5 text-sm hover:bg-ink-50/40">
                      {p.title}
                      <span className="text-xs text-muted">v{p.version}</span>
                    </Link>
                  </li>
                ))}
              </ul>
            </Panel>
          )}

          {data.vendor_reviews_due.length > 0 && (
            <Panel title="Vendor reviews due" flush>
              <ul>
                {data.vendor_reviews_due.map((v) => (
                  <li key={v.id} className="flex justify-between border-b border-line px-4 py-2.5 text-sm last:border-0">
                    <Link href="/vendors" className="hover:underline">{v.name}</Link>
                    <span className="text-xs text-muted">{fmtDate(v.next_review_date)}</span>
                  </li>
                ))}
              </ul>
            </Panel>
          )}
        </div>
      </div>
    </>
  );
}
