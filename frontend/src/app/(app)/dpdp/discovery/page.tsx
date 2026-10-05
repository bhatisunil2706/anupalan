"use client";

import { useState } from "react";

import { useSession } from "@/components/session";
import { Badge, Button, Drawer, Empty, Field, FormError, Input, LoadError, Loading, PageHeader, Panel, Select, Textarea, useToast } from "@/components/ui";
import { api, useApi } from "@/lib/api";
import { fmtDateTime } from "@/lib/format";

interface Source {
  id: string;
  name: string;
  kind: "postgres" | "mysql" | "s3";
  config: Record<string, string>;
  status: "new" | "scanned" | "error";
  last_scan_at: string | null;
  last_error: string;
  stats: { tables?: number; objects?: number; findings?: number };
}

interface Group {
  source_id: string;
  source: string;
  container: string;
  categories: string[];
  sensitive: boolean;
  fields: { field: string; category: string; label: string; matches: number; sampled: number; by_name_only: boolean; examples: string[]; sensitive: boolean }[];
}

const KINDS = {
  postgres: {
    label: "PostgreSQL",
    config: [["host", "Host"], ["port", "Port"], ["database", "Database"], ["username", "Read-only username"], ["sslmode", "SSL mode (require, prefer)"]],
    secrets: [["password", "Password"]],
  },
  mysql: {
    label: "MySQL / MariaDB",
    config: [["host", "Host"], ["port", "Port"], ["database", "Database"], ["username", "Read-only username"]],
    secrets: [["password", "Password"]],
  },
  s3: {
    label: "Amazon S3 bucket",
    config: [["bucket", "Bucket name"], ["prefix", "Folder prefix (optional)"], ["region", "Region"]],
    secrets: [["access_key_id", "Access key ID"], ["secret_access_key", "Secret access key"]],
  },
} as const;

type Kind = keyof typeof KINDS;

