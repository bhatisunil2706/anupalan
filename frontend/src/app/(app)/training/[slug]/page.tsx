"use client";

import { ArrowLeft, Award, Check, ExternalLink, ShieldAlert, ShieldCheck, Video, X } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useMemo, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { Badge, Button, FormError, LoadError, Loading, PageHeader, Panel, cx } from "@/components/ui";
import { api, useApi } from "@/lib/api";

interface Scenario { from: string; subject: string; body: string; verdict: "phish" | "legit"; explain: string }
interface Course {
  slug: string; title: string; summary: string; minutes: number; body_md: string; pass_mark: number; video_url: string;
  scenarios: Scenario[]; category: string; quiz: { q: string; options: string[] }[];
}
interface Result { score: number; passed: boolean; pass_mark: number; results: { correct: boolean; answer: number; explain: string }[] }

/** Stable per-visit shuffle so the right answer isn't always in the same place. */
function shuffled(n: number, seed: number): number[] {
  const idx = Array.from({ length: n }, (_, i) => i);
  let s = seed;
  for (let i = n - 1; i > 0; i--) {
    s = (s * 9301 + 49297) % 233280;
    const j = Math.floor((s / 233280) * (i + 1));
    [idx[i], idx[j]] = [idx[j], idx[i]];
  }
  return idx;
}

