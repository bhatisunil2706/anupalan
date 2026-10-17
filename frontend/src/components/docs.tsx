"use client";

import { ArrowLeft, ArrowRight, BookOpen, Search } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Children, isValidElement, useEffect, useRef, useState, type ReactNode } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { api, useApi } from "@/lib/api";

import { LoadError, Loading, cx } from "./ui";

export interface Card { slug: string; title: string; section: string; summary: string; routes: string[] }
export interface Index { sections: { title: string; articles: Card[] }[] }
interface Article extends Card {
  body_md: string;
  headings: { level: number; text: string; id: string }[];
  prev: Card | null;
  next: Card | null;
}
interface Result extends Card { snippet: string; heading: { id: string; text: string } | null }

/** Must match anchor() in backend/app/services/help.py. */
export function anchor(text: string): string {
  return text.toLowerCase().replace(/[`*_]/g, "").replace(/[^a-z0-9\s-]/g, "").replace(/[\s-]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 80);
}

function textOf(node: ReactNode): string {
  return Children.toArray(node).map((c) => (typeof c === "string" || typeof c === "number" ? String(c) : isValidElement<{ children?: ReactNode }>(c) ? textOf(c.props.children) : "")).join("");
}

export function DocsSearch({ autoFocus }: { autoFocus?: boolean }) {
  const router = useRouter();
  const [q, setQ] = useState("");
  const [results, setResults] = useState<Result[] | null>(null);
  const [active, setActive] = useState(0);
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (q.trim().length < 2) return setResults(null);
    const t = setTimeout(() => {
      api<{ results: Result[] }>(`/help/search?q=${encodeURIComponent(q.trim())}`).then((r) => { setResults(r.results); setActive(0); }).catch(() => setResults([]));
    }, 180);
    return () => clearTimeout(t);
  }, [q]);

  useEffect(() => {
    const close = (e: MouseEvent) => { if (box.current && !box.current.contains(e.target as Node)) setResults(null); };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);

  const href = (r: Result) => `/docs/${r.slug}${r.heading ? `#${r.heading.id}` : ""}`;

  return (
    <div ref={box} className="relative">
      <Search size={15} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted" aria-hidden />
      <input
        type="search"
        value={q}
        autoFocus={autoFocus}
        onChange={(e) => setQ(e.target.value)}
        onKeyDown={(e) => {
          if (!results?.length) return;
          if (e.key === "ArrowDown") { e.preventDefault(); setActive((a) => Math.min(a + 1, results.length - 1)); }
          if (e.key === "ArrowUp") { e.preventDefault(); setActive((a) => Math.max(a - 1, 0)); }
          if (e.key === "Enter") { e.preventDefault(); router.push(href(results[active])); setResults(null); setQ(""); }
          if (e.key === "Escape") setResults(null);
        }}
        placeholder="Search the documentation"
        aria-label="Search the documentation"
        role="combobox"
        aria-expanded={!!results}
        aria-controls="docs-search-results"
        className="h-10 w-full rounded-md border border-line bg-surface pl-9 pr-3 text-sm placeholder:text-muted focus:border-ink focus:outline-none"
      />
      {results && (
        <ul id="docs-search-results" role="listbox" className="absolute z-30 mt-1 max-h-[60vh] w-full overflow-y-auto rounded-md border border-line bg-surface shadow-lg">
          {results.length === 0 ? (
            <li className="px-3 py-3 text-sm text-muted">No articles match “{q}”.</li>
          ) : results.map((r, i) => (
            <li key={r.slug + (r.heading?.id ?? "")} role="option" aria-selected={i === active}>
              <Link
                href={href(r)}
                onClick={() => { setResults(null); setQ(""); }}
                className={cx("block border-b border-line px-3 py-2.5 last:border-0", i === active ? "bg-ink-50" : "hover:bg-ink-50")}
              >
                <p className="text-sm font-medium">{r.title}{r.heading && <span className="font-normal text-muted"> › {r.heading.text}</span>}</p>
                <p className="mt-0.5 line-clamp-2 text-xs text-muted">{r.snippet}</p>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function DocsNav({ index, current }: { index: Index; current?: string }) {
  return (
    <nav aria-label="Documentation" className="space-y-5 text-sm">
      {index.sections.map((s) => (
        <div key={s.title}>
          <p className="mb-1 text-xs font-semibold uppercase tracking-wider text-muted">{s.title}</p>
          <ul>
            {s.articles.map((a) => (
              <li key={a.slug}>
                <Link
                  href={`/docs/${a.slug}`}
                  aria-current={a.slug === current ? "page" : undefined}
                  className={cx("block rounded px-2 py-1", a.slug === current ? "bg-ink-50 font-medium text-ink" : "text-text hover:bg-ink-50")}
                >
                  {a.title}
                </Link>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </nav>
  );
}

function Heading({ level, children }: { level: 2 | 3 | 4; children: ReactNode }) {
  const id = anchor(textOf(children));
  const Tag = `h${level}` as const;
  return (
    <Tag id={id} className="group scroll-mt-20">
      {children}
      <a href={`#${id}`} className="ml-2 text-muted opacity-0 group-hover:opacity-100" aria-label="Link to this section">#</a>
    </Tag>
  );
}

export function DocsMarkdown({ body }: { body: string }) {
  return (
    <div className="prose-policy prose-docs max-w-none">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          h2: ({ children }) => <Heading level={2}>{children}</Heading>,
          h3: ({ children }) => <Heading level={3}>{children}</Heading>,
          h4: ({ children }) => <Heading level={4}>{children}</Heading>,
          a: ({ href = "", children }) =>
            href.startsWith("/") ? <Link href={href}>{children}</Link> : <a href={href} target="_blank" rel="noreferrer noopener">{children}</a>,
          table: ({ children }) => <div className="my-4 overflow-x-auto"><table>{children}</table></div>,
        }}
      >
        {body}
      </ReactMarkdown>
    </div>
  );
}