export default function DiscoveryPage() {
  const { isAdmin, canWrite } = useSession();
  const toast = useToast();
  const sources = useApi<Source[]>("/discovery/sources");
  const findings = useApi<Group[]>("/discovery/findings");
  const [adding, setAdding] = useState(false);
  const [kind, setKind] = useState<Kind>("postgres");
  const [name, setName] = useState("");
  const [config, setConfig] = useState<Record<string, string>>({ port: "5432", sslmode: "prefer" });
  const [secrets, setSecrets] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [scanning, setScanning] = useState<string | null>(null);
  const [toInventory, setToInventory] = useState<Group | null>(null);
  const [assetName, setAssetName] = useState("");
  const [purposes, setPurposes] = useState("");

  async function addSource() {
    setFormError(null);
    try {
      const s = await api<Source>("/discovery/sources", { method: "POST", json: { name, kind, config, secrets } });
      setAdding(false);
      setSecrets({});
      sources.reload();
      scan(s.id);
    } catch (e) {
      setFormError(e instanceof Error ? e.message : "Failed");
    }
  }

  async function scan(id: string) {
    setScanning(id);
    try {
      const s = await api<Source>(`/discovery/sources/${id}/scan`, { method: "POST" });
      toast(`Scan finished: ${s.stats.findings ?? 0} findings`);
    } catch (e) {
      toast(e instanceof Error ? e.message : "Scan failed", "error");
    } finally {
      setScanning(null);
      sources.reload();
      findings.reload();
    }
  }

  async function remove(s: Source) {
    if (!confirm(`Remove ${s.name}? Its findings are deleted and the stored credentials are erased.`)) return;
    await api(`/discovery/sources/${s.id}`, { method: "DELETE" });
    sources.reload();
    findings.reload();
  }

  async function addToInventory() {
    if (!toInventory) return;
    try {
      await api("/discovery/to-inventory", { method: "POST", json: { source_id: toInventory.source_id, container: toInventory.container, name: assetName, purposes } });
      toast("Added to the data inventory");
      setToInventory(null);
    } catch (e) {
      toast(e instanceof Error ? e.message : "Failed", "error");
    }
  }

  if (sources.loading && !sources.data) return <Loading />;
  if (sources.error || !sources.data) return <LoadError error={sources.error ?? "Could not load"} retry={sources.reload} />;

  const spec = KINDS[kind];

  return (
    <>
      <PageHeader
        title="Data discovery"
        description="Scan databases and storage for personal data: Aadhaar (checksum-validated), PAN, phone numbers, emails, UPI IDs, card numbers, bank and GST details. Rows are sampled read-only, and only masked examples are kept."
        actions={isAdmin && <Button onClick={() => { setName(""); setConfig({ port: "5432", sslmode: "prefer" }); setKind("postgres"); setFormError(null); setAdding(true); }}>Add data source</Button>}
      />

      <Panel title="Data sources" flush className="mb-6">
        {sources.data.length ? (
          <ul>
            {sources.data.map((s) => (
              <li key={s.id} className="flex flex-wrap items-center gap-3 border-b border-line px-4 py-3 last:border-0">
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium">{s.name} <span className="font-normal text-muted">({KINDS[s.kind].label})</span></p>
                  <p className="text-xs text-muted">
                    {s.status === "error" ? <span className="text-fail">{s.last_error}</span>
                      : s.last_scan_at ? `Scanned ${fmtDateTime(s.last_scan_at)}: ${s.stats.tables ?? s.stats.objects ?? 0} ${s.kind === "s3" ? "files" : "tables"}, ${s.stats.findings ?? 0} findings`
                      : "Not scanned yet"}
                  </p>
                </div>
                {isAdmin && (
                  <>
                    <Button size="sm" variant="ghost" onClick={() => remove(s)}>Remove</Button>
                    <Button size="sm" busy={scanning === s.id} onClick={() => scan(s.id)}>Scan now</Button>
                  </>
                )}
              </li>
            ))}
          </ul>
        ) : (
          <Empty title="No data sources yet">
            Add a database or S3 bucket with a read-only login. Start with the production database behind your app.
          </Empty>
        )}
      </Panel>

      {(findings.data?.length ?? 0) > 0 && (
        <section aria-label="Findings" className="space-y-3">
          <h2 className="text-sm font-semibold">Where personal data was found</h2>
          {findings.data!.map((g) => (
            <details key={`${g.source_id}-${g.container}`} className="rounded-lg border border-line bg-surface" open={g.sensitive}>
              <summary className="flex cursor-pointer flex-wrap items-center gap-2 px-4 py-3">
                <span className="font-mono text-sm font-medium">{g.container}</span>
                <span className="text-xs text-muted">{g.source}</span>
                <span className="flex flex-1 flex-wrap justify-end gap-1">
                  {g.categories.map((c) => <Badge key={c} tone={g.fields.some((f) => f.label === c && f.sensitive) ? "fail" : "ink"}>{c}</Badge>)}
                </span>
              </summary>
              <div className="border-t border-line px-4 py-3">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left text-xs text-muted">
                      <th className="pb-2 font-medium">Field</th>
                      <th className="pb-2 font-medium">Type</th>
                      <th className="pb-2 font-medium">Evidence</th>
                      <th className="pb-2 font-medium">Masked examples</th>
                    </tr>
                  </thead>
                  <tbody>
                    {g.fields.map((f) => (
                      <tr key={`${f.field}-${f.category}`} className="border-t border-line/60">
                        <td className="py-2 font-mono text-xs">{f.field || "(file content)"}</td>
                        <td className="py-2">{f.label}</td>
                        <td className="py-2 text-xs text-muted">{f.by_name_only ? "Field name only" : `${f.matches} of ${f.sampled} sampled values`}</td>
                        <td className="py-2 font-mono text-xs text-muted">{f.examples.join(", ") || "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {canWrite && (
                  <div className="mt-3 flex justify-end">
                    <Button size="sm" variant="secondary" onClick={() => { setAssetName(g.container.split(/[./]/).pop() ?? g.container); setPurposes(""); setToInventory(g); }}>
                      Add to data inventory
                    </Button>
                  </div>
                )}
              </div>
            </details>
          ))}
        </section>
      )}

      <Drawer
        open={adding}
        onClose={() => setAdding(false)}
        title="Add data source"
        footer={<><Button variant="ghost" onClick={() => setAdding(false)}>Cancel</Button><Button onClick={addSource} disabled={!name}>Add and scan</Button></>}
      >
        <p className="rounded-md bg-paper px-3 py-2.5 text-sm text-muted">
          Use a read-only login. The scanner reads up to 200 rows per table (or the first 256 KB of up to 200 files) and stores only masked
          examples. Credentials are encrypted at rest.
        </p>
        <FormError error={formError} />
        <Field label="Name">{(id) => <Input id={id} value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Production app database" />}</Field>
        <Field label="Type">
          {(id) => (
            <Select
              id={id}
              value={kind}
              onChange={(e) => {
                const k = e.target.value as Kind;
                setKind(k);
                setConfig(k === "postgres" ? { port: "5432", sslmode: "prefer" } : k === "mysql" ? { port: "3306" } : { region: "ap-south-1" });
              }}
            >
              {Object.entries(KINDS).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
            </Select>
          )}
        </Field>
        {spec.config.map(([k, label]) => (
          <Field key={k} label={label}>{(id) => <Input id={id} value={config[k] ?? ""} onChange={(e) => setConfig({ ...config, [k]: e.target.value })} />}</Field>
        ))}
        {spec.secrets.map(([k, label]) => (
          <Field key={k} label={label}>{(id) => <Input id={id} type="password" autoComplete="off" value={secrets[k] ?? ""} onChange={(e) => setSecrets({ ...secrets, [k]: e.target.value })} />}</Field>
        ))}
      </Drawer>

      <Drawer
        open={toInventory !== null}
        onClose={() => setToInventory(null)}
        title="Add to data inventory"
        footer={<><Button variant="ghost" onClick={() => setToInventory(null)}>Cancel</Button><Button onClick={addToInventory} disabled={!assetName}>Add</Button></>}
      >
        {toInventory && (
          <>
            <p className="text-sm text-muted">
              Creates a processing activity for <span className="font-mono">{toInventory.container}</span> with these data categories:{" "}
              {toInventory.categories.join(", ")}. You can add the lawful ground and retention afterwards.
            </p>
            <Field label="Processing activity name">{(id) => <Input id={id} value={assetName} onChange={(e) => setAssetName(e.target.value)} />}</Field>
            <Field label="Purposes">{(id) => <Textarea id={id} value={purposes} onChange={(e) => setPurposes(e.target.value)} placeholder="Why this data is processed" />}</Field>
          </>
        )}
      </Drawer>
    </>
  );
}
