"use client";

import { ArrowLeft, Check, X } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { Badge, Button, FormError, LoadError, Loading, PageHeader, Panel, cx } from "@/components/ui";
import { api, useApi } from "@/lib/api";

interface Course {
  slug: string;
  title: string;
  summary: string;
  minutes: number;
  body_md: string;
  pass_mark: number;
  quiz: { q: string; options: string[] }[];
}
interface Result {
  score: number;
  passed: boolean;
  pass_mark: number;
  results: { correct: boolean; answer: number }[];
}

export default function CoursePage() {
  const { slug } = useParams<{ slug: string }>();
  const { data, error, loading, reload } = useApi<Course>(`/training/courses/${slug}`);
  const [answers, setAnswers] = useState<(number | null)[]>([]);
  const [result, setResult] = useState<Result | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (loading && !data) return <Loading />;
  if (error || !data) return <LoadError error={error ?? "Could not load"} retry={reload} />;
  const chosen = data.quiz.map((_, i) => answers[i] ?? null);

  async function submit() {
    if (chosen.some((a) => a === null)) return setFormError("Answer every question first");
    setBusy(true);
    setFormError(null);
    try {
      setResult(await api<Result>(`/training/courses/${slug}/submit`, { method: "POST", json: { answers: chosen } }));
      window.scrollTo({ top: document.body.scrollHeight, behavior: "smooth" });
    } catch (e) {
      setFormError(e instanceof Error ? e.message : "Failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="max-w-3xl">
      <Link href="/training" className="mb-3 inline-flex items-center gap-1 text-sm text-muted hover:text-text"><ArrowLeft size={14} /> Training</Link>
      <PageHeader title={data.title} description={`${data.minutes} minutes · pass mark ${data.pass_mark}%`} />
      <Panel>
        <article className="prose-sm max-w-none space-y-3 text-[15px] leading-relaxed [&_h2]:mt-6 [&_h2]:text-lg [&_h2]:font-semibold [&_h3]:font-semibold [&_li]:ml-5 [&_ol]:list-decimal [&_ul]:list-disc">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{data.body_md}</ReactMarkdown>
        </article>
      </Panel>
      <h2 className="mb-3 mt-8 text-lg font-semibold">Check your understanding</h2>
      <div className="space-y-4">
        {data.quiz.map((q, i) => (
          <fieldset key={i} className="rounded-lg border border-line bg-surface p-4">
            <legend className="sr-only">Question {i + 1}</legend>
            <p className="font-medium">{i + 1}. {q.q}</p>
            <div className="mt-3 space-y-2">
              {q.options.map((opt, j) => {
                const r = result?.results[i];
                const isAnswer = r && r.answer === j;
                const pickedWrong = r && chosen[i] === j && !r.correct;
                return (
                  <label key={j} className={cx("flex cursor-pointer items-start gap-2.5 rounded-md border px-3 py-2 text-sm", isAnswer ? "border-pass/50 bg-pass-50" : pickedWrong ? "border-fail/40 bg-fail-50" : "border-line hover:border-ink/30")}>
                    <input type="radio" name={`q${i}`} className="mt-0.5 accent-ink" checked={chosen[i] === j} disabled={!!result} onChange={() => setAnswers(Object.assign([...chosen], { [i]: j }))} />
                    <span className="flex-1">{opt}</span>
                    {isAnswer && <Check size={16} className="text-pass" aria-label="Correct answer" />}
                    {pickedWrong && <X size={16} className="text-fail" aria-label="Your answer" />}
                  </label>
                );
              })}
            </div>
          </fieldset>
        ))}
      </div>
      <div className="mt-5 space-y-3">
        <FormError error={formError} />
        {result ? (
          <div className={cx("rounded-lg border p-4", result.passed ? "border-pass/30 bg-pass-50" : "border-fail/25 bg-fail-50")}>
            <p className="font-semibold">{result.passed ? "Passed" : "Not passed yet"} <Badge tone={result.passed ? "pass" : "fail"}>{result.score}%</Badge></p>
            <p className="mt-1 text-sm">{result.passed ? "Your completion has been recorded." : `You need ${result.pass_mark}% to pass. Review the material and try again.`}</p>
            {!result.passed && <Button className="mt-3" variant="secondary" onClick={() => { setResult(null); setAnswers([]); window.scrollTo({ top: 0 }); }}>Try again</Button>}
          </div>
        ) : (
          <Button busy={busy} onClick={submit}>Submit answers</Button>
        )}
      </div>
    </div>
  );
}