export function DocsLayout({ slug }: { slug?: string }) {
  const index = useApi<Index>("/help");
  const article = useApi<Article>(slug ? `/help/${slug}` : null);
  const [activeId, setActiveId] = useState("");

  useEffect(() => {
    if (!article.data) return;
    const hash = decodeURIComponent(window.location.hash.slice(1));
    if (hash) setTimeout(() => document.getElementById(hash)?.scrollIntoView(), 50);
    else window.scrollTo({ top: 0 });
    const els = article.data.headings.map((h) => document.getElementById(h.id)).filter(Boolean) as HTMLElement[];
    const obs = new IntersectionObserver((entries) => {
      const visible = entries.filter((e) => e.isIntersecting).sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top);
      if (visible[0]) setActiveId(visible[0].target.id);
    }, { rootMargin: "0px 0px -70% 0px" });
    els.forEach((el) => obs.observe(el));
    return () => obs.disconnect();
  }, [article.data]);

  if (index.loading && !index.data) return <Loading />;
  if (index.error || !index.data) return <LoadError error={index.error ?? "Could not load"} retry={index.reload} />;

  return (
    <div className="grid grid-cols-1 gap-8 [&>*]:min-w-0 lg:grid-cols-[220px_minmax(0,1fr)] xl:grid-cols-[220px_minmax(0,1fr)_200px]">
      <aside className="hidden lg:block">
        <div className="sticky top-6 max-h-[calc(100vh-3rem)] overflow-y-auto pb-6 pr-2">
          <Link href="/docs" className="mb-4 flex items-center gap-2 font-semibold"><BookOpen size={16} aria-hidden /> Documentation</Link>
          <DocsNav index={index.data} current={slug} />
        </div>
      </aside>

      <main className="min-w-0">
        <div className="mb-6"><DocsSearch autoFocus={!slug} /></div>
        {!slug ? (
          <DocsHome index={index.data} />
        ) : article.loading && !article.data ? (
          <Loading />
        ) : article.error || !article.data ? (
          <LoadError error={article.error ?? "Article not found"} />
        ) : (
          <article>
            <p className="text-sm font-medium text-muted">{article.data.section}</p>
            <h1 className="mt-1 text-[28px] font-bold tracking-[-0.015em]">{article.data.title}</h1>
            <p className="mt-2 max-w-[70ch] text-[15px] leading-relaxed text-muted">{article.data.summary}</p>
            <details className="mt-4 rounded-md border border-line bg-surface px-3 py-2 text-sm lg:hidden">
              <summary className="cursor-pointer font-medium">All articles</summary>
              <div className="mt-3"><DocsNav index={index.data} current={slug} /></div>
            </details>
            <div className="mt-6 border-t border-line pt-6">
              <DocsMarkdown body={article.data.body_md} />
            </div>
            {article.data.routes.length > 0 && (
              <p className="mt-8 text-sm">
                Open in the app: {article.data.routes.filter((r) => !r.includes("*") && !r.includes("[")).slice(0, 3).map((r, i) => (
                  <span key={r}>{i > 0 && " · "}<Link href={r} className="font-medium text-ink hover:underline">{r}</Link></span>
                ))}
              </p>
            )}
            <nav aria-label="Previous and next" className="mt-10 grid gap-3 border-t border-line pt-6 sm:grid-cols-2">
              {article.data.prev ? (
                <Link href={`/docs/${article.data.prev.slug}`} className="rounded-lg border border-line bg-surface p-3 hover:border-ink/40">
                  <span className="flex items-center gap-1 text-xs text-muted"><ArrowLeft size={12} aria-hidden /> Previous</span>
                  <span className="mt-0.5 block text-sm font-medium">{article.data.prev.title}</span>
                </Link>
              ) : <span />}
              {article.data.next && (
                <Link href={`/docs/${article.data.next.slug}`} className="rounded-lg border border-line bg-surface p-3 text-right hover:border-ink/40">
                  <span className="flex items-center justify-end gap-1 text-xs text-muted">Next <ArrowRight size={12} aria-hidden /></span>
                  <span className="mt-0.5 block text-sm font-medium">{article.data.next.title}</span>
                </Link>
              )}
            </nav>
          </article>
        )}
      </main>

      {slug && article.data && article.data.headings.length > 0 && (
        <aside className="hidden xl:block">
          <div className="sticky top-6 max-h-[calc(100vh-3rem)] overflow-y-auto text-sm">
            <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted">On this page</p>
            <ul className="space-y-1 border-l border-line">
              {article.data.headings.map((h) => (
                <li key={h.id}>
                  <a
                    href={`#${h.id}`}
                    className={cx("-ml-px block border-l py-0.5 hover:text-text", h.level === 3 ? "pl-6" : "pl-3",
                      activeId === h.id ? "border-ink font-medium text-ink" : "border-transparent text-muted")}
                  >
                    {h.text}
                  </a>
                </li>
              ))}
            </ul>
          </div>
        </aside>
      )}
    </div>
  );
}