export default function CoursePage() {
  const { slug } = useParams<{ slug: string }>();
  const { data, error, loading, reload } = useApi<Course>(`/training/courses/${slug}`);
  const [answers, setAnswers] = useState<(number | null)[]>([]);
  const [result, setResult] = useState<Result | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [seed, setSeed] = useState(() => Math.floor(Math.random() * 100000));
  const orders = useMemo(() => (data?.quiz ?? []).map((q, i) => shuffled(q.options.length, seed + i * 7)), [data, seed]);

  if (loading && !data) return <Loading />;
  if (error || !data) return <LoadError error={error ?? "Could not load"} retry={reload} />;
  const chosen = data.quiz.map((_, i) => answers[i] ?? null);

  async function submit() {
    if (chosen.some((a) => a === null)) return setFormError("Answer every question first");
    setBusy(true);
    setFormError(null);
    try {
      setResult(await api<Result>(`/training/courses/${slug}/submit`, { method: "POST", json: { answers: chosen } }));
      setTimeout(() => document.getElementById("result")?.scrollIntoView({ behavior: "smooth" }), 50);
    } catch (e) {
      setFormError(e instanceof Error ? e.message : "Failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="max-w-3xl">
      <Link href="/training" className="mb-3 inline-flex items-center gap-1 text-sm text-muted hover:text-text"><ArrowLeft size={14} /> Training</Link>
      <PageHeader title={data.title} description={`${data.minutes} minutes · ${data.quiz.length} questions · pass mark ${data.pass_mark}%`} />
      {data.video_url && (
        <a href={data.video_url} target="_blank" rel="noreferrer noopener" className="mb-4 flex items-center gap-3 rounded-lg border border-line bg-surface p-4 hover:border-ink/40">
          <Video className="text-ink" aria-hidden />
          <span className="flex-1"><span className="block font-medium">Watch the video</span><span className="text-xs text-muted">Opens in a new tab</span></span>
          <ExternalLink size={16} className="text-muted" aria-hidden />
        </a>
      )}
      {data.body_md && (
        <Panel>
          <article className="prose-policy max-w-none text-[15px]">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{data.body_md}</ReactMarkdown>
          </article>
        </Panel>
      )}

      {data.scenarios.length > 0 && <Practice scenarios={data.scenarios} />}

      <h2 className="mb-3 mt-8 text-lg font-semibold">Check your understanding</h2>
      <div className="space-y-4">
        {data.quiz.map((q, i) => (
          <fieldset key={i} className="rounded-lg border border-line bg-surface p-4">
            <legend className="sr-only">Question {i + 1}</legend>
            <p className="font-medium">{i + 1}. {q.q}</p>
            <div className="mt-3 space-y-2">
              {orders[i]?.map((j) => {
                const r = result?.results[i];
                const isAnswer = r && r.answer === j;
                const pickedWrong = r && chosen[i] === j && !r.correct;
                return (
                  <label key={j} className={cx("flex cursor-pointer items-start gap-2.5 rounded-md border px-3 py-2 text-sm", isAnswer ? "border-pass/50 bg-pass-50" : pickedWrong ? "border-fail/40 bg-fail-50" : "border-line hover:border-ink/30")}>
                    <input type="radio" name={`q${i}`} className="mt-0.5 accent-ink" checked={chosen[i] === j} disabled={!!result} onChange={() => setAnswers(Object.assign([...chosen], { [i]: j }))} />
                    <span className="flex-1">{q.options[j]}</span>
                    {isAnswer && <Check size={16} className="text-pass" aria-label="Correct answer" />}
                    {pickedWrong && <X size={16} className="text-fail" aria-label="Your answer" />}
                  </label>
                );
              })}
            </div>
            {result?.results[i]?.explain && <p className="mt-2 text-sm text-muted">{result.results[i].explain}</p>}
          </fieldset>
        ))}
      </div>
      <div id="result" className="mt-5 space-y-3">
        <FormError error={formError} />
        {result ? (
          <div className={cx("rounded-lg border p-4", result.passed ? "border-pass/30 bg-pass-50" : "border-fail/25 bg-fail-50")}>
            <p className="font-semibold">{result.passed ? "Passed" : "Not passed yet"} <Badge tone={result.passed ? "pass" : "fail"}>{result.score}%</Badge></p>
            <p className="mt-1 text-sm">{result.passed ? "Your completion has been recorded." : `You need ${result.pass_mark}% to pass. Read the explanations above and try again.`}</p>
            <div className="mt-3 flex flex-wrap gap-2">
              {result.passed && (
                <Link href={`/training/${slug}/certificate`} className="inline-flex h-9 items-center gap-1.5 rounded-md bg-ink px-4 text-sm font-medium text-white hover:bg-ink-700"><Award size={14} aria-hidden /> View certificate</Link>
              )}
              {!result.passed && <Button variant="secondary" onClick={() => { setResult(null); setAnswers([]); setSeed(seed + 1); window.scrollTo({ top: 0 }); }}>Try again</Button>}
              <Link href="/training" className="inline-flex h-9 items-center rounded-md border border-line px-4 text-sm font-medium hover:border-ink/40">Back to my courses</Link>
            </div>
          </div>
        ) : (
          <Button busy={busy} onClick={submit}>Submit answers</Button>
        )}
      </div>
    </div>
  );
}

function Practice({ scenarios }: { scenarios: Scenario[] }) {
  const [picks, setPicks] = useState<Record<number, "phish" | "legit">>({});
  const score = scenarios.filter((s, i) => picks[i] === s.verdict).length;
  const done = Object.keys(picks).length === scenarios.length;
  return (
    <section className="mt-8">
      <h2 className="text-lg font-semibold">Practice: phishing or legitimate?</h2>
      <p className="mb-3 text-sm text-muted">Look at each message and decide. These don&apos;t count towards your score.</p>
      <div className="space-y-4">
        {scenarios.map((s, i) => {
          const pick = picks[i];
          const right = pick === s.verdict;
          return (
            <div key={i} className="overflow-hidden rounded-lg border border-line bg-surface">
              <div className="border-b border-line bg-paper px-4 py-2 text-xs">
                <p><span className="text-muted">From:</span> <span className="font-medium">{s.from}</span></p>
                {s.subject && <p><span className="text-muted">Subject:</span> {s.subject}</p>}
              </div>
              <p className="px-4 py-3 text-sm leading-relaxed">{s.body}</p>
              <div className="flex flex-wrap items-center gap-2 border-t border-line px-4 py-2.5">
                {!pick ? (
                  <>
                    <Button size="sm" variant="secondary" onClick={() => setPicks({ ...picks, [i]: "phish" })}><ShieldAlert size={14} aria-hidden /> Phishing</Button>
                    <Button size="sm" variant="secondary" onClick={() => setPicks({ ...picks, [i]: "legit" })}><ShieldCheck size={14} aria-hidden /> Legitimate</Button>
                  </>
                ) : (
                  <div className={cx("w-full rounded-md px-3 py-2 text-sm", right ? "bg-pass-50" : "bg-fail-50")}>
                    <p className="font-medium">{right ? "Correct" : "Not quite"}: this is {s.verdict === "phish" ? "phishing" : "legitimate"}.</p>
                    <p className="mt-0.5">{s.explain}</p>
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>
      {done && <p className="mt-3 text-sm font-medium">You spotted {score} of {scenarios.length}.</p>}
    </section>
  );
}
