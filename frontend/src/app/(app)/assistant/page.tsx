"use client";

import { AlertTriangle, Download, FileText, ListChecks, MessageSquareText, Sparkles, Upload } from "lucide-react";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { useSession } from "@/components/session";
import { Badge, Button, Drawer, Empty, Field, FormError, Input, LoadError, Loading, PageHeader, Panel, Select, Textarea, tbl, useToast } from "@/components/ui";
import { api, download, useApi } from "@/lib/api";
import { fmtDateTime } from "@/lib/format";
import type { Readiness } from "@/lib/types";

type Kind = "policy_draft" | "gap_analysis" | "questionnaire";
interface Status { enabled: boolean; available: boolean; model: string; used_24h: number; limit_24h: number; can_toggle: boolean }
interface JobRow { id: string; kind: Kind; title: string; status: "pending" | "running" | "done" | "failed"; error: string; created_at: string; finished_at: string | null; created_by: string | null }
interface Answer { id: string; question: string; answer: "yes" | "no" | "partial" | "unknown"; response: string; confidence: "high" | "medium" | "low"; sources: { id: string; source: string }[]; reviewed: boolean }
interface Job extends JobRow {
  input: Record<string, unknown>;
  output: {
    title?: string; body_md?: string; sources?: string[]; todo?: string[];
    framework?: string; summary?: string; items?: { refs: string[]; title: string; priority: string; effort: string; why: string; actions: string[] }[]; uncovered?: string[];
    answers?: Answer[];
  };
}

const KINDS: Record<Kind, { label: string; icon: typeof FileText; blurb: string }> = {
  policy_draft: { label: "Draft a policy", icon: FileText, blurb: "A first draft in your company's voice, consistent with your existing policies." },
  gap_analysis: { label: "Plan remediation", icon: ListChecks, blurb: "Turns unmet requirements into a prioritised plan with concrete actions." },
  questionnaire: { label: "Answer a questionnaire", icon: MessageSquareText, blurb: "Upload a customer's security questionnaire; answers cite your own policies and controls." },
};

