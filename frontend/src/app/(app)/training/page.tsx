"use client";

import { CheckCircle2, Clock, Upload } from "lucide-react";
import Link from "next/link";
import { useRef, useState } from "react";

import { useSession } from "@/components/session";
import { Badge, Button, Checkbox, Empty, FormError, LoadError, Loading, PageHeader, Panel, Tabs, tbl, useToast } from "@/components/ui";
import { api, useApi } from "@/lib/api";
import { fmtDate } from "@/lib/format";

interface Course {
  slug: string;
  title: string;
  summary: string;
  minutes: number;
  required: boolean;
  renew_months: number;
  due_days: number;
  my_status: Status;
  my_last_completed_at: string | null;
  my_score: number | null;
}
type Status = "passed" | "expired" | "failed" | "overdue" | "due" | "optional";
interface Report {
  required_courses: string[];
  completion_percent: number;
  people: { user_id: string; full_name: string; email: string; role: string; complete: boolean; courses: Record<string, Status> }[];
}

const STATUS: Record<Status, { label: string; tone: "pass" | "fail" | "warn" | "prog" | "idle" }> = {
  passed: { label: "Completed", tone: "pass" },
  expired: { label: "Expired", tone: "warn" },
  failed: { label: "Not passed", tone: "fail" },
  overdue: { label: "Overdue", tone: "fail" },
  due: { label: "To do", tone: "prog" },
  optional: { label: "Optional", tone: "idle" },
};

type Tab = "mine" | "team";

export default function TrainingPage() {
  const { isAdmin, me } = useSession();
  const [tab, setTab] = useState<Tab>("mine");
  const canSeeTeam = isAdmin || me.role === "auditor";
  return (
    <>
      <PageHeader
        title="Security training"
        description="Short courses on security and India's DPDP Act. Completions count as evidence for the awareness training control (HR-03)."
      />
      {canSeeTeam && (
        <Tabs<Tab> tabs={[{ value: "mine", label: "My courses" }, { value: "team", label: "Team progress" }]} value={tab} onChange={setTab} />
      )}
      {tab === "mine" || !canSeeTeam ? <MyCourses /> : <TeamReport />}
    </>
  );
}

function MyCourses() {
  const { data, error, loading, reload } = useApi<Course[]>("/training/courses");
  if (loading && !data) return <Loading />;
  if (error || !data) return <LoadError error={error ?? "Could not load"} retry={reload} />;
  return (
    <div className="grid gap-4 sm:grid-cols-2">
      {data.map((c) => (
        <Link key={c.slug} href={`/training/${c.slug}`} className="group rounded-lg border border-line bg-surface p-4 hover:border-ink/40">
          <div className="flex items-start justify-between gap-3">
            <h2 className="font-semibold group-hover:text-ink">{c.title}</h2>
            <Badge tone={STATUS[c.my_status].tone}>{STATUS[c.my_status].label}</Badge>
          </div>
          <p className="mt-1.5 line-clamp-2 text-sm text-muted">{c.summary}</p>
          <p className="mt-3 flex items-center gap-3 text-xs text-muted">
            <span className="flex items-center gap-1"><Clock size={12} aria-hidden /> {c.minutes} min</span>
            {c.my_last_completed_at && (
              <span className="flex items-center gap-1"><CheckCircle2 size={12} aria-hidden /> {fmtDate(c.my_last_completed_at)}{c.my_score !== null && ` · ${c.my_score}%`}</span>
            )}
            {c.required && <span>Renew every {c.renew_months} months</span>}
          </p>
        </Link>
      ))}
    </div>
  );
}

function TeamReport() {
  const { isAdmin } = useSession();
  const toast = useToast();
  const report = useApi<Report>("/training/report");
  const courses = useApi<Course[]>("/training/courses");
  const file = useRef<HTMLInputElement>(null);
  const [importError, setImportError] = useState<string | null>(null);

  if ((report.loading && !report.data) || (courses.loading && !courses.data)) return <Loading />;
  if (report.error || !report.data || !courses.data) return <LoadError error={report.error ?? "Could not load"} retry={report.reload} />;
  const titles = Object.fromEntries(courses.data.map((c) => [c.slug, c.title]));
  const r = report.data;

  async function setRequired(c: Course, required: boolean) {
    await api(`/training/assignments/${c.slug}`, { method: "PUT", json: { required, renew_months: c.renew_months, due_days: c.due_days } });
    toast(required ? `${c.title} is now required` : `${c.title} is now optional`);
    courses.reload();
    report.reload();
  }

  async function importCsv(f: File) {
    setImportError(null);
    const form = new FormData();
    form.append("file", f);
    try {
      const res = await api<{ imported: number; skipped: string[] }>("/training/import", { method: "POST", body: form });
      toast(`Imported ${res.imported} completions${res.skipped.length ? `, skipped ${res.skipped.length} rows` : ""}`);
      report.reload();
    } catch (e) {
      setImportError(e instanceof Error ? e.message : "Import failed");
    }
  }

  return (
    <div className="space-y-6">
      <Panel
        title={`${r.completion_percent}% of people have completed all required training`}
        flush
        actions={
          isAdmin && (
            <>
              <input ref={file} type="file" accept=".csv" className="hidden" onChange={(e) => e.target.files?.[0] && importCsv(e.target.files[0])} />
              <Button size="sm" variant="secondary" onClick={() => file.current?.click()}><Upload size={14} aria-hidden /> Import from another LMS</Button>
            </>
          )
        }
      >
        <div className="px-4 pt-3"><FormError error={importError} /></div>
        {r.people.length === 0 ? (
          <Empty title="No one to report on yet" />
        ) : (
          <div className={tbl.wrap}>
            <table className={tbl.table}>
              <thead>
                <tr>
                  <th className={tbl.th}>Person</th>
                  {r.required_courses.map((s) => <th key={s} className={tbl.th}>{titles[s] ?? s}</th>)}
                </tr>
              </thead>
              <tbody>
                {r.people.map((p) => (
                  <tr key={p.user_id} className={tbl.row}>
                    <td className={tbl.td}><p className="font-medium">{p.full_name}</p><p className="text-xs text-muted">{p.email}</p></td>
                    {r.required_courses.map((s) => (
                      <td key={s} className={tbl.td}><Badge tone={STATUS[p.courses[s]].tone}>{STATUS[p.courses[s]].label}</Badge></td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {isAdmin && <p className="px-4 py-3 text-xs text-muted">CSV columns: email, course (name or id), completed_at, and optionally score.</p>}
      </Panel>
      {isAdmin && (
        <Panel title="Required courses">
          <div className="space-y-3">
            {courses.data.map((c) => (
              <Checkbox key={c.slug} label={c.title} hint={`${c.minutes} min · due within ${c.due_days} days of joining · renew every ${c.renew_months} months`} checked={c.required} onChange={(v) => setRequired(c, v)} />
            ))}
          </div>
        </Panel>
      )}
    </div>
  );
}
