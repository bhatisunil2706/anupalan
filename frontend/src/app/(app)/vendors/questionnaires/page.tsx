"use client";

import { ArrowLeft, Copy, Download, FileUp, Plus } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";

import { AssessmentDrawer, AssessmentsTable, STATUS, type Assessment, type AssessmentStatus, type Question, type TemplateSummary } from "@/components/questionnaires";
import { useSession } from "@/components/session";
import { Badge, Button, Drawer, Input, LoadError, Loading, PageHeader, Select, Tabs, useToast } from "@/components/ui";
import { api, download, useApi } from "@/lib/api";

type Tab = "sent" | "library";

export default function QuestionnairesPage() {
  const [tab, setTab] = useState<Tab>("sent");
  useEffect(() => {
    if (new URLSearchParams(window.location.search).get("tab") === "library") setTab("library");
  }, []);
  return (
    <>
      <Link href="/vendors" className="mb-3 inline-flex items-center gap-1 text-sm text-muted hover:text-text"><ArrowLeft size={14} /> Vendors</Link>
      <PageHeader
        title="Vendor questionnaires"
        description="Track every questionnaire you've sent, and see or customise the questions vendors are asked. The standard sets follow the domains of common industry questionnaires and reference ISO 27001 and SOC 2."
      />
      <Tabs tabs={[{ value: "sent", label: "Sent to vendors" }, { value: "library", label: "Questionnaire library" }]} value={tab} onChange={setTab} />
      {tab === "sent" ? <Sent /> : <Library />}
    </>
  );
}

function Sent() {
  const { data, error, loading, reload } = useApi<Assessment[]>("/assessments");
  const [status, setStatus] = useState<"" | AssessmentStatus | "open">("");
  const [q, setQ] = useState("");
  const [viewing, setViewing] = useState<Assessment | null>(null);
  const rows = useMemo(() => (data ?? []).filter((a) =>
    (!status || (status === "open" ? ["sent", "in_progress"].includes(a.status) : a.status === status)) &&
    (!q || `${a.vendor_name} ${a.sent_to_email} ${a.template_title}`.toLowerCase().includes(q.toLowerCase()))), [data, status, q]);

  if (loading && !data) return <Loading />;
  if (error || !data) return <LoadError error={error ?? "Could not load"} retry={reload} />;
  const count = (s: AssessmentStatus) => data.filter((a) => a.status === s).length;
  const tiles: { key: typeof status; label: string; n: number }[] = [
    { key: "open", label: "Waiting for vendor", n: count("sent") + count("in_progress") },
    { key: "submitted", label: "Ready to review", n: count("submitted") },
    { key: "expired", label: "Expired", n: count("expired") },
    { key: "reviewed", label: "Reviewed", n: count("reviewed") },
  ];

  return (
    <>
      <div className="mb-4 grid gap-3 sm:grid-cols-4">
        {tiles.map((t) => (
          <button key={t.key} type="button" onClick={() => setStatus(status === t.key ? "" : t.key)}
            className={`rounded-lg border p-3 text-left ${status === t.key ? "border-ink bg-ink-50/60" : "border-line bg-surface hover:border-ink/40"}`}>
            <p className="text-2xl font-bold">{t.n}</p>
            <p className="text-xs text-muted">{t.label}</p>
          </button>
        ))}
      </div>
      <div className="mb-3 flex flex-wrap gap-2">
        <Input placeholder="Search vendor, email or questionnaire" value={q} onChange={(e) => setQ(e.target.value)} className="w-72" aria-label="Search" />
        <Select value={status} onChange={(e) => setStatus(e.target.value as typeof status)} className="w-48" aria-label="Status">
          <option value="">All statuses</option>
          <option value="open">Waiting for vendor</option>
          {(Object.keys(STATUS) as AssessmentStatus[]).map((s) => <option key={s} value={s}>{STATUS[s].label}</option>)}
        </Select>
      </div>
      <div className="rounded-lg border border-line bg-surface">
        <AssessmentsTable rows={rows} showVendor onChanged={reload} onOpen={setViewing} />
      </div>
      <p className="mt-3 text-xs text-muted">{rows.length} of {data.length} questionnaires. A reminder with a fresh link goes out automatically 3 days before the due date.</p>
      {viewing && <AssessmentDrawer vendorId={viewing.vendor_id} assessmentId={viewing.id} onClose={() => setViewing(null)} onReviewed={() => { setViewing(null); reload(); }} />}
    </>
  );
}

