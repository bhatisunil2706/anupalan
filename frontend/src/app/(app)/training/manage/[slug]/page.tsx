"use client";

import { ArrowLeft, Plus, Trash2 } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { PolicyEditor } from "@/components/policy-editor";
import { useSession } from "@/components/session";
import { Button, Checkbox, Field, FormError, Input, LoadError, Loading, Panel, Textarea, useToast } from "@/components/ui";
import { api } from "@/lib/api";

interface QuizItem { q: string; options: string[]; answer: number; explain: string }
interface CustomCourse { slug: string; title: string; summary: string; minutes: number; body_md: string; video_url: string; quiz: QuizItem[]; pass_mark: number; published: boolean }

const BLANK: CustomCourse = {
  slug: "", title: "", summary: "", minutes: 10, body_md: "", video_url: "", pass_mark: 80, published: false,
  quiz: [{ q: "", options: ["", "", ""], answer: 0, explain: "" }],
};

export default function ManageCourse() {
  const { slug } = useParams<{ slug: string }>();
  const isNew = slug === "new";
  const router = useRouter();
  const { isAdmin } = useSession();
  const toast = useToast();
  const [form, setForm] = useState<CustomCourse | null>(isNew ? BLANK : null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (isNew) return;
    api<CustomCourse>(`/training/custom/${slug}`).then(setForm).catch((e) => setLoadError(e instanceof Error ? e.message : "Could not load"));
  }, [slug, isNew]);

  if (!isAdmin) return <p className="text-sm text-muted">Only admins can create courses.</p>;
  if (loadError) return <LoadError error={loadError} />;
  if (!form) return <Loading />;
  const f = form;
  const setQ = (i: number, patch: Partial<QuizItem>) => setForm({ ...f, quiz: f.quiz.map((q, j) => (j === i ? { ...q, ...patch } : q)) });

  async function save(publish?: boolean) {
    setBusy(true);
    setError(null);
    const body = { ...f, published: publish ?? f.published, quiz: f.quiz.filter((q) => q.q.trim()).map((q) => ({ ...q, options: q.options.filter((o) => o.trim()) })) };
    try {
      const out = await api<CustomCourse>(isNew ? "/training/custom" : `/training/custom/${slug}`, { method: isNew ? "POST" : "PUT", json: body });
      toast(body.published ? "Course published" : "Draft saved");
      if (isNew) router.replace(`/training/manage/${out.slug}`);
      else setForm(out);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't save");
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    if (!confirm("Delete this course? Completion records are kept.")) return;
    await api(`/training/custom/${slug}`, { method: "DELETE" });
    router.push("/training?tab=courses");
  }

  return (
    <div className="max-w-4xl">
      <Link href="/training?tab=courses" className="mb-3 inline-flex items-center gap-1 text-sm text-muted hover:text-text"><ArrowLeft size={14} /> Courses and assignments</Link>
      <h1 className="mb-1 text-[22px] font-bold">{isNew ? "Create a course" : f.title || "Course"}</h1>
      <p className="mb-6 text-sm text-muted">Teach your own policies, tools or client requirements. Paste content from Google Docs or Word, import a document, or link a video. Publish when the quiz is ready; then assign it from Courses and assignments.</p>
      <div className="space-y-6">
        <Panel title="Details">
          <div className="space-y-4">
            <Field label="Title">{(id) => <Input id={id} value={f.title} onChange={(e) => setForm({ ...f, title: e.target.value })} placeholder="e.g. Handling client data on the Acme project" />}</Field>
            <Field label="Summary" hint="One or two sentences shown on the course card.">{(id) => <Textarea id={id} value={f.summary} onChange={(e) => setForm({ ...f, summary: e.target.value })} className="min-h-[60px]" />}</Field>
            <div className="grid gap-3 sm:grid-cols-3">
              <Field label="Minutes">{(id) => <Input id={id} type="number" min={1} max={180} value={f.minutes} onChange={(e) => setForm({ ...f, minutes: Number(e.target.value) })} />}</Field>
              <Field label="Pass mark (%)">{(id) => <Input id={id} type="number" min={0} max={100} value={f.pass_mark} onChange={(e) => setForm({ ...f, pass_mark: Number(e.target.value) })} />}</Field>
            </div>
            <Field label="Video link (optional)" hint="YouTube, Vimeo, Google Drive or any https link. Opens in a new tab.">{(id) => <Input id={id} type="url" value={f.video_url} onChange={(e) => setForm({ ...f, video_url: e.target.value })} placeholder="https://" />}</Field>
          </div>
        </Panel>
        <section>
          <h2 className="mb-2 text-sm font-semibold">Course content</h2>
          <PolicyEditor value={f.body_md} onChange={(md) => setForm((cur) => (cur ? { ...cur, body_md: md } : cur))} />
        </section>
        <Panel title={`Quiz (${f.quiz.length} questions)`}>
          <div className="space-y-5">
            {f.quiz.map((q, i) => (
              <div key={i} className="rounded-md border border-line p-3">
                <div className="flex gap-2">
                  <Input value={q.q} onChange={(e) => setQ(i, { q: e.target.value })} placeholder={`Question ${i + 1}`} aria-label={`Question ${i + 1}`} />
                  <button type="button" aria-label="Delete question" onClick={() => setForm({ ...f, quiz: f.quiz.filter((_, j) => j !== i) })} className="rounded p-2 text-muted hover:bg-fail-50 hover:text-fail"><Trash2 size={14} /></button>
                </div>
                <div className="mt-2 space-y-1.5">
                  {q.options.map((o, j) => (
                    <div key={j} className="flex items-center gap-2">
                      <input type="radio" name={`ans${i}`} className="accent-ink" checked={q.answer === j} onChange={() => setQ(i, { answer: j })} aria-label={`Option ${j + 1} is correct`} />
                      <Input value={o} onChange={(e) => setQ(i, { options: q.options.map((x, k) => (k === j ? e.target.value : x)) })} placeholder={`Option ${j + 1}`} aria-label={`Option ${j + 1}`} />
                      {q.options.length > 2 && <button type="button" aria-label="Remove option" onClick={() => setQ(i, { options: q.options.filter((_, k) => k !== j), answer: q.answer >= j && q.answer > 0 ? q.answer - 1 : q.answer })} className="rounded p-1 text-muted hover:text-fail"><Trash2 size={12} /></button>}
                    </div>
                  ))}
                  {q.options.length < 6 && <button type="button" onClick={() => setQ(i, { options: [...q.options, ""] })} className="text-xs font-medium text-ink">+ option</button>}
                </div>
                <Input className="mt-2" value={q.explain} onChange={(e) => setQ(i, { explain: e.target.value })} placeholder="Explanation shown after answering (optional)" aria-label="Explanation" />
                <p className="mt-1 text-xs text-muted">Select the radio button next to the correct answer.</p>
              </div>
            ))}
            <Button size="sm" variant="secondary" onClick={() => setForm({ ...f, quiz: [...f.quiz, { q: "", options: ["", "", ""], answer: 0, explain: "" }] })}><Plus size={14} aria-hidden /> Add question</Button>
          </div>
        </Panel>
        <FormError error={error} />
        <div className="flex flex-wrap items-center gap-2">
          {!isNew && <Button variant="danger" onClick={remove}>Delete</Button>}
          <span className="flex-1" />
          <Checkbox label="Published" checked={f.published} onChange={(v) => setForm({ ...f, published: v })} />
          <Button variant="secondary" busy={busy} onClick={() => save(false)} disabled={f.title.length < 3}>Save draft</Button>
          <Button busy={busy} onClick={() => save(true)} disabled={f.title.length < 3}>Publish</Button>
        </div>
      </div>
    </div>
  );
}
