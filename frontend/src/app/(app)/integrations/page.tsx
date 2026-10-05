"use client";

import { useState } from "react";

import { useSession } from "@/components/session";
import { Badge, Button, Drawer, Field, FormError, Input, LoadError, Loading, PageHeader, Textarea, useToast } from "@/components/ui";
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

const PLANNED = ["Azure", "Google Cloud", "GitLab", "Jira", "Okta", "Jamf / Intune", "Darwinbox", "Slack audit logs"];

export default function IntegrationsPage() {
  const { isAdmin } = useSession();
  const toast = useToast();
  const { data, error, loading, reload } = useApi<IntegrationItem[]>("/integrations");
  const tests = useApi<TestRow[]>("/tests");
  const [connecting, setConnecting] = useState<IntegrationItem | null>(null);
  const [values, setValues] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

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
    }
  }

  async function disconnect(item: IntegrationItem) {
    if (!confirm(`Disconnect ${item.name}? Stored credentials are deleted. Collected evidence stays until it expires.`)) return;
    await api(`/integrations/${item.provider}`, { method: "DELETE" });
    toast(`${item.name} disconnected`);
    reload();
  }

  if (loading && !data) return <Loading />;
  if (error || !data) return <LoadError error={error ?? "Could not load"} retry={reload} />;

  return (
    <>
      <PageHeader
        title="Integrations"
        description="Connect read-only access to your tools. Checks run on connect, then every 6 hours. Passing checks become evidence; failing checks create tasks and alert the control owner."
      />
      <div className="grid gap-4 md:grid-cols-2">
        {data.map((item) => {
          const conn = item.connection;
          const keys = new Set(item.tests.map((t) => t.key));
          const rows = (tests.data ?? []).filter((t) => keys.has(t.key));
          return (
            <section key={item.provider} className="flex flex-col rounded-lg border border-line bg-surface">
              <div className="flex items-start justify-between gap-3 border-b border-line p-4">
                <div>
                  <h2 className="flex items-center gap-2 font-semibold">
                    {item.name}
                    <span className="text-xs font-normal text-muted">{item.category}</span>
                    {item.beta && <Badge tone="warn">Beta</Badge>}
                  </h2>
                  <p className="mt-0.5 text-sm text-muted">{item.description}</p>
                </div>
                {conn ? <Badge tone={conn.status === "error" ? "fail" : "pass"}>{conn.status === "error" ? "Error" : "Connected"}</Badge> : <Badge>Not connected</Badge>}
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
                  <ul className="space-y-1 text-sm text-muted">
                    {item.tests.map((t) => <li key={t.key}>{t.title}</li>)}
                  </ul>
                )}
                {(item.provides_accounts || item.provides_people) && (
                  <p className="mt-3 text-xs text-muted">
                    {item.provides_people
                      ? "Imports your employee list for leaver checks and access reviews."
                      : "Also syncs user accounts for leaver checks and access reviews."}
                  </p>
                )}
              </div>
              <div className="flex flex-wrap items-center justify-between gap-2 border-t border-line px-4 py-3">
                <span className="text-xs text-muted">{conn?.last_synced_at ? `Last checked ${fmtDateTime(conn.last_synced_at)}` : ""}</span>
                {isAdmin && (
                  <div className="ml-auto flex flex-wrap justify-end gap-2">
                    {conn ? (
                      <>
                        <Button size="sm" variant="ghost" onClick={() => disconnect(item)}>Disconnect</Button>
                        <Button size="sm" variant="secondary" onClick={() => openConnect(item)}>Update credentials</Button>
                        <Button size="sm" busy={busy === item.provider} onClick={() => sync(item.provider)}>Run checks</Button>
                      </>
                    ) : (
                      <Button size="sm" onClick={() => openConnect(item)}>Connect</Button>
                    )}
                  </div>
                )}
              </div>
            </section>
          );
        })}
      </div>
      <p className="mt-6 text-sm text-muted">Coming next: {PLANNED.join(", ")}.</p>

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
