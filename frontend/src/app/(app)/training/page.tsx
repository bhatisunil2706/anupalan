"use client";

import { Award, CheckCircle2, Clock, Download, Gamepad2, Mail, Plus, Upload, Users, Video } from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";

import { PhishingTab } from "@/components/phishing";
import { useSession } from "@/components/session";
import { Badge, Button, Checkbox, Drawer, Empty, Field, FormError, Input, LoadError, Loading, PageHeader, Panel, Select, Tabs, tbl, useToast } from "@/components/ui";
import { api, download, useApi } from "@/lib/api";
import { fmtDate } from "@/lib/format";

type Status = "passed" | "expired" | "failed" | "overdue" | "due" | "optional";
interface Course {
  slug: string; title: string; summary: string; minutes: number; category: string; audience: string;
  source: "built_in" | "custom"; published: boolean; has_scenarios: boolean; has_video: boolean; questions: number;
  required: boolean; my_status: Status; my_due: string | null; my_reason: string; my_last_completed_at: string | null;
  my_score: number | null; has_certificate: boolean;
  assignment?: { required: boolean; renew_months: number; due_days: number; departments: string[] };
}
interface Person {
  user_id: string | null; full_name: string; email: string; department: string; role: string; has_account: boolean;
  complete: boolean; courses: Record<string, Status>; due: Record<string, string | null>;
}
interface Report {
  people: Person[]; required_courses: string[]; course_titles: Record<string, string>; completion_percent: number;
  with_account_percent: number; not_invited: number;
  departments: { department: string; people: number; complete: number; percent: number; overdue: number }[];
}

const STATUS: Record<Status, { label: string; tone: "pass" | "fail" | "warn" | "prog" | "idle" }> = {
  passed: { label: "Completed", tone: "pass" },
  expired: { label: "Renewal due", tone: "warn" },
  failed: { label: "Not passed", tone: "fail" },
  overdue: { label: "Overdue", tone: "fail" },
  due: { label: "To do", tone: "prog" },
  optional: { label: "Optional", tone: "idle" },
};

type Tab = "mine" | "team" | "courses" | "phishing";

export default function TrainingPage() {
  const { isAdmin, me } = useSession();
  const [tab, setTab] = useState<Tab>("mine");
  const canSeeTeam = isAdmin || me.role === "auditor";
  useEffect(() => {
    const t = new URLSearchParams(window.location.search).get("tab") as Tab | null;
    if (t && ["team", "courses", "phishing"].includes(t)) setTab(t);
  }, []);
  const tabs: { value: Tab; label: string }[] = [{ value: "mine", label: "My learning" }];
  if (canSeeTeam) tabs.push({ value: "team", label: "Team progress" });
  if (isAdmin) tabs.push({ value: "courses", label: "Courses and assignments" }, { value: "phishing", label: "Phishing simulations" });
  return (
    <>
      <PageHeader
        title="Security training"
        description="Short, practical courses with role-based assignments, phishing simulations and certificates. Completions are evidence for the awareness training control (HR-03)."
      />
      {tabs.length > 1 && <Tabs<Tab> tabs={tabs} value={tab} onChange={setTab} />}
      {tab === "mine" && <MyLearning />}
      {tab === "team" && canSeeTeam && <TeamReport />}
      {tab === "courses" && isAdmin && <CourseAdmin />}
      {tab === "phishing" && isAdmin && <PhishingTab />}
    </>
  );
}

// ================================================================ my learning