export default function AssistantPage() {
  const { canWrite } = useSession();
  const status = useApi<Status>("/ai/status");
  const jobs = useApi<JobRow[]>("/ai/jobs");
  const [kind, setKind] = useState<Kind | null>(null);
  const [openId, setOpenId] = useState<string | null>(null);

  const running = jobs.data?.some((j) => j.status === "pending" || j.status === "running");
  useEffect(() => {
    if (!running) return;
    const t = setInterval(() => jobs.reload(), 4000);
    return () => clearInterval(t);
  }, [running, jobs]);

  if (status.loading && !status.data) return <Loading />;
  if (status.error || !status.data) return <LoadError error={status.error ?? "Could not load"} retry={status.reload} />;
  const s = status.data;

  return (
    <>
      <PageHeader
        title="AI assistant"
        description="Drafts for people to review, never final answers. Everything is grounded in your own policies and controls, with sources."
        actions={s.enabled && <span className="text-xs text-muted">{s.used_24h} of {s.limit_24h} requests used today</span>}
      />
      {!s.enabled ? (
        <Panel>
          <Empty title={s.available ? "The AI assistant is off" : "The AI assistant isn't available on this server"}>
            {s.available ? (s.can_toggle ? <>Turn it on in <Link href="/settings" className="underline">Settings &gt; Security</Link>. You&apos;ll see exactly what is shared first.</> : "Ask your workspace owner to turn it on.") : "Your administrator needs to set up an AI provider."}
          </Empty>
        </Panel>
      ) : (
        <>
          {canWrite && (
            <div className="mb-6 grid gap-3 sm:grid-cols-3">
              {(Object.keys(KINDS) as Kind[]).map((k) => {
                const K = KINDS[k];
                return (
                  <button key={k} onClick={() => setKind(k)} className="rounded-lg border border-line bg-surface p-4 text-left hover:border-ink/40">
                    <K.icon size={18} className="text-ink" aria-hidden />
                    <p className="mt-2 font-semibold">{K.label}</p>
                    <p className="mt-1 text-sm text-muted">{K.blurb}</p>
                  </button>
                );
              })}
            </div>
          )}
          <Panel title="History" flush>
            {jobs.loading && !jobs.data ? <Loading /> : !jobs.data?.length ? <Empty title="Nothing yet" /> : (
              <div className={tbl.wrap}>
                <table className={tbl.table}>
                  <thead><tr><th className={tbl.th}>Request</th><th className={tbl.th}>Status</th><th className={tbl.th}>By</th><th className={tbl.th}>When</th></tr></thead>
                  <tbody>
                    {jobs.data.map((j) => (
                      <tr key={j.id} className={`${tbl.row} cursor-pointer`} onClick={() => setOpenId(j.id)}>
                        <td className={tbl.td}>{j.title}</td>
                        <td className={tbl.td}>
                          {j.status === "done" ? <Badge tone="pass">Ready</Badge> : j.status === "failed" ? <Badge tone="fail">Failed</Badge> : <Badge tone="prog"><Sparkles size={11} className="animate-pulse" aria-hidden /> Working</Badge>}
                        </td>
                        <td className={tbl.td}>{j.created_by}</td>
                        <td className={`${tbl.td} text-muted`}>{fmtDateTime(j.created_at)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Panel>
        </>
      )}
      {kind && <NewJob kind={kind} onClose={() => setKind(null)} onCreated={(id) => { setKind(null); jobs.reload(); status.reload(); setOpenId(id); }} />}
      {openId && <JobDrawer id={openId} onClose={() => { setOpenId(null); jobs.reload(); }} />}
    </>
  );
}

function NewJob({ kind, onClose, onCreated }: { kind: Kind; onClose: () => void; onCreated: (id: string) => void }) {
  const fws = useApi<Readiness[]>(kind === "gap_analysis" ? "/frameworks/readiness" : null);
  const [topic, setTopic] = useState("");
  const [notes, setNotes] = useState("");
  const [codes, setCodes] = useState("");
  const [framework, setFramework] = useState("");
  const [questions, setQuestions] = useState<{ id: string; text: string }[]>([]);
  const file = useRef<HTMLInputElement>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function parse(f: File) {
    setError(null);
    const form = new FormData();
    form.append("file", f);
    try {
      const r = await api<{ questions: { id: string; text: string }[]; truncated?: boolean }>("/ai/questionnaire/parse", { method: "POST", body: form });
      setQuestions(r.questions);
      if (!r.questions.length) setError("No questions found. Put one question per row, with a 'Question' column header.");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't read the file");
    }
  }

  async function start() {
    setBusy(true);
    setError(null);
    const body =
      kind === "policy_draft" ? { kind, topic, notes, control_codes: codes.split(/[\s,]+/).filter(Boolean) }
      : kind === "gap_analysis" ? { kind, framework_code: framework || fws.data?.[0]?.code }
      : { kind, questions };
    try {
      const j = await api<{ id: string }>("/ai/jobs", { method: "POST", json: body });
      onCreated(j.id);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Drawer open onClose={onClose} title={KINDS[kind].label} footer={<><Button variant="secondary" onClick={onClose}>Cancel</Button><Button busy={busy} onClick={start}><Sparkles size={14} aria-hidden /> Generate</Button></>}>
      <FormError error={error} />
      {kind === "policy_draft" && (
        <>
          <Field label="What is the policy about?">{(id) => <Input id={id} placeholder="Bring your own device" value={topic} onChange={(e) => setTopic(e.target.value)} />}</Field>
          <Field label="Anything it must say" hint="Your tools, team names, decisions already made.">{(id) => <Textarea id={id} value={notes} onChange={(e) => setNotes(e.target.value)} />}</Field>
          <Field label="Controls it should cover (optional)" hint="Control codes, e.g. AST-05, HR-06">{(id) => <Input id={id} value={codes} onChange={(e) => setCodes(e.target.value)} />}</Field>
        </>
      )}
      {kind === "gap_analysis" && (
        <Field label="Framework">{(id) => <Select id={id} value={framework} onChange={(e) => setFramework(e.target.value)}>{(fws.data ?? []).map((f) => <option key={f.code} value={f.code}>{f.name} ({f.percent}% ready)</option>)}</Select>}</Field>
      )}
      {kind === "questionnaire" && (
        <>
          <input ref={file} type="file" accept=".csv,.xlsx" className="hidden" onChange={(e) => e.target.files?.[0] && parse(e.target.files[0])} />
          <Button variant="secondary" onClick={() => file.current?.click()}><Upload size={14} aria-hidden /> Upload .xlsx or .csv</Button>
          {questions.length > 0 && (
            <div>
              <p className="mb-2 text-sm font-medium">{questions.length} questions found</p>
              <ol className="max-h-72 list-decimal space-y-1 overflow-y-auto pl-5 text-sm text-muted">{questions.slice(0, 50).map((q) => <li key={q.id}>{q.text}</li>)}</ol>
            </div>
          )}
        </>
      )}
      <p className="text-xs text-muted">Your policies and control descriptions relevant to this request are sent to the AI provider. Evidence files and personal data are not.</p>
    </Drawer>
  );
}

function JobDrawer({ id, onClose }: { id: string; onClose: () => void }) {
  const { canWrite } = useSession();
  const toast = useToast();
  const { data, error, loading, reload, setData } = useApi<Job>(`/ai/jobs/${id}`);
  const pending = data && (data.status === "pending" || data.status === "running");
  useEffect(() => {
    if (!pending) return;
    const t = setInterval(reload, 3000);
    return () => clearInterval(t);
  }, [pending, reload]);

  return (
    <Drawer open onClose={onClose} title={data?.title ?? "Result"} wide>
      {loading && !data ? <Loading /> : error || !data ? <LoadError error={error ?? "Could not load"} /> : pending ? (
        <Loading label="Working on it. This usually takes under a minute" />
      ) : data.status === "failed" ? (
        <p className="rounded-md border border-fail/25 bg-fail-50 p-3 text-sm text-fail">{data.error}</p>
      ) : (
        <>
          <p className="flex items-start gap-2 rounded-md bg-warn-50 p-3 text-xs text-warn"><AlertTriangle size={14} className="mt-0.5 shrink-0" aria-hidden /> AI-generated draft. Check every statement against how you actually work before using it.</p>
          {data.kind === "policy_draft" && <PolicyResult job={data} canWrite={canWrite} />}
          {data.kind === "gap_analysis" && <GapResult job={data} />}
          {data.kind === "questionnaire" && <QuestionnaireResult job={data} canWrite={canWrite} onSaved={(j) => { setData(j); toast("Answers saved"); }} />}
        </>
      )}
    </Drawer>
  );
}

function PolicyResult({ job, canWrite }: { job: Job; canWrite: boolean }) {
  const [saved, setSaved] = useState<string | null>(null);
  const o = job.output;
  return (
    <>
      {canWrite && (
        saved ? <Link href={`/policies/${saved}`} className="text-sm font-medium underline">Open the draft policy</Link>
          : <Button onClick={async () => setSaved((await api<{ policy_id: string }>(`/ai/jobs/${job.id}/save-policy`, { method: "POST" })).policy_id)}>Save as draft policy</Button>
      )}
      {o.todo && o.todo.length > 0 && (
        <div className="rounded-md border border-line p-3 text-sm"><p className="font-medium">Open questions</p><ul className="ml-5 mt-1 list-disc text-muted">{o.todo.map((t, i) => <li key={i}>{t}</li>)}</ul></div>
      )}
      <article className="space-y-3 text-sm leading-relaxed [&_h1]:text-lg [&_h1]:font-bold [&_h2]:mt-4 [&_h2]:font-semibold [&_li]:ml-5 [&_ol]:list-decimal [&_ul]:list-disc">
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{o.body_md ?? ""}</ReactMarkdown>
      </article>
      {o.sources && o.sources.length > 0 && <p className="text-xs text-muted">Based on: {o.sources.join(", ")}</p>}
    </>
  );
}

function GapResult({ job }: { job: Job }) {
  const o = job.output;
  const tone = { high: "fail", medium: "warn", low: "idle" } as const;
  return (
    <>
      {o.summary && <p className="text-sm">{o.summary}</p>}
      <ol className="space-y-3">
        {(o.items ?? []).map((it, i) => (
          <li key={i} className="rounded-md border border-line p-3 text-sm">
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-semibold">{i + 1}. {it.title}</span>
              <Badge tone={tone[it.priority as keyof typeof tone] ?? "idle"}>{it.priority} priority</Badge>
              <Badge>{it.effort}</Badge>
            </div>
            <p className="mt-1 text-xs text-muted">{it.refs.join(", ")}</p>
            {it.why && <p className="mt-2">{it.why}</p>}
            <ul className="ml-5 mt-2 list-disc">{it.actions.map((a, j) => <li key={j}>{a}</li>)}</ul>
          </li>
        ))}
      </ol>
      {o.uncovered && o.uncovered.length > 0 && <p className="text-xs text-muted">Not covered by the plan: {o.uncovered.join(", ")}</p>}
    </>
  );
}

function QuestionnaireResult({ job, canWrite, onSaved }: { job: Job; canWrite: boolean; onSaved: (j: Job) => void }) {
  const [answers, setAnswers] = useState<Answer[]>(job.output.answers ?? []);
  const [busy, setBusy] = useState(false);
  const toast = useToast();
  const reviewed = answers.filter((a) => a.reviewed).length;
  const tone = { high: "pass", medium: "warn", low: "fail" } as const;

  async function save() {
    setBusy(true);
    try {
      onSaved(await api<Job>(`/ai/jobs/${job.id}/answers`, { method: "PUT", json: answers.map((a) => ({ id: a.id, answer: a.answer, response: a.response, reviewed: a.reviewed })) }));
    } catch (e) {
      toast(e instanceof Error ? e.message : "Failed", "error");
    } finally {
      setBusy(false);
    }
  }
  const update = (i: number, patch: Partial<Answer>) => setAnswers(answers.map((a, j) => (j === i ? { ...a, ...patch } : a)));

  return (
    <>
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm text-muted">{reviewed} of {answers.length} reviewed</span>
        <span className="flex-1" />
        {canWrite && <Button size="sm" variant="secondary" busy={busy} onClick={save}>Save edits</Button>}
        <Button size="sm" variant="secondary" onClick={() => download(`/ai/jobs/${job.id}/export.xlsx`, "questionnaire-answers.xlsx")}><Download size={14} aria-hidden /> Export .xlsx</Button>
      </div>
      <ol className="space-y-3">
        {answers.map((a, i) => (
          <li key={a.id} className="rounded-md border border-line p-3 text-sm">
            <p className="font-medium">{a.id}. {a.question}</p>
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <Select aria-label="Answer" value={a.answer} disabled={!canWrite} onChange={(e) => update(i, { answer: e.target.value as Answer["answer"], reviewed: true })} className="w-32">
                <option value="yes">Yes</option><option value="no">No</option><option value="partial">Partial</option><option value="unknown">Unknown</option>
              </Select>
              <Badge tone={tone[a.confidence]}>{a.confidence} confidence</Badge>
              {a.reviewed && <Badge tone="pass">Reviewed</Badge>}
            </div>
            <Textarea className="mt-2" aria-label="Response" value={a.response} disabled={!canWrite} onChange={(e) => update(i, { response: e.target.value, reviewed: true })} />
            {a.sources.length > 0 && <p className="mt-1 text-xs text-muted">Sources: {a.sources.map((s) => s.source).join("; ")}</p>}
          </li>
        ))}
      </ol>
    </>
  );
}
