"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { ReportIncidentDrawer } from "@/components/incidents";
import { useSession } from "@/components/session";
import { Badge, Button, Empty, LoadError, Loading, PageHeader, tbl } from "@/components/ui";
import { useApi } from "@/lib/api";
import { SEVERITY } from "@/lib/constants";
import { fmtDateTime, humanize } from "@/lib/format";
import type { Incident } from "@/lib/types";

export default function IncidentsPage() {
  const router = useRouter();
  const { canWrite } = useSession();
  const { data, error, loading, reload } = useApi<Incident[]>("/incidents");
  const [creating, setCreating] = useState(false);
  if (loading && !data) return <Loading />;
  if (error || !data) return <LoadError error={error ?? "Could not load"} retry={reload} />;

  return (
    <>
      <PageHeader
        title="Incidents"
        description="Record security incidents and personal data breaches. Reporting clocks start from the time the incident was noticed, and everyone following an incident gets its updates in one email thread."
        actions={canWrite && <Button onClick={() => setCreating(true)}>Report incident</Button>}
      />
      <div className="rounded-lg border border-line bg-surface">
        {data.length ? (
          <div className={tbl.wrap}>
            <table className={tbl.table}>
              <thead>
                <tr>
                  <th className={tbl.th}>Incident</th>
                  <th className={tbl.th}>Severity</th>
                  <th className={tbl.th}>Noticed</th>
                  <th className={tbl.th}>Reporting</th>
                  <th className={tbl.th}>Status</th>
                </tr>
              </thead>
              <tbody>
                {data.map((i) => (
                  <tr key={i.id} className={tbl.row}>
                    <td className={tbl.td}>
                      <Link href={`/incidents/${i.id}`} className="hover:underline">
                        <span className="text-xs font-semibold text-muted">INC-{i.number}</span>
                        <span className="block font-medium">{i.title}</span>
                      </Link>
                    </td>
                    <td className={tbl.td}><Badge tone={SEVERITY[i.severity].tone}>{SEVERITY[i.severity].label}</Badge></td>
                    <td className={`${tbl.td} whitespace-nowrap text-muted`}>{fmtDateTime(i.detected_at)}</td>
                    <td className={tbl.td}>
                      <div className="flex flex-wrap gap-1">
                        {i.certin_reportable && <Badge tone={i.certin_reported_at ? "pass" : "fail"}>CERT-In {i.certin_reported_at ? "reported" : "pending"}</Badge>}
                        {i.personal_data_breach && <Badge tone={i.dpb_detailed_reported_at ? "pass" : "fail"}>DPDP {i.dpb_detailed_reported_at ? "reported" : "pending"}</Badge>}
                        {i.regulator_clocks.filter((c) => !c.key.includes("_")).map((c) => (
                          <Badge key={c.key} tone={c.reported_at ? "pass" : "fail"}>{c.regulator.toUpperCase()} {c.reported_at ? "reported" : "pending"}</Badge>
                        ))}
                        {!i.certin_reportable && !i.personal_data_breach && !i.regulators.length && <span className="text-muted">None required</span>}
                      </div>
                    </td>
                    <td className={`${tbl.td} text-muted`}>{humanize(i.status)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <Empty title="No incidents recorded">Report an incident as soon as it is noticed. The CERT-In clock is 6 hours.</Empty>
        )}
      </div>

      <ReportIncidentDrawer open={creating} onClose={() => setCreating(false)} onReported={(i) => router.push(`/incidents/${i.id}`)} />
    </>
  );
}