function CourseCard({ c }: { c: Course }) {
  return (
    <Link href={`/training/${c.slug}`} className="group flex flex-col rounded-lg border border-line bg-surface p-4 hover:border-ink/40">
      <div className="flex items-start justify-between gap-3">
        <h3 className="font-semibold group-hover:text-ink">{c.title}</h3>
        <Badge tone={STATUS[c.my_status].tone}>{STATUS[c.my_status].label}</Badge>
      </div>
      <p className="mt-1.5 line-clamp-2 flex-1 text-sm text-muted">{c.summary}</p>
      <p className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted">
        <span className="flex items-center gap-1"><Clock size={12} aria-hidden /> {c.minutes} min</span>
        {c.has_scenarios && <span className="flex items-center gap-1"><Gamepad2 size={12} aria-hidden /> Practice exercises</span>}
        {c.has_video && <span className="flex items-center gap-1"><Video size={12} aria-hidden /> Video</span>}
        {c.audience !== "Everyone" && <span>For {c.audience.toLowerCase()}</span>}
        {c.required && c.my_due && c.my_status !== "passed" && <span className={c.my_status === "overdue" ? "font-medium text-fail" : ""}>Due {fmtDate(c.my_due)}</span>}
        {c.my_last_completed_at && <span className="flex items-center gap-1"><CheckCircle2 size={12} aria-hidden /> {fmtDate(c.my_last_completed_at)}{c.my_score !== null && ` · ${c.my_score}%`}</span>}
        {c.has_certificate && <span className="flex items-center gap-1 text-pass"><Award size={12} aria-hidden /> Certificate</span>}
      </p>
      {c.my_reason && c.my_status !== "passed" && <p className="mt-2 rounded bg-warn-50 px-2 py-1 text-xs text-warn">{c.my_reason}</p>}
    </Link>
  );
}

function MyLearning() {
  const { data, error, loading, reload } = useApi<Course[]>("/training/courses");
  if (loading && !data) return <Loading />;
  if (error || !data) return <LoadError error={error ?? "Could not load"} retry={reload} />;
  const visible = data.filter((c) => c.published);
  const required = visible.filter((c) => c.required);
  const todo = required.filter((c) => c.my_status !== "passed");
  const overdue = required.filter((c) => ["overdue", "expired", "failed"].includes(c.my_status)).length;
  const done = required.length - todo.length;
  const others = visible.filter((c) => !c.required);
  const categories = Array.from(new Set(others.map((c) => c.category)));

  return (
    <div className="space-y-8">
      <div className="grid gap-3 sm:grid-cols-3">
        <Stat label="Required courses completed" value={`${done} of ${required.length}`} tone={todo.length ? "prog" : "pass"} />
        <Stat label="To do" value={String(todo.length)} tone={todo.length ? "warn" : "pass"} />
        <Stat label="Overdue or renewal due" value={String(overdue)} tone={overdue ? "fail" : "pass"} />
      </div>
      {required.length > 0 && (
        <section>
          <h2 className="mb-3 text-sm font-semibold">Assigned to you</h2>
          <div className="grid gap-4 sm:grid-cols-2">{[...todo, ...required.filter((c) => c.my_status === "passed")].map((c) => <CourseCard key={c.slug} c={c} />)}</div>
        </section>
      )}
      {categories.map((cat) => (
        <section key={cat}>
          <h2 className="mb-3 text-sm font-semibold">{cat === "Your courses" ? "From your company" : `${cat}: optional`}</h2>
          <div className="grid gap-4 sm:grid-cols-2">{others.filter((c) => c.category === cat).map((c) => <CourseCard key={c.slug} c={c} />)}</div>
        </section>
      ))}
    </div>
  );
}

function Stat({ label, value, tone }: { label: string; value: string; tone: "pass" | "warn" | "fail" | "prog" }) {
  const color = { pass: "text-pass", warn: "text-warn", fail: "text-fail", prog: "text-ink" }[tone];
  return (
    <div className="rounded-lg border border-line bg-surface p-4">
      <p className={`text-2xl font-bold ${color}`}>{value}</p>
      <p className="text-xs text-muted">{label}</p>
    </div>
  );
}

// ================================================================ team progress

