"use client";

import { CheckCircle2, FileUp, Lock } from "lucide-react";
import { useParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { Button, Field, FormError, Input, Loading, Select, Textarea, cx, useToast } from "@/components/ui";
import { api } from "@/lib/api";

interface Question { id: string; section: string; text: string; type: "yes_no" | "text" | "choice"; evidence?: boolean; weight?: number; options?: string[]; guidance?: string; refs?: string }
interface Info {
  org_name: string; vendor_name: string; title: string; description: string; questions: Question[];
  answers: Record<string, { answer: string; comment: string }>; status: string; expires_at: string; respondent_name: string;
  doc_kinds: Record<string, string>; documents: { kind: string; title: string; file_name: string }[];
}
type Answers = Record<string, { answer: string; comment: string }>;

export default function VendorQuestionnairePage() {
  const { token } = useParams<{ token: string }>();
  const toast = useToast();
  const [info, setInfo] = useState<Info | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [answers, setAnswers] = useState<Answers>({});
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const dirty = useRef(false);

  useEffect(() => {
    api<Info>(`/public/assessments/${token}`)
      .then((d) => { setInfo(d); setAnswers(d.answers); setName(d.respondent_name); setSubmitted(d.status === "submitted" || d.status === "reviewed"); })
      .catch((e) => setLoadError(e instanceof Error ? e.message : "This link isn't valid"));
  }, [token]);

  useEffect(() => {
    const warn = (e: BeforeUnloadEvent) => { if (dirty.current) e.preventDefault(); };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, []);

  if (loadError) return <Shell><p className="rounded-lg border border-line bg-surface p-6 text-sm">{loadError}. Ask your contact for a new link.</p></Shell>;
  if (!info) return <Loading />;

  const set = (id: string, patch: Partial<{ answer: string; comment: string }>) => {
    dirty.current = true;
    setAnswers((a) => ({ ...a, [id]: { ...(a[id] ?? { answer: "", comment: "" }), ...patch } }));
  };
  const yesNo = info.questions.filter((q) => q.type === "yes_no" || q.type === "choice");
  const answered = yesNo.filter((q) => answers[q.id]?.answer).length;
  const naMissing = info.questions.filter((q) => q.type === "yes_no" && q.weight && answers[q.id]?.answer === "na" && !answers[q.id]?.comment?.trim()).length;
  const sections = Array.from(new Set(info.questions.map((q) => q.section)));

  async function save() {
    setBusy(true);
    setError(null);
    try {
      await api(`/public/assessments/${token}`, { method: "PUT", json: { answers, respondent_name: name } });
      dirty.current = false;
      toast("Progress saved. You can close this page and come back with the same link.");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't save");
    } finally {
      setBusy(false);
    }
  }
  async function submit() {
    setBusy(true);
    setError(null);
    try {
      await api(`/public/assessments/${token}/submit`, { method: "POST", json: { answers, respondent_name: name } });
      dirty.current = false;
      setSubmitted(true);
      window.scrollTo({ top: 0 });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't submit");
    } finally {
      setBusy(false);
    }
  }

  if (submitted) {
    return (
      <Shell org={info.org_name}>
        <div className="rounded-lg border border-pass/30 bg-pass-50 p-6">
          <CheckCircle2 className="text-pass" aria-hidden />
          <h1 className="mt-2 text-lg font-semibold">Thank you, the questionnaire has been submitted</h1>
          <p className="mt-1 text-sm">{info.org_name} will review your answers and may follow up with questions.</p>
        </div>
      </Shell>
    );
  }

  return (
    <Shell org={info.org_name}>
      <h1 className="text-[22px] font-bold tracking-[-0.01em]">{info.title}</h1>
      <p className="mt-1 text-sm text-muted">{info.org_name} has asked {info.vendor_name} to answer these questions. {info.description}</p>
      <p className="mt-2 text-xs text-muted">Link valid until {new Date(info.expires_at).toLocaleDateString("en-IN", { day: "numeric", month: "long", year: "numeric" })}. Save as you go; submit when every yes/no and choice question is answered. If a question doesn&apos;t apply, choose N/A and say why.</p>

      <div className="sticky top-0 z-10 -mx-4 mt-6 border-b border-line bg-paper/95 px-4 py-2 text-sm backdrop-blur">
        {answered} of {yesNo.length} answered
        <div className="mt-1 h-1.5 overflow-hidden rounded bg-line"><div className="h-full bg-ink" style={{ width: `${(100 * answered) / Math.max(1, yesNo.length)}%` }} /></div>
      </div>

      <div className="mt-6 space-y-8">
        {sections.map((s) => (
          <section key={s}>
            <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-muted">{s}</h2>
            <div className="space-y-3">
              {info.questions.filter((q) => q.section === s).map((q) => (
                <div key={q.id} className="rounded-lg border border-line bg-surface p-4">
                  <p className="text-sm font-medium">{q.text}</p>
                  {q.guidance && <p className="mt-1 text-xs text-muted">{q.guidance}</p>}
                  {q.type === "choice" ? (
                    <Select className="mt-3 sm:w-80" aria-label={q.text} value={answers[q.id]?.answer ?? ""} onChange={(e) => set(q.id, { answer: e.target.value })}>
                      <option value="">Choose…</option>
                      {(q.options ?? []).map((o) => <option key={o} value={o}>{o}</option>)}
                    </Select>
                  ) : q.type === "yes_no" ? (
                    <div className="mt-3 flex flex-wrap gap-2" role="radiogroup" aria-label={q.text}>
                      {[["yes", "Yes"], ["no", "No"], ["na", "Not applicable"]].map(([v, label]) => (
                        <button key={v} type="button" role="radio" aria-checked={answers[q.id]?.answer === v} onClick={() => set(q.id, { answer: v })}
                          className={cx("h-8 rounded-md border px-3 text-sm", answers[q.id]?.answer === v ? "border-ink bg-ink text-white" : "border-line hover:border-ink/40")}>
                          {label}
                        </button>
                      ))}
                    </div>
                  ) : (
                    <Textarea className="mt-3" aria-label={q.text} value={answers[q.id]?.answer ?? ""} onChange={(e) => set(q.id, { answer: e.target.value })} />
                  )}
                  {(q.type === "yes_no" || q.type === "choice") && (
                    <Input className={cx("mt-2", answers[q.id]?.answer === "na" && q.weight && !answers[q.id]?.comment?.trim() ? "border-warn" : "")} aria-label="Comment"
                      placeholder={answers[q.id]?.answer === "na" && q.weight ? "Why doesn't this apply? (required)" : q.evidence ? "Comment (attach the document below)" : "Comment (optional)"}
                      value={answers[q.id]?.comment ?? ""} onChange={(e) => set(q.id, { comment: e.target.value })} />
                  )}
                </div>
              ))}
            </div>
          </section>
        ))}
        <Documents token={token} kinds={info.doc_kinds} initial={info.documents} />
        <section className="rounded-lg border border-line bg-surface p-4">
          <Field label="Your name and role">{(id) => <Input id={id} placeholder="Ravi Kumar, Head of Security" value={name} onChange={(e) => { dirty.current = true; setName(e.target.value); }} />}</Field>
          <div className="mt-4 space-y-3">
            <FormError error={error} />
            <div className="flex flex-wrap gap-2">
              <Button variant="secondary" busy={busy} onClick={save}>Save progress</Button>
              <Button busy={busy} disabled={answered < yesNo.length || naMissing > 0 || !name.trim()} onClick={submit}>Submit</Button>
            </div>
            {naMissing > 0 && <p className="text-xs text-warn">Add a reason to {naMissing} N/A answer{naMissing > 1 ? "s" : ""} before submitting.</p>}
          </div>
        </section>
      </div>
    </Shell>
  );
}

function Documents({ token, kinds, initial }: { token: string; kinds: Record<string, string>; initial: Info["documents"] }) {
  const [docs, setDocs] = useState(initial);
  const [kind, setKind] = useState("iso27001");
  const [validUntil, setValidUntil] = useState("");
  const file = useRef<HTMLInputElement>(null);
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
      const d = await api<Info["documents"][number]>(`/public/assessments/${token}/documents`, { method: "POST", body: form });
      setDocs([...docs, d]);
      if (file.current) file.current.value = "";
    } catch (e) {
      setError(e instanceof Error ? e.message : "Upload failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="rounded-lg border border-line bg-surface p-4">
      <h2 className="text-sm font-semibold">Supporting documents</h2>
      <p className="mt-1 text-sm text-muted">Certificates, audit reports or your DPA. Files are encrypted and only visible to the requesting company.</p>
      {docs.length > 0 && <ul className="mt-3 space-y-1 text-sm">{docs.map((d, i) => <li key={i} className="flex items-center gap-2"><CheckCircle2 size={14} className="text-pass" aria-hidden />{d.title}: {d.file_name}</li>)}</ul>}
      <div className="mt-3 grid gap-3 sm:grid-cols-3">
        <Field label="Type">{(id) => <Select id={id} value={kind} onChange={(e) => setKind(e.target.value)}>{Object.entries(kinds).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</Select>}</Field>
        <Field label="Valid until (if any)">{(id) => <Input id={id} type="date" value={validUntil} onChange={(e) => setValidUntil(e.target.value)} />}</Field>
        <Field label="File">{(id) => <input id={id} ref={file} type="file" className="pt-1.5 text-sm" />}</Field>
      </div>
      <FormError error={error} />
      <Button className="mt-3" variant="secondary" size="sm" busy={busy} onClick={upload}><FileUp size={14} aria-hidden /> Upload</Button>
    </section>
  );
}

function Shell({ org, children }: { org?: string; children: React.ReactNode }) {
  return (
    <div className="min-h-screen bg-paper">
      <header className="border-b border-line bg-surface">
        <div className="mx-auto flex max-w-3xl items-center justify-between px-4 py-3">
          <p className="font-semibold">{org ?? "Security questionnaire"}</p>
          <p className="flex items-center gap-1 text-xs text-muted"><Lock size={12} aria-hidden /> Secure link · powered by {process.env.NEXT_PUBLIC_APP_NAME ?? "Anupalan"}</p>
        </div>
      </header>
      <main className="mx-auto max-w-3xl px-4 py-8">{children}</main>
    </div>
  );
}