function DocsHome({ index }: { index: Index }) {
  return (
    <>
      <h1 className="text-[28px] font-bold tracking-[-0.015em]">Documentation</h1>
      <p className="mt-2 max-w-[70ch] text-[15px] leading-relaxed text-muted">
        Everything about how the platform works: the concepts behind it, every module, administration, security and the APIs.
        New here? Start with <Link href="/docs/introduction" className="font-medium text-ink underline">Introduction</Link> and{" "}
        <Link href="/docs/first-steps" className="font-medium text-ink underline">Your first 30 days</Link>.
      </p>
      <div className="mt-8 space-y-8">
        {index.sections.map((s) => (
          <section key={s.title}>
            <h2 className="mb-3 text-sm font-semibold uppercase tracking-wider text-muted">{s.title}</h2>
            <div className="grid gap-3 sm:grid-cols-2">
              {s.articles.map((a) => (
                <Link key={a.slug} href={`/docs/${a.slug}`} className="rounded-lg border border-line bg-surface p-4 hover:border-ink/40">
                  <p className="font-semibold">{a.title}</p>
                  <p className="mt-1 text-sm leading-relaxed text-muted">{a.summary}</p>
                </Link>
              ))}
            </div>
          </section>
        ))}
      </div>
    </>
  );
}
