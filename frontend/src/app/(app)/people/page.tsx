"use client";

import Link from "next/link";
import { useRef, useState } from "react";

import { useSession } from "@/components/session";
import { Badge, Button, Empty, LoadError, Loading, PageHeader, Tabs, cx, tbl, useToast } from "@/components/ui";
import { api, useApi } from "@/lib/api";
import { fmtDate, fmtDateTime } from "@/lib/format";

interface PersonRow {
  id: string;
  email: string;
  full_name: string;
  employee_id: string;
  department: string;
  title: string;
  manager_email: string;
  status: "active" | "exited";
  join_date: string | null;
  exit_date: string | null;
  source: string;
  accounts: { system: string; active: boolean; admin: boolean; mfa: boolean | null }[];
}

interface AccountRow {
  id: string;
  system: string;
  email: string;
  name: string;
  is_admin: boolean;
  is_active: boolean;
  mfa_enabled: boolean | null;
  last_login_at: string | null;
  person_status: "active" | "exited" | "unknown" | "unmatched";
}

interface Leavers {
  findings: { email: string; name: string; system: string; exit_date: string | null; days_since_exit: number | null }[];
  leavers_checked: number;
  accounts_checked: number;
}

type Tab = "people" | "accounts";

export default function PeoplePage() {
  const { isAdmin } = useSession();
  const toast = useToast();
  const [tab, setTab] = useState<Tab>("people");
  const people = useApi<PersonRow[]>("/people");
  const accounts = useApi<AccountRow[]>("/accounts");
  const leavers = useApi<Leavers>("/people/leavers-with-access");
  const fileRef = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<{ created: number; updated: number; exited: number; warnings: string[] } | null>(null);
  const [filter, setFilter] = useState("");

  async function upload(file: File) {
    setBusy(true);
    const fd = new FormData();
    fd.set("file", file);
    try {
      const r = await api<{ created: number; updated: number; exited: number; warnings: string[] }>("/people/upload", { method: "POST", body: fd });
      setResult(r);
      toast(`Imported ${r.created + r.updated} people`);
      people.reload();
      leavers.reload();
    } catch (e) {
      toast(e instanceof Error ? e.message : "Import failed", "error");
    } finally {
      setBusy(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  const q = filter.toLowerCase();

  return (
    <>
      <PageHeader
        title="People & accounts"
        description="Your employee list, matched against the accounts in connected systems. Leavers who still have access are flagged and turned into tasks automatically."
        actions={
          isAdmin && (
            <>
              <input ref={fileRef} type="file" accept=".csv,text/csv" className="hidden" onChange={(e) => e.target.files?.[0] && upload(e.target.files[0])} />
              <Button variant="secondary" busy={busy} onClick={() => fileRef.current?.click()}>Upload employee CSV</Button>
              <Link href="/integrations" className="inline-flex h-9 items-center rounded-md bg-ink px-4 text-sm font-medium text-white hover:bg-ink-700">Connect HR system</Link>
            </>
          )
        }
      />

      {result && (
        <div className="mb-4 rounded-md border border-line bg-surface px-4 py-3 text-sm">
          Imported {result.created + result.updated} people: {result.created} new, {result.updated} updated.{" "}
          {result.exited === 1 ? "1 person has left the company." : `${result.exited} people have left the company.`}
          {result.warnings.length > 0 && (
            <details className="mt-1 text-muted">
              <summary className="cursor-pointer">{result.warnings.length} rows need attention</summary>
              <ul className="mt-1 list-disc pl-5">{result.warnings.map((w) => <li key={w}>{w}</li>)}</ul>
            </details>
          )}
        </div>
      )}

      {leavers.data && leavers.data.findings.length > 0 && (
        <section className="mb-6 rounded-lg border border-fail/30 bg-fail-50 p-4" aria-label="Leavers with access">
          <h2 className="text-sm font-semibold text-fail">
            {leavers.data.findings.length === 1
              ? "1 account still belongs to someone who has left"
              : `${leavers.data.findings.length} accounts still belong to people who have left`}
          </h2>
          <p className="mt-0.5 text-sm text-fail/80">Remove these within 24 hours of exit (control ACC-02). A task has been created.</p>
          <ul className="mt-3 space-y-1 text-sm">
            {leavers.data.findings.map((f) => (
              <li key={`${f.email}-${f.system}`}>
                <span className="font-medium">{f.name || f.email}</span> on {f.system}
                {f.days_since_exit !== null && <span className="text-fail/80">, left {f.days_since_exit} days ago</span>}
              </li>
            ))}
          </ul>
        </section>
      )}

      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <Tabs<Tab>
          tabs={[
            { value: "people", label: `Employees${people.data ? ` (${people.data.length})` : ""}` },
            { value: "accounts", label: `Accounts${accounts.data ? ` (${accounts.data.length})` : ""}` },
          ]}
          value={tab}
          onChange={setTab}
        />
        <input
          placeholder="Search name or email"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          aria-label="Search people"
          className="h-9 w-60 rounded-md border border-line bg-surface px-3 text-sm"
        />
      </div>

      {tab === "people" &&
        (people.loading && !people.data ? <Loading /> : people.error || !people.data ? <LoadError error={people.error ?? "Could not load"} retry={people.reload} /> : (
          <div className="rounded-lg border border-line bg-surface">
            {people.data.length ? (
              <div className={tbl.wrap}>
                <table className={tbl.table}>
                  <thead>
                    <tr>
                      <th className={tbl.th}>Person</th>
                      <th className={tbl.th}>Role</th>
                      <th className={tbl.th}>Manager</th>
                      <th className={tbl.th}>Status</th>
                      <th className={tbl.th}>Accounts</th>
                    </tr>
                  </thead>
                  <tbody>
                    {people.data.filter((p) => !q || `${p.full_name} ${p.email}`.toLowerCase().includes(q)).map((p) => {
                      const live = p.accounts.filter((a) => a.active);
                      return (
                        <tr key={p.id} className={cx(tbl.row, p.status === "exited" && live.length > 0 && "bg-fail-50/50")}>
                          <td className={tbl.td}>
                            <p className="font-medium">{p.full_name || p.email}</p>
                            <p className="text-xs text-muted">{p.email}</p>
                          </td>
                          <td className={`${tbl.td} text-muted`}>{[p.title, p.department].filter(Boolean).join(", ") || "—"}</td>
                          <td className={`${tbl.td} text-muted`}>{p.manager_email || "—"}</td>
                          <td className={tbl.td}>
                            {p.status === "exited" ? <Badge tone="idle">Left {fmtDate(p.exit_date)}</Badge> : <Badge tone="pass">Active</Badge>}
                          </td>
                          <td className={tbl.td}>
                            <div className="flex flex-wrap gap-1">
                              {p.accounts.map((a) => (
                                <Badge key={a.system} tone={!a.active ? "idle" : p.status === "exited" ? "fail" : a.mfa === false ? "warn" : "ink"}>
                                  {a.system}{a.admin ? " (admin)" : ""}{!a.active ? " (disabled)" : a.mfa === false ? ", no MFA" : ""}
                                </Badge>
                              ))}
                              {!p.accounts.length && <span className="text-xs text-muted">None found</span>}
                            </div>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            ) : (
              <Empty title="No employees yet">
                Upload a CSV export from Keka, Darwinbox, greytHR, Zoho People or a spreadsheet. It needs a work email column;
                name, manager email, status and exit date are used if present.
              </Empty>
            )}
          </div>
        ))}

      {tab === "accounts" &&
        (accounts.loading && !accounts.data ? <Loading /> : accounts.error || !accounts.data ? <LoadError error={accounts.error ?? "Could not load"} retry={accounts.reload} /> : (
          <div className="rounded-lg border border-line bg-surface">
            {accounts.data.length ? (
              <div className={tbl.wrap}>
                <table className={tbl.table}>
                  <thead>
                    <tr>
                      <th className={tbl.th}>Account</th>
                      <th className={tbl.th}>System</th>
                      <th className={tbl.th}>Access</th>
                      <th className={tbl.th}>Last sign-in</th>
                      <th className={tbl.th}>Employee</th>
                    </tr>
                  </thead>
                  <tbody>
                    {accounts.data.filter((a) => !q || `${a.name} ${a.email}`.toLowerCase().includes(q)).map((a) => (
                      <tr key={a.id} className={cx(tbl.row, a.is_active && a.person_status === "exited" && "bg-fail-50/50")}>
                        <td className={tbl.td}>
                          <p className="font-medium">{a.name || a.email}</p>
                          {a.email && a.name && <p className="text-xs text-muted">{a.email}</p>}
                        </td>
                        <td className={`${tbl.td} text-muted`}>{a.system}</td>
                        <td className={tbl.td}>
                          <div className="flex flex-wrap gap-1">
                            {!a.is_active && <Badge tone="idle">Disabled</Badge>}
                            {a.is_admin && <Badge tone="warn">Admin</Badge>}
                            {a.mfa_enabled === false && <Badge tone="fail">No MFA</Badge>}
                            {a.mfa_enabled === true && <Badge tone="pass">MFA</Badge>}
                          </div>
                        </td>
                        <td className={`${tbl.td} whitespace-nowrap text-muted`}>{fmtDateTime(a.last_login_at)}</td>
                        <td className={tbl.td}>
                          {a.person_status === "exited" ? <Badge tone="fail">Has left</Badge>
                            : a.person_status === "active" ? <Badge tone="pass">Employee</Badge>
                            : <span className="text-xs text-muted">{a.person_status === "unmatched" ? "No email to match" : "Not in employee list"}</span>}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <Empty title="No accounts synced yet" action={<Link href="/integrations" className="text-sm font-medium text-ink underline">Connect Google Workspace or Microsoft 365</Link>}>
                Identity integrations bring in every user account so leavers and missing MFA are caught automatically.
              </Empty>
            )}
          </div>
        ))}
    </>
  );
}