function TeamReport() {
  const { isAdmin } = useSession();
  const toast = useToast();
  const { data: r, error, loading, reload } = useApi<Report>("/training/report");
  const file = useRef<HTMLInputElement>(null);
  const [importError, setImportError] = useState<string | null>(null);
  const [dept, setDept] = useState("");
  const [filter, setFilter] = useState<"" | "incomplete" | "overdue" | "not_invited">("");
  const [inviting, setInviting] = useState(false);

  const people = useMemo(() => (r?.people ?? []).filter((p) =>
    (!dept || (p.department || "No department") === dept) &&
    (filter !== "incomplete" || !p.complete) &&
    (filter !== "overdue" || Object.values(p.courses).some((s) => ["overdue", "expired", "failed"].includes(s))) &&
    (filter !== "not_invited" || !p.has_account)), [r, dept, filter]);

  if (loading && !r) return <Loading />;
  if (error || !r) return <LoadError error={error ?? "Could not load"} retry={reload} />;

  async function importCsv(f: File) {
    setImportError(null);
    const form = new FormData();
    form.append("file", f);
    try {
      const res = await api<{ imported: number; skipped: string[] }>("/training/import", { method: "POST", body: form });
      toast(`Imported ${res.imported} completions${res.skipped.length ? `, skipped ${res.skipped.length} rows` : ""}`);
      reload();
    } catch (e) {
      setImportError(e instanceof Error ? e.message : "Import failed");
    }
  }

  async function inviteRoster() {
    if (!confirm(`Email an invitation to ${r!.not_invited} people from your HR roster so they can take their training?`)) return;
    setInviting(true);
    try {
      const res = await api<{ invited: number }>("/training/invite-roster", { method: "POST" });
      toast(`Invited ${res.invited} people`);
      reload();
    } catch (e) {
      toast(e instanceof Error ? e.message : "Failed", "error");
    } finally {
      setInviting(false);
    }
  }

  return (
    <div className="space-y-6">
      <div className="grid gap-3 sm:grid-cols-3">
        <Stat label="Everyone fully trained" value={`${r.completion_percent}%`} tone={r.completion_percent >= 95 ? "pass" : r.completion_percent >= 70 ? "warn" : "fail"} />
        <Stat label="People with an account fully trained" value={`${r.with_account_percent}%`} tone={r.with_account_percent >= 95 ? "pass" : "warn"} />
        <div className="rounded-lg border border-line bg-surface p-4">
          <p className={`text-2xl font-bold ${r.not_invited ? "text-warn" : "text-pass"}`}>{r.not_invited}</p>
          <p className="text-xs text-muted">In the HR roster without an account</p>
          {isAdmin && r.not_invited > 0 && <Button size="sm" variant="secondary" className="mt-2" busy={inviting} onClick={inviteRoster}><Mail size={14} aria-hidden /> Invite them</Button>}
        </div>
      </div>

      {r.departments.length > 1 && (
        <Panel title="By department">
          <ul className="space-y-2.5">
            {r.departments.map((d) => (
              <li key={d.department}>
                <button type="button" onClick={() => setDept(dept === d.department ? "" : d.department)} className="w-full text-left">
                  <div className="flex items-center justify-between text-sm">
                    <span className={dept === d.department ? "font-semibold text-ink" : ""}>{d.department}</span>
                    <span className="text-xs text-muted">{d.complete}/{d.people} complete{d.overdue ? ` · ${d.overdue} overdue` : ""}</span>
                  </div>
                  <div className="mt-1 h-2 overflow-hidden rounded bg-line">
                    <div className={`h-full ${d.percent >= 95 ? "bg-pass" : d.percent >= 70 ? "bg-warn" : "bg-fail"}`} style={{ width: `${d.percent}%` }} />
                  </div>
                </button>
              </li>
            ))}
          </ul>
        </Panel>
      )}

      <Panel
        title="People"
        flush
        actions={
          <div className="flex flex-wrap gap-2">
            <Button size="sm" variant="secondary" onClick={() => download("/training/report.csv", "training-report.csv").catch((e) => toast(e.message, "error"))}><Download size={14} aria-hidden /> Export CSV</Button>
            {isAdmin && (
              <>
                <input ref={file} type="file" accept=".csv" className="hidden" aria-label="Import completions" onChange={(e) => e.target.files?.[0] && importCsv(e.target.files[0])} />
                <Button size="sm" variant="secondary" onClick={() => file.current?.click()}><Upload size={14} aria-hidden /> Import from another LMS</Button>
              </>
            )}
          </div>
        }
      >
        <div className="flex flex-wrap gap-2 px-4 pt-3">
          <Select value={dept} onChange={(e) => setDept(e.target.value)} className="w-48" aria-label="Department">
            <option value="">All departments</option>
            {r.departments.map((d) => <option key={d.department}>{d.department}</option>)}
          </Select>
          <Select value={filter} onChange={(e) => setFilter(e.target.value as typeof filter)} className="w-48" aria-label="Show">
            <option value="">Everyone</option>
            <option value="incomplete">Not fully trained</option>
            <option value="overdue">Overdue</option>
            <option value="not_invited">No account yet</option>
          </Select>
        </div>
        <div className="px-4 pt-3"><FormError error={importError} /></div>
        {people.length === 0 ? (
          <Empty title="No one matches" />
        ) : (
          <div className={tbl.wrap}>
            <table className={tbl.table}>
              <thead>
                <tr>
                  <th className={tbl.th}>Person</th>
                  {r.required_courses.map((s) => <th key={s} className={tbl.th}>{r.course_titles[s] ?? s}</th>)}
                </tr>
              </thead>
              <tbody>
                {people.map((p) => (
                  <tr key={p.email} className={tbl.row}>
                    <td className={tbl.td}>
                      <p className="font-medium">{p.full_name}</p>
                      <p className="text-xs text-muted">{p.email}{p.department ? ` · ${p.department}` : ""}</p>
                      {!p.has_account && <Badge tone="warn" className="mt-1">No account</Badge>}
                    </td>
                    {r.required_courses.map((s) => (
                      <td key={s} className={tbl.td}>
                        {p.courses[s] ? (
                          <>
                            <Badge tone={STATUS[p.courses[s]].tone}>{STATUS[p.courses[s]].label}</Badge>
                            {p.courses[s] !== "passed" && p.due[s] && <p className="mt-1 text-xs text-muted">due {fmtDate(p.due[s])}</p>}
                          </>
                        ) : <span className="text-xs text-muted">Not assigned</span>}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {isAdmin && <p className="px-4 py-3 text-xs text-muted">Import CSV columns: email, course (name or id), completed_at, and optionally score. People without an account count towards &quot;everyone&quot;; auditors expect all staff to be trained.</p>}
      </Panel>
    </div>
  );
}

// ================================================================ admin: courses and assignments

function CourseAdmin() {
  const toast = useToast();
  const { data, error, loading, reload } = useApi<Course[]>("/training/courses");
  const depts = useApi<string[]>("/training/departments");
  const [editing, setEditing] = useState<Course | null>(null);

  if (loading && !data) return <Loading />;
  if (error || !data) return <LoadError error={error ?? "Could not load"} retry={reload} />;

  async function quickToggle(c: Course, required: boolean) {
    const a = c.assignment!;
    try {
      await api(`/training/assignments/${c.slug}`, { method: "PUT", json: { ...a, required } });
      toast(required ? `${c.title} is now required` : `${c.title} is now optional`);
      reload();
    } catch (e) {
      toast(e instanceof Error ? e.message : "Failed", "error");
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="max-w-[70ch] text-sm text-muted">Choose which courses are required, and for whom. Department targeting uses the HR roster (People page). New joiners get the same number of days from their joining date.</p>
        <Link href="/training/manage/new" className="inline-flex h-9 items-center gap-1.5 rounded-md bg-ink px-4 text-sm font-medium text-white hover:bg-ink-700"><Plus size={14} aria-hidden /> Create a course</Link>
      </div>
      <div className="rounded-lg border border-line bg-surface">
        <div className={tbl.wrap}>
          <table className={tbl.table}>
            <thead>
              <tr>
                <th className={tbl.th}>Course</th>
                <th className={tbl.th}>Required</th>
                <th className={tbl.th}>Who</th>
                <th className={tbl.th}>Due / renew</th>
                <th className={tbl.th}><span className="sr-only">Actions</span></th>
              </tr>
            </thead>
            <tbody>
              {data.map((c) => (
                <tr key={c.slug} className={tbl.row}>
                  <td className={tbl.td}>
                    <p className="font-medium">{c.title} {c.source === "custom" && <Badge tone="ink" className="ml-1">Yours</Badge>} {!c.published && <Badge tone="warn" className="ml-1">Draft</Badge>}</p>
                    <p className="text-xs text-muted">{c.category} · {c.minutes} min · {c.questions} questions{c.audience !== "Everyone" ? ` · suggested for ${c.audience.toLowerCase()}` : ""}</p>
                  </td>
                  <td className={tbl.td}>
                    <input type="checkbox" className="h-4 w-4 accent-ink" aria-label={`${c.title} required`} checked={!!c.assignment?.required} disabled={!c.published} onChange={(e) => quickToggle(c, e.target.checked)} />
                  </td>
                  <td className={`${tbl.td} text-sm`}>
                    {!c.assignment?.required ? <span className="text-muted">Optional</span> : c.assignment.departments.length ? c.assignment.departments.join(", ") : "Everyone"}
                  </td>
                  <td className={`${tbl.td} whitespace-nowrap text-xs text-muted`}>{c.assignment ? `${c.assignment.due_days} days · every ${c.assignment.renew_months} months` : "—"}</td>
                  <td className={`${tbl.td} whitespace-nowrap text-right`}>
                    <Button size="sm" variant="ghost" onClick={() => setEditing(c)}><Users size={14} aria-hidden /> Assign</Button>
                    {c.source === "custom" && <Link href={`/training/manage/${c.slug}`} className="ml-1 text-sm font-medium text-ink hover:underline">Edit</Link>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
      {editing && <AssignDrawer course={editing} departments={depts.data ?? []} onClose={() => setEditing(null)} onSaved={() => { setEditing(null); reload(); }} />}
    </div>
  );
}

function AssignDrawer({ course, departments, onClose, onSaved }: { course: Course; departments: string[]; onClose: () => void; onSaved: () => void }) {
  const toast = useToast();
  const a = course.assignment ?? { required: false, renew_months: 12, due_days: 30, departments: [] };
  const [form, setForm] = useState({ ...a, scope: a.departments.length ? "departments" : "everyone" });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function save() {
    setBusy(true);
    setError(null);
    try {
      await api(`/training/assignments/${course.slug}`, {
        method: "PUT",
        json: { required: form.required, renew_months: form.renew_months, due_days: form.due_days, departments: form.scope === "everyone" ? [] : form.departments },
      });
      toast("Assignment saved");
      onSaved();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Drawer open onClose={onClose} title={`Assign: ${course.title}`} footer={<><Button variant="ghost" onClick={onClose}>Cancel</Button><Button busy={busy} onClick={save}>Save</Button></>}>
      <FormError error={error} />
      <Checkbox label="Required" hint="Required courses show up in people's to-do list, get reminders, and count for HR-03." checked={form.required} onChange={(v) => setForm({ ...form, required: v })} />
      {form.required && (
        <>
          <fieldset className="space-y-2">
            <legend className="mb-1 text-[13px] font-medium">Who must take it</legend>
            <label className="flex items-center gap-2 text-sm"><input type="radio" className="accent-ink" checked={form.scope === "everyone"} onChange={() => setForm({ ...form, scope: "everyone" })} /> Everyone</label>
            <label className="flex items-center gap-2 text-sm"><input type="radio" className="accent-ink" checked={form.scope === "departments"} onChange={() => setForm({ ...form, scope: "departments" })} disabled={!departments.length} /> Only these departments</label>
            {!departments.length && <p className="text-xs text-muted">Add departments by importing your HR roster on the People page or connecting an HR system.</p>}
            {form.scope === "departments" && (
              <div className="ml-6 space-y-1.5">
                {departments.map((d) => (
                  <Checkbox key={d} label={d} checked={form.departments.includes(d)} onChange={(v) => setForm({ ...form, departments: v ? [...form.departments, d] : form.departments.filter((x) => x !== d) })} />
                ))}
              </div>
            )}
          </fieldset>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Days to complete" hint="From joining, or from today for current staff.">{(id) => <Input id={id} type="number" min={1} max={180} value={form.due_days} onChange={(e) => setForm({ ...form, due_days: Number(e.target.value) })} />}</Field>
            <Field label="Renew every (months)">{(id) => <Input id={id} type="number" min={1} max={36} value={form.renew_months} onChange={(e) => setForm({ ...form, renew_months: Number(e.target.value) })} />}</Field>
          </div>
        </>
      )}
    </Drawer>
  );
}
