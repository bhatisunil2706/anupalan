"use client";

import { ArrowDown, ArrowLeft, ArrowUp, Download, Plus, Trash2 } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import type { Question, TemplateSummary } from "@/components/questionnaires";
import { useSession } from "@/components/session";
import { Button, Field, FormError, Input, LoadError, Loading, Select, Textarea, useToast } from "@/components/ui";
import { api, download, useApi } from "@/lib/api";

type Editable = Question & { key: string };
let seq = 0;
const withKeys = (qs: Question[]): Editable[] => qs.map((q) => ({ ...q, key: `k${seq++}` }));

export default function QuestionnaireEditor() {
  const { slug } = useParams<{ slug: string }>();
  const router = useRouter();
  const { canWrite } = useSession();
  const toast = useToast();
  const { data, error, loading, reload } = useApi<TemplateSummary & { questions_list: Question[] }>(`/questionnaires/${slug}`);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [items, setItems] = useState<Editable[]>([]);
  const [dirty, setDirty] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (data) {
      setTitle(data.title);
      setDescription(data.description);
      setItems(withKeys(data.questions_list));
      setDirty(false);
    }
  }, [data]);
  useEffect(() => {
    if (!dirty) return;
    const h = (e: BeforeUnloadEvent) => e.preventDefault();
    window.addEventListener("beforeunload", h);
    return () => window.removeEventListener("beforeunload", h);
  }, [dirty]);

  if (loading && !data) return <Loading />;
  if (error || !data) return <LoadError error={error ?? "Could not load"} retry={reload} />;
  const editable = canWrite && data.source === "custom";

  const update = (key: string, patch: Partial<Question>) => {
    setDirty(true);
    setItems((xs) => xs.map((x) => (x.key === key ? { ...x, ...patch } : x)));
  };
  const move = (i: number, d: -1 | 1) => {
    setDirty(true);
    setItems((xs) => {
      const next = [...xs];
      const j = i + d;
      if (j < 0 || j >= next.length) return xs;
      [next[i], next[j]] = [next[j], next[i]];
      return next;
    });
  };
  const add = (section: string) => {
    setDirty(true);
    setItems((xs) => [...xs, { key: `k${seq++}`, id: "", section, text: "", type: "yes_no", weight: 1, good: "yes" }]);
  };

  async function save() {
    setBusy(true);
    setFormError(null);
    try {
      await api(`/questionnaires/${slug}`, {
        method: "PUT",
        json: { title, description, questions: items.map(({ key: _k, ...q }) => q) },
      });
      toast("Questionnaire saved");
      setDirty(false);
      reload();
    } catch (e) {
      setFormError(e instanceof Error ? e.message : "Failed");
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    if (!confirm("Delete this questionnaire? Questionnaires already sent keep their own copy.")) return;
    await api(`/questionnaires/${slug}`, { method: "DELETE" });
    router.push("/vendors/questionnaires?tab=library");
  }

  const sections = Array.from(new Set(items.map((q) => q.section || "General")));
  return (
    <>
      <Link href="/vendors/questionnaires?tab=library" className="mb-3 inline-flex items-center gap-1 text-sm text-muted hover:text-text"><ArrowLeft size={14} /> Questionnaire library</Link>
      <div className="mb-6 flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 flex-1 space-y-2">
          {editable ? (
            <>
              <Input value={title} onChange={(e) => { setTitle(e.target.value); setDirty(true); }} aria-label="Title" className="h-11 max-w-xl text-base font-semibold" />
              <Textarea value={description} onChange={(e) => { setDescription(e.target.value); setDirty(true); }} aria-label="Description" placeholder="Who this questionnaire is for" className="max-w-xl" />
            </>
          ) : (
            <>
              <h1 className="text-[22px] font-bold">{data.title}</h1>
              <p className="max-w-[72ch] text-sm text-muted">{data.description}</p>
              {data.source === "built_in" && <p className="text-sm text-muted">Built-in questionnaires can&apos;t be edited. Duplicate it from the library to customise.</p>}
            </>
          )}
        </div>
        <div className="flex gap-2">
          <Button variant="ghost" onClick={() => download(`/questionnaires/${slug}/export`, `${data.title}.xlsx`).catch((e) => toast(e.message, "error"))}><Download size={14} aria-hidden /> Excel</Button>
          {editable && <Button variant="danger" onClick={remove}>Delete</Button>}
          {editable && <Button busy={busy} disabled={!dirty} onClick={save}>Save</Button>}
        </div>
      </div>
      <FormError error={formError} />
      <p className="mb-4 text-xs text-muted">
        {items.length} questions. Yes/no questions with a weight count towards the score; weight 3 marks a critical question. Vendors can always answer N/A with a reason.
      </p>
      <div className="space-y-8">
        {sections.map((s) => (
          <section key={s}>
            <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">{s}</h2>
            <ol className="space-y-2">
              {items.map((q, i) => (q.section || "General") !== s ? null : (
                <li key={q.key} className="rounded-lg border border-line bg-surface p-3">
                  {editable ? (
                    <div className="space-y-2">
                      <div className="flex gap-2">
                        <Textarea value={q.text} onChange={(e) => update(q.key, { text: e.target.value })} aria-label="Question" placeholder="Question text" className="min-h-[60px] flex-1" />
                        <div className="flex flex-col gap-1">
                          <button type="button" aria-label="Move up" onClick={() => move(i, -1)} className="rounded p-1 text-muted hover:bg-ink-50"><ArrowUp size={14} /></button>
                          <button type="button" aria-label="Move down" onClick={() => move(i, 1)} className="rounded p-1 text-muted hover:bg-ink-50"><ArrowDown size={14} /></button>
                          <button type="button" aria-label="Delete question" onClick={() => { setDirty(true); setItems((xs) => xs.filter((x) => x.key !== q.key)); }} className="rounded p-1 text-muted hover:bg-fail-50 hover:text-fail"><Trash2 size={14} /></button>
                        </div>
                      </div>
                      <div className="grid gap-2 sm:grid-cols-5">
                        <Field label="Section">{(id) => <Input id={id} value={q.section} onChange={(e) => update(q.key, { section: e.target.value })} />}</Field>
                        <Field label="Type">
                          {(id) => (
                            <Select id={id} value={q.type} onChange={(e) => update(q.key, { type: e.target.value as Question["type"] })}>
                              <option value="yes_no">Yes / No</option>
                              <option value="choice">Choice</option>
                              <option value="text">Free text</option>
                            </Select>
                          )}
                        </Field>
                        {q.type === "yes_no" && (
                          <>
                            <Field label="Expected answer">
                              {(id) => (
                                <Select id={id} value={q.good ?? "yes"} onChange={(e) => update(q.key, { good: e.target.value as "yes" | "no" })}>
                                  <option value="yes">Yes</option>
                                  <option value="no">No</option>
                                </Select>
                              )}
                            </Field>
                            <Field label="Weight">
                              {(id) => (
                                <Select id={id} value={q.weight ?? 0} onChange={(e) => update(q.key, { weight: Number(e.target.value) })}>
                                  <option value={0}>0 (not scored)</option>
                                  <option value={1}>1</option>
                                  <option value={2}>2</option>
                                  <option value={3}>3 (critical)</option>
                                </Select>
                              )}
                            </Field>
                            <label className="flex items-end gap-2 pb-2 text-sm">
                              <input type="checkbox" className="h-4 w-4 accent-ink" checked={!!q.evidence} onChange={(e) => update(q.key, { evidence: e.target.checked })} /> Ask for evidence
                            </label>
                          </>
                        )}
                        {q.type === "choice" && (
                          <Field label="Options (one per line)" className="sm:col-span-3">
                            {(id) => <Textarea id={id} value={(q.options ?? []).join("\n")} onChange={(e) => update(q.key, { options: e.target.value.split("\n") })} className="min-h-[60px]" />}
                          </Field>
                        )}
                      </div>
                    </div>
                  ) : (
                    <div className="text-sm">
                      <p>{q.text}</p>
                      <p className="mt-1 text-xs text-muted">
                        {q.type === "yes_no" ? `Yes/No${q.weight ? `, expected ${q.good === "yes" ? "Yes" : "No"}, weight ${q.weight}` : ", not scored"}` : q.type === "choice" ? `Choice: ${(q.options ?? []).join(" · ")}` : "Free text"}
                        {q.refs ? ` · ${q.refs}` : ""}
                      </p>
                    </div>
                  )}
                </li>
              ))}
            </ol>
            {editable && <Button size="sm" variant="ghost" className="mt-2" onClick={() => add(s)}><Plus size={14} aria-hidden /> Add question to {s}</Button>}
          </section>
        ))}
        {editable && (
          <Button variant="secondary" onClick={() => add(`Section ${sections.length + 1}`)}><Plus size={14} aria-hidden /> New section</Button>
        )}
      </div>
    </>
  );
}
