"use client";

import { Search, TerminalSquare } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { useSession } from "@/components/session";
import { Badge, Button, Drawer, Field, FormError, Input, LoadError, Loading, PageHeader, Panel, Textarea, cx, useToast } from "@/components/ui";
import { api, useApi } from "@/lib/api";
import { fmtDateTime } from "@/lib/format";
import type { IntegrationItem } from "@/lib/types";

interface TestRow {
  key: string;
  title: string;
  status: string;
  run_at: string;
  control_codes: string[];
  summary: string;
}

interface Coverage {
  total: number;
  counts: { automated: number; assisted: number; manual: number };
  percent_automated: number;
  percent_hands_off: number;
  connected: string[];
  recommendations: { provider: string; name: string; category: string; beta: boolean; controls: string[] }[];
  controls: { id: string; code: string; title: string; level: "automated" | "assisted" | "manual"; could_automate: string[]; workflow: string | null; policy: string | null }[];
}

export default function IntegrationsPage() {
  const { isAdmin } = useSession();
  const toast = useToast();
  const { data, error, loading, reload } = useApi<IntegrationItem[]>("/integrations");
  const tests = useApi<TestRow[]>("/tests");
  const coverage = useApi<Coverage>("/automation/coverage");
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("All");
  const [showManual, setShowManual] = useState(false);
  const [connecting, setConnecting] = useState<IntegrationItem | null>(null);
  const [values, setValues] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  useEffect(() => {
    const q = new URLSearchParams(window.location.search).get("q");
    if (q) setQuery(q);
  }, []);

  function openConnect(item: IntegrationItem) {
    setFormError(null);
    setValues(Object.fromEntries(item.fields.map((f) => [f.name, f.secret ? "" : item.connection?.config[f.name] ?? f.default])));
    setConnecting(item);
  }

  async function connect() {
    if (!connecting) return;
    setBusy("connect");
    setFormError(null);
    const config: Record<string, string> = {};
    const secrets: Record<string, string> = {};
    for (const f of connecting.fields) (f.secret ? secrets : config)[f.name] = values[f.name] ?? "";
    try {
      await api(`/integrations/${connecting.provider}`, { method: "POST", json: { config, secrets } });
      toast(`${connecting.name} connected. Running checks…`);
      const provider = connecting.provider;
      setConnecting(null);
      await sync(provider);
    } catch (e) {
      setFormError(e instanceof Error ? e.message : "Could not connect");
    } finally {
      setBusy(null);
    }
  }

  async function sync(provider: string) {
    setBusy(provider);
    try {
      const r = await api<{ results: { status: string }[] }>(`/integrations/${provider}/sync`, { method: "POST" });
      const failed = r.results.filter((x) => x.status !== "pass").length;
      toast(failed ? `Checks finished: ${failed} need attention` : "All checks passed", failed ? "error" : "ok");
    } catch (e) {
      toast(e instanceof Error ? e.message : "Sync failed", "error");
    } finally {
      setBusy(null);
      reload();
      tests.reload();
      coverage.reload();
    }
  }

  async function disconnect(item: IntegrationItem) {
    if (!confirm(`Disconnect ${item.name}? Stored credentials are deleted. Collected evidence stays until it expires.`)) return;
    await api(`/integrations/${item.provider}`, { method: "DELETE" });
    toast(`${item.name} disconnected`);
    reload();
    coverage.reload();
  }

  if (loading && !data) return <Loading />;
  if (error || !data) return <LoadError error={error ?? "Could not load"} retry={reload} />;

  const connected = data.filter((i) => i.connection);
  const categories = ["All", ...Array.from(new Set(data.filter((i) => !i.connection).map((i) => i.category))).sort()];
  const q = query.trim().toLowerCase();
  const available = data.filter((i) => !i.connection && (category === "All" || i.category === category) &&
    (!q || `${i.name} ${i.category} ${i.description}`.toLowerCase().includes(q)));

  const card = (item: IntegrationItem) => {
    const conn = item.connection;
    const keys = new Set(item.tests.map((t) => t.key));
    const rows = (tests.data ?? []).filter((t) => keys.has(t.key));
    return (
      <section key={item.provider} className="flex flex-col rounded-lg border border-line bg-surface">
        <div className="flex items-start justify-between gap-3 border-b border-line p-4">
          <div>
            <h3 className="flex items-center gap-2 font-semibold">
              {item.name}
              <span className="text-xs font-normal text-muted">{item.category}</span>
              {item.beta && <Badge tone="warn">Beta</Badge>}
            </h3>
            <p className="mt-0.5 text-sm text-muted">{item.description}</p>
          </div>
          <Badge tone={conn?.status === "error" ? "fail" : "pass"}>{conn?.status === "error" ? "Error" : "Connected"}</Badge>
        </div>
        <div className="flex-1 p-4">
          {conn?.last_error && <p className="mb-3 rounded-md bg-fail-50 px-3 py-2 text-sm text-fail">{conn.last_error}</p>}
          {rows.length ? (
            <ul className="space-y-2">
              {rows.map((t) => (
                <li key={t.key} className="flex items-start gap-2 text-sm">
                  <Badge tone={t.status === "pass" ? "pass" : "fail"}>{t.status === "pass" ? "Pass" : t.status === "fail" ? "Fail" : "Error"}</Badge>
                  <span className="min-w-0 flex-1">
                    {t.title}
                    <span className="block text-xs text-muted">{t.summary}</span>
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <ul className="space-y-1 text-sm text-muted">{item.tests.map((t) => <li key={t.key}>{t.title}</li>)}</ul>
          )}
        </div>
        <div className="flex flex-wrap items-center justify-between gap-2 border-t border-line px-4 py-3">
          <span className="text-xs text-muted">{conn?.last_synced_at ? `Last checked ${fmtDateTime(conn.last_synced_at)}` : ""}</span>
          {isAdmin && (
            <div className="ml-auto flex flex-wrap justify-end gap-2">
              <Button size="sm" variant="ghost" onClick={() => disconnect(item)}>Disconnect</Button>
              <Button size="sm" variant="secondary" onClick={() => openConnect(item)}>Update credentials</Button>
              <Button size="sm" busy={busy === item.provider} onClick={() => sync(item.provider)}>Run checks</Button>
            </div>
          )}
        </div>
      </section>
    );
  };

  return (
    <>
      <PageHeader
        title="Integrations"
        description="Connect read-only access to your tools. Checks run on connect, then every 6 hours. Passing checks become evidence; failing checks create tasks and alert the control owner."
      />
      {coverage.data && <CoveragePanel cov={coverage.data} items={data} canConnect={isAdmin} onConnect={openConnect} showManual={showManual} setShowManual={setShowManual} />}

      {connected.length > 0 && (
        <>
          <h2 className="mb-3 mt-8 text-sm font-semibold">Connected ({connected.length})</h2>
          <div className="grid gap-4 md:grid-cols-2">{connected.map(card)}</div>
        </>
      )}

      <div className="mb-3 mt-8 flex flex-wrap items-center gap-2">
        <h2 className="mr-2 text-sm font-semibold">Available ({available.length})</h2>
        <div className="relative">
          <Search size={14} className="pointer-events-none absolute left-2.5 top-2.5 text-muted" aria-hidden />
          <Input aria-label="Search integrations" placeholder="Search" value={query} onChange={(e) => setQuery(e.target.value)} className="w-52 pl-8" />
        </div>
        {categories.map((c) => (
          <button key={c} onClick={() => setCategory(c)} className={cx("h-8 rounded-full border px-3 text-xs", category === c ? "border-ink bg-ink text-white" : "border-line bg-surface hover:border-ink/40")}>
            {c}
          </button>
        ))}
      </div>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {available.map((item) => (
          <section key={item.provider} className="flex flex-col rounded-lg border border-line bg-surface p-4">
            <h3 className="flex items-center gap-2 font-semibold">
              {item.name}
              {item.beta && <Badge tone="warn">Beta</Badge>}
            </h3>
            <p className="text-xs text-muted">{item.category}</p>
            <p className="mt-2 flex-1 text-sm text-muted">{item.description}</p>
            <div className="mt-3 flex items-center justify-between gap-2">
              <span className="text-xs text-muted">
                {item.tests.length ? `${item.tests.length} automated ${item.tests.length === 1 ? "check" : "checks"}` : item.provides_people ? "Employee sync" : "Task sync"}
              </span>
              {isAdmin && <Button size="sm" onClick={() => openConnect(item)}>Connect</Button>}
            </div>
          </section>
        ))}
        {available.length === 0 && <p className="text-sm text-muted">No integrations match.</p>}
      </div>

      <EvidenceApi />

      <Drawer
        open={connecting !== null}
        onClose={() => setConnecting(null)}
        title={connecting ? `Connect ${connecting.name}` : ""}
        footer={<><Button variant="ghost" onClick={() => setConnecting(null)}>Cancel</Button><Button onClick={connect} busy={busy === "connect"}>Connect and run checks</Button></>}
      >
        {connecting && (
          <>
            <p className="rounded-md bg-paper px-3 py-2.5 text-sm text-muted">{connecting.setup_help}</p>
            <FormError error={formError} />
            {connecting.fields.map((f) => (
              <Field key={f.name} label={f.label} hint={f.help || (f.secret ? "Encrypted at rest. Never shown again after saving." : undefined)}>
                {(id) => f.multiline ? (
                  <Textarea
                    id={id}
                    value={values[f.name] ?? ""}
                    onChange={(e) => setValues({ ...values, [f.name]: e.target.value })}
                    className="min-h-[140px] font-mono text-xs"
                    spellCheck={false}
                  />
                ) : (
                  <Input
                    id={id}
                    type={f.secret ? "password" : "text"}
                    autoComplete="off"
                    value={values[f.name] ?? ""}
                    onChange={(e) => setValues({ ...values, [f.name]: e.target.value })}
                  />
                )}
              </Field>
            ))}
          </>
        )}
      </Drawer>
    </>
  );
}

function CoveragePanel({ cov, items, canConnect, onConnect, showManual, setShowManual }: {
  cov: Coverage; items: IntegrationItem[]; canConnect: boolean; onConnect: (i: IntegrationItem) => void;
  showManual: boolean; setShowManual: (v: boolean) => void;
}) {
  const seg = (n: number) => `${(100 * n) / Math.max(1, cov.total)}%`;
  const manual = cov.controls.filter((c) => c.level === "manual");
  return (
    <Panel>
      <div className="grid gap-6 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]">
        <div>
          <p className="text-sm text-muted">Controls that collect their own evidence</p>
          <p className="mt-1 text-3xl font-bold">{cov.percent_automated}%</p>
          <p className="text-sm text-muted">{cov.counts.automated} of {cov.total} fully automated · {cov.percent_hands_off}% automated or one-click</p>
          <div className="mt-3 flex h-2.5 overflow-hidden rounded-full bg-line" role="img" aria-label={`${cov.counts.automated} automated, ${cov.counts.assisted} one-click, ${cov.counts.manual} manual`}>
            <span className="bg-pass" style={{ width: seg(cov.counts.automated) }} />
            <span className="bg-prog" style={{ width: seg(cov.counts.assisted) }} />
          </div>
          <ul className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted">
            <li><span className="mr-1 inline-block h-2 w-2 rounded-full bg-pass" />Automated {cov.counts.automated}</li>
            <li><span className="mr-1 inline-block h-2 w-2 rounded-full bg-prog" />One-click (policy or workflow) {cov.counts.assisted}</li>
            <li><span className="mr-1 inline-block h-2 w-2 rounded-full bg-line" />Manual upload {cov.counts.manual}</li>
          </ul>
          <button className="mt-3 text-sm font-medium text-ink underline" onClick={() => setShowManual(!showManual)}>
            {showManual ? "Hide" : "Show"} the {manual.length} manual controls
          </button>
        </div>
        <div>
          <p className="text-sm font-semibold">Connect next</p>
          <p className="text-xs text-muted">Ranked by how many of your controls each one would automate.</p>
          <ul className="mt-3 divide-y divide-line rounded-md border border-line">
            {cov.recommendations.slice(0, 5).map((r) => {
              const item = items.find((i) => i.provider === r.provider);
              return (
                <li key={r.provider} className="flex items-center gap-3 px-3 py-2.5">
                  <span className="min-w-0 flex-1">
                    <span className="font-medium">{r.name}</span> <span className="text-xs text-muted">{r.category}</span>
                    <span className="block truncate text-xs text-muted" title={r.controls.join(", ")}>Automates {r.controls.length}: {r.controls.join(", ")}</span>
                  </span>
                  <Badge tone="pass">+{r.controls.length}</Badge>
                  {canConnect && item && <Button size="sm" variant="secondary" onClick={() => onConnect(item)}>Connect</Button>}
                </li>
              );
            })}
            {cov.recommendations.length === 0 && <li className="px-3 py-2.5 text-sm text-muted">Every control that an integration can automate is covered.</li>}
          </ul>
        </div>
      </div>
      {showManual && (
        <ul className="mt-5 grid gap-x-6 gap-y-1 border-t border-line pt-4 text-sm sm:grid-cols-2">
          {manual.map((c) => (
            <li key={c.code}>
              <Link href={`/controls/${c.id}`} className="hover:underline"><span className="text-muted">{c.code}</span> {c.title}</Link>
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}

function EvidenceApi() {
  const origin = typeof window !== "undefined" ? window.location.origin : "";
  const snippet = `curl -X POST ${origin}/api/v1/evidence \\
  -H "Authorization: Bearer $PRAMAANLY_API_KEY" -H "Content-Type: application/json" \\
  -d '{"check": "backup-restore", "title": "Nightly restore test", "control_codes": ["OPS-06"],
       "status": "pass", "summary": "Restored 42 GB in 18 min", "source": "Jenkins"}'`;
  return (
    <Panel className="mt-8" title={<span className="flex items-center gap-2"><TerminalSquare size={15} aria-hidden /> Push evidence from any tool</span>}>
      <p className="text-sm text-muted">
        No integration for a tool you use? Send its result from a CI job, backup script or scheduled task. Passing results become evidence on the controls you name; failing ones open a task, just like built-in checks. Create a key with the <code className="font-mono">evidence:write</code> scope in Settings &gt; Security.
      </p>
      <pre className="mt-3 overflow-x-auto rounded-md bg-ink p-3 font-mono text-xs leading-relaxed text-white">{snippet}</pre>
    </Panel>
  );
}
