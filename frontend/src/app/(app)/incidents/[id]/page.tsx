"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import { IncidentActivity } from "@/components/incidents";
import { MemberSelect } from "@/components/pickers";
import { useSession } from "@/components/session";
import { Badge, Button, Checkbox, Field, Input, LoadError, Loading, Panel, Select, Textarea, cx, useToast } from "@/components/ui";
import { api, useApi } from "@/lib/api";
import { SEVERITY } from "@/lib/constants";
import { countdown, fmtDateTime, isoToLocal, localToIso } from "@/lib/format";
import type { Incident } from "@/lib/types";

type StampKey = "certin_reported_at" | "dpb_initial_reported_at" | "dpb_detailed_reported_at" | "principals_notified_at";

function useNow(intervalMs = 30000) {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), intervalMs);
    return () => clearInterval(t);
  }, [intervalMs]);
  return now;
}

export default function IncidentPage() {
  const { id } = useParams<{ id: string }>();
  const { canWrite } = useSession();
  const toast = useToast();
  const now = useNow();
  const { data: inc, error, loading, reload } = useApi<Incident>(`/incidents/${id}`);
  const [version, setVersion] = useState(0);
  const [form, setForm] = useState({ status: "open", severity: "sev3", lead_id: "", root_cause: "", actions_taken: "", lessons_learned: "", affected: "" });

  useEffect(() => {
    if (inc)
      setForm({
        status: inc.status, severity: inc.severity, lead_id: inc.lead?.id ?? "", root_cause: inc.root_cause,
        actions_taken: inc.actions_taken, lessons_learned: inc.lessons_learned, affected: inc.affected_principals_estimate?.toString() ?? "",
      });
  }, [inc]);

  if (loading && !inc) return <Loading />;
  if (error || !inc) return <LoadError error={error ?? "Could not load"} retry={reload} />;

  async function patch(body: Record<string, unknown>, msg = "Saved") {
    try {
      await api(`/incidents/${id}`, { method: "PATCH", json: body });
      toast(msg);
      reload();
      setVersion((v) => v + 1);
    } catch (e) {
      toast(e instanceof Error ? e.message : "Failed", "error");
    }
  }

  const clocks: { key: StampKey; title: string; rule: string; due: string | null; show: boolean }[] = [
    { key: "certin_reported_at", title: "Report to CERT-In", rule: "Within 6 hours of noticing (CERT-In Directions, para (ii))", due: inc.certin_due_at, show: inc.certin_reportable },
    { key: "principals_notified_at", title: "Notify affected data principals", rule: "Without delay (DPDP Rules R.7(1))", due: null, show: inc.personal_data_breach },
    { key: "dpb_initial_reported_at", title: "Initial intimation to the Data Protection Board", rule: "Without delay (DPDP Rules R.7(2))", due: null, show: inc.personal_data_breach },
    { key: "dpb_detailed_reported_at", title: "Detailed report to the Board", rule: "Within 72 hours of becoming aware (DPDP Rules R.7(2))", due: inc.dpb_due_at, show: inc.personal_data_breach },
  ];

  return (
    <>
      <nav className="mb-3 text-sm text-muted">
        <Link href="/incidents" className="hover:underline">Incidents</Link> / INC-{inc.number}
      </nav>
      <header className="mb-6">
        <div className="flex flex-wrap items-center gap-2">
          <Badge tone={SEVERITY[inc.severity].tone}>{SEVERITY[inc.severity].label}</Badge>
          <span className="text-sm text-muted">Noticed {fmtDateTime(inc.detected_at)}</span>
        </div>
        <h1 className="mt-1 text-[22px] font-bold tracking-[-0.01em]">{inc.title}</h1>
        {inc.reported_by && <p className="mt-1 text-xs text-muted">Reported by {inc.reported_by.full_name} · {fmtDateTime(inc.created_at)}</p>}
        {inc.description && <p className="mt-2 max-w-[72ch] whitespace-pre-wrap text-sm text-muted">{inc.description}</p>}
      </header>

      <div className="grid grid-cols-1 gap-6 [&>*]:min-w-0 lg:grid-cols-[minmax(0,1fr)_320px]">
        <div className="space-y-6">
          <Panel title="Regulatory reporting" flush>
            {clocks.some((c) => c.show) ? (
              <ul>
                {clocks.filter((c) => c.show).map((c) => {
                  const done = inc[c.key];
                  const cd = c.due ? countdown(c.due, now) : null;
                  return (
                    <li key={c.key} className={cx("flex flex-wrap items-center gap-4 border-b border-line px-4 py-4 last:border-0", !done && cd?.overdue && "bg-fail-50/50")}>
                      <div className="min-w-0 flex-1">
                        <p className="text-sm font-semibold">{c.title}</p>
                        <p className="text-xs text-muted">{c.rule}</p>
                      </div>
                      {done ? (
                        <div className="text-right">
                          <Badge tone="pass">Done</Badge>
                          <p className="mt-1 text-xs text-muted">{fmtDateTime(done)}</p>
                        </div>
                      ) : (
                        <>
                          <div className="text-right">
                            {cd ? (
                              <>
                                <p className={cx("text-lg font-bold", cd.overdue ? "text-fail" : "text-text")}>{cd.text}</p>
                                <p className="text-xs text-muted">Due {fmtDateTime(c.due)}</p>
                              </>
                            ) : (
                              <p className="text-sm font-semibold text-warn">Do this now</p>
                            )}
                          </div>
                          {canWrite && <Button size="sm" onClick={() => patch({ [c.key]: new Date().toISOString() }, "Recorded")}>Mark done now</Button>}
                        </>
                      )}
                    </li>
                  );
                })}
              </ul>
            ) : (
              <p className="px-4 py-5 text-sm text-muted">This incident is not marked as CERT-In reportable or as a personal data breach, so no regulator deadline applies.</p>
            )}
            {canWrite && (
              <div className="space-y-3 border-t border-line bg-paper/50 px-4 py-4">
                <Checkbox label="Reportable to CERT-In" checked={inc.certin_reportable} onChange={(v) => patch({ certin_reportable: v }, "Updated")} />
                <Checkbox label="Personal data breach (DPDP)" checked={inc.personal_data_breach} onChange={(v) => patch({ personal_data_breach: v }, "Updated")} />
              </div>
            )}
          </Panel>

          {canWrite && clocks.some((c) => c.show && inc[c.key]) && (
            <Panel title="Correct a recorded time">
              <div className="grid gap-3 sm:grid-cols-2">
                {clocks.filter((c) => c.show && inc[c.key]).map((c) => (
                  <Field key={c.key} label={`${c.title} (IST)`}>
                    {(fid) => (
                      <Input
                        id={fid}
                        type="datetime-local"
                        defaultValue={isoToLocal(inc[c.key])}
                        onBlur={(e) => e.target.value && patch({ [c.key]: localToIso(e.target.value) }, "Time corrected")}
                      />
                    )}
                  </Field>
                ))}
              </div>
            </Panel>
          )}

          <IncidentActivity incident={inc} version={version} part="timeline" />

          <Panel title="Investigation">
            <div className="space-y-4">
              <Field label="Root cause">{(fid) => <Textarea id={fid} value={form.root_cause} disabled={!canWrite} onChange={(e) => setForm({ ...form, root_cause: e.target.value })} />}</Field>
              <Field label="Actions taken">{(fid) => <Textarea id={fid} value={form.actions_taken} disabled={!canWrite} onChange={(e) => setForm({ ...form, actions_taken: e.target.value })} />}</Field>
              <Field label="Lessons learned">{(fid) => <Textarea id={fid} value={form.lessons_learned} disabled={!canWrite} onChange={(e) => setForm({ ...form, lessons_learned: e.target.value })} />}</Field>
              {canWrite && (
                <div className="flex justify-end">
                  <Button onClick={() => patch({ root_cause: form.root_cause, actions_taken: form.actions_taken, lessons_learned: form.lessons_learned }, "Investigation saved")}>
                    Save investigation
                  </Button>
                </div>
              )}
            </div>
          </Panel>

        </div>

        <aside>
          <Panel title="Details">
            <div className="space-y-4">
              <Field label="Status">
                {(fid) => (
                  <Select id={fid} value={form.status} disabled={!canWrite} onChange={(e) => patch({ status: e.target.value }, "Status updated")}>
                    {["open", "contained", "resolved", "closed"].map((s) => <option key={s} value={s}>{s[0].toUpperCase() + s.slice(1)}</option>)}
                  </Select>
                )}
              </Field>
              <Field label="Severity">
                {(fid) => (
                  <Select id={fid} value={form.severity} disabled={!canWrite} onChange={(e) => patch({ severity: e.target.value }, "Severity updated")}>
                    {Object.entries(SEVERITY).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
                  </Select>
                )}
              </Field>
              <Field label="Incident lead">
                {(fid) => <MemberSelect id={fid} value={form.lead_id} disabled={!canWrite} onChange={(v) => patch({ lead_id: v || null }, "Lead updated")} />}
              </Field>
              {inc.personal_data_breach && (
                <Field label="Estimated people affected">
                  {(fid) => (
                    <Input
                      id={fid}
                      type="number"
                      min={0}
                      value={form.affected}
                      disabled={!canWrite}
                      onChange={(e) => setForm({ ...form, affected: e.target.value })}
                      onBlur={() => patch({ affected_principals_estimate: form.affected ? Number(form.affected) : null })}
                    />
                  )}
                </Field>
              )}
            </div>
          </Panel>
          <IncidentActivity incident={inc} version={version} part="followers" />
        </aside>
      </div>
    </>
  );
}