function Library() {
  const router = useRouter();
  const { canWrite } = useSession();
  const toast = useToast();
  const { data, error, loading, reload } = useApi<TemplateSummary[]>("/questionnaires");
  const [preview, setPreview] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  async function duplicate(t: TemplateSummary) {
    setBusy(t.slug);
    try {
      const c = await api<TemplateSummary>("/questionnaires", { method: "POST", json: { title: `${t.title} (our version)`, description: t.description, copy_from: t.slug } });
      router.push(`/vendors/questionnaires/${c.slug}`);
    } catch (e) {
      toast(e instanceof Error ? e.message : "Failed", "error");
      setBusy(null);
    }
  }

  async function createBlank() {
    setBusy("new");
    try {
      const c = await api<TemplateSummary>("/questionnaires", {
        method: "POST",
        json: { title: "New questionnaire", questions: [{ section: "General", text: "Do you have an information security policy approved by management?", type: "yes_no", weight: 2, good: "yes" }] },
      });
      router.push(`/vendors/questionnaires/${c.slug}`);
    } catch (e) {
      toast(e instanceof Error ? e.message : "Failed", "error");
      setBusy(null);
    }
  }

  async function importFile(file: File | undefined) {
    if (!file) return;
    setBusy("import");
    try {
      const fd = new FormData();
      fd.set("file", file);
      const { questions } = await api<{ questions: Question[] }>("/questionnaires/parse", { method: "POST", body: fd });
      const c = await api<TemplateSummary>("/questionnaires", { method: "POST", json: { title: file.name.replace(/\.[^.]+$/, ""), questions } });
      toast(`Imported ${questions.length} questions`);
      router.push(`/vendors/questionnaires/${c.slug}`);
    } catch (e) {
      toast(e instanceof Error ? e.message : "Import failed", "error");
      setBusy(null);
    } finally {
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  if (loading && !data) return <Loading />;
  if (error || !data) return <LoadError error={error ?? "Could not load"} retry={reload} />;
  const groups: { title: string; hint: string; items: TemplateSummary[] }[] = [
    { title: "Core questionnaires", hint: "Send one of these to every vendor, sized to the vendor's risk tier.", items: data.filter((t) => t.kind === "core") },
    { title: "Add-ons", hint: "Send alongside a core questionnaire when the vendor processes personal data, uses AI or handles card data.", items: data.filter((t) => t.kind === "addon") },
    { title: "Your questionnaires", hint: "Copies you've customised, or questionnaires imported from Excel.", items: data.filter((t) => t.source === "custom") },
  ];

  return (
    <>
      {canWrite && (
        <div className="mb-4 flex flex-wrap gap-2">
          <Button variant="secondary" busy={busy === "new"} onClick={createBlank}><Plus size={14} aria-hidden /> New questionnaire</Button>
          <Button variant="secondary" busy={busy === "import"} onClick={() => fileRef.current?.click()}><FileUp size={14} aria-hidden /> Import from Excel or CSV</Button>
          <input ref={fileRef} type="file" accept=".xlsx,.csv" className="hidden" aria-label="Import questionnaire" onChange={(e) => importFile(e.target.files?.[0])} />
          <span className="self-center text-xs text-muted">Columns: Section, Question, Type (Yes/No, Text, Choice), Weight 0-3, Expected answer, Evidence required, Options.</span>
        </div>
      )}
      <div className="space-y-8">
        {groups.filter((g) => g.items.length || g.title === "Your questionnaires").map((g) => (
          <section key={g.title}>
            <h2 className="text-sm font-semibold">{g.title}</h2>
            <p className="mb-3 text-xs text-muted">{g.hint}</p>
            {g.items.length ? (
              <div className="grid gap-3 md:grid-cols-2">
                {g.items.map((t) => (
                  <article key={t.slug} className="flex flex-col rounded-lg border border-line bg-surface p-4">
                    <div className="flex flex-wrap items-center gap-2">
                      <h3 className="font-semibold">{t.title.replace(/^Add-on: /, "")}</h3>
                      {t.recommended_for.map((r) => <Badge key={r} tone="ink">{r} risk</Badge>)}
                    </div>
                    <p className="mt-1 flex-1 text-sm leading-relaxed text-muted">{t.description || "No description"}</p>
                    <p className="mt-2 text-xs text-muted">{t.questions} questions · {t.scored} scored · {t.sections.length} sections</p>
                    <div className="mt-3 flex flex-wrap gap-2">
                      <Button size="sm" variant="secondary" onClick={() => setPreview(t.slug)}>View questions</Button>
                      {t.source === "custom" ? (
                        canWrite && <Button size="sm" variant="secondary" onClick={() => router.push(`/vendors/questionnaires/${t.slug}`)}>Edit</Button>
                      ) : (
                        canWrite && <Button size="sm" variant="ghost" busy={busy === t.slug} onClick={() => duplicate(t)}><Copy size={14} aria-hidden /> Duplicate to customise</Button>
                      )}
                      <Button size="sm" variant="ghost" onClick={() => download(`/questionnaires/${t.slug}/export`, `${t.title}.xlsx`).catch((e) => toast(e.message, "error"))}><Download size={14} aria-hidden /> Excel</Button>
                    </div>
                  </article>
                ))}
              </div>
            ) : (
              <p className="rounded-lg border border-dashed border-line px-4 py-6 text-center text-sm text-muted">None yet. Duplicate a standard questionnaire to add or remove questions, or import your own from Excel.</p>
            )}
          </section>
        ))}
      </div>
      {preview && <PreviewDrawer slug={preview} onClose={() => setPreview(null)} />}
    </>
  );
}

function PreviewDrawer({ slug, onClose }: { slug: string; onClose: () => void }) {
  const { data, error, loading } = useApi<TemplateSummary & { questions_list: Question[] }>(`/questionnaires/${slug}`);
  const [q, setQ] = useState("");
  const list = (data?.questions_list ?? []).filter((x) => !q || `${x.text} ${x.section} ${x.refs ?? ""}`.toLowerCase().includes(q.toLowerCase()));
  const sections = Array.from(new Set(list.map((x) => x.section)));
  return (
    <Drawer open onClose={onClose} title={data?.title ?? "Questionnaire"} wide>
      {loading && !data ? <Loading /> : error || !data ? <LoadError error={error ?? "Could not load"} /> : (
        <>
          <p className="text-sm text-muted">{data.description}</p>
          <Input placeholder="Search questions" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search questions" />
          {sections.map((s) => (
            <div key={s}>
              <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">{s}</p>
              <ol className="space-y-2">
                {list.filter((x) => x.section === s).map((x) => (
                  <li key={x.id} className="rounded-md border border-line p-3 text-sm">
                    <p>{x.text}</p>
                    <p className="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-xs text-muted">
                      <span>{x.type === "yes_no" ? "Yes / No / N/A" : x.type === "choice" ? `Choice: ${(x.options ?? []).join(" · ")}` : "Free text"}</span>
                      {x.type === "yes_no" && !!x.weight && <span>Expected: {x.good === "yes" ? "Yes" : "No"} · weight {x.weight}{x.weight >= 3 ? " (critical)" : ""}</span>}
                      {x.evidence && <span>Evidence requested</span>}
                      {x.refs && <span>{x.refs}</span>}
                    </p>
                  </li>
                ))}
              </ol>
            </div>
          ))}
        </>
      )}
    </Drawer>
  );
}
