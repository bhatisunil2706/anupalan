"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { MemberSelect } from "@/components/pickers";
import { useSession } from "@/components/session";
import { Badge, Button, Drawer, Empty, Field, FormError, Input, LoadError, Loading, PageHeader, tbl } from "@/components/ui";
import { api, useApi } from "@/lib/api";
import { fmtDate } from "@/lib/format";
import type { ReviewSummary } from "@/lib/types";

interface ListResponse {
  reviews: ReviewSummary[];
  available_systems: { provider: string; name: string; accounts: number }[];
}

function defaultTitle() {
  const d = new Date();
  return `Access review Q${Math.floor(d.getMonth() / 3) + 1} ${d.getFullYear()}`;
}

export default function AccessReviewsPage() {
  const router = useRouter();
  const { isAdmin } = useSession();
  const { data, error, loading, reload } = useApi<ListResponse>("/access-reviews");
  const [creating, setCreating] = useState(false);
  const [title, setTitle] = useState(defaultTitle());
  const [providers, setProviders] = useState<string[]>([]);
  const [due, setDue] = useState(() => new Date(Date.now() + 14 * 864e5).toISOString().slice(0, 10));
  const [reviewer, setReviewer] = useState("");
  const [formError, setFormError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function start() {
    setBusy(true);
    setFormError(null);
    try {
      const r = await api<{ id: string }>("/access-reviews", {
        method: "POST",
        json: { title, providers, due_date: due || null, default_reviewer_id: reviewer || null },
      });
      router.push(`/access-reviews/${r.id}`);
    } catch (e) {
      setFormError(e instanceof Error ? e.message : "Failed");
      setBusy(false);
    }
  }

  if (loading && !data) return <Loading />;
  if (error || !data) return <LoadError error={error ?? "Could not load"} retry={reload} />;

  return (
    <>
      <PageHeader
        title="Access reviews"
        description="Each account is sent to the person's manager to keep or remove. Removals are verified on the next sync, and the finished review is filed as evidence for ACC-05."
        actions={
          isAdmin && (
            <Button
              onClick={() => {
                setProviders(data.available_systems.map((s) => s.provider));
                setCreating(true);
              }}
              disabled={!data.available_systems.length}
            >
              Start access review
            </Button>
          )
        }
      />
      <div className="rounded-lg border border-line bg-surface">
        {data.reviews.length ? (
          <div className={tbl.wrap}>
            <table className={tbl.table}>
              <thead>
                <tr>
                  <th className={tbl.th}>Review</th>
                  <th className={tbl.th}>Progress</th>
                  <th className={tbl.th}>Outcome</th>
                  <th className={tbl.th}>Due</th>
                  <th className={tbl.th}>Status</th>
                </tr>
              </thead>
              <tbody>
                {data.reviews.map((r) => {
                  const done = r.total - r.pending;
                  return (
                    <tr key={r.id} className={`${tbl.row} cursor-pointer`} onClick={() => router.push(`/access-reviews/${r.id}`)}>
                      <td className={tbl.td}>
                        <Link href={`/access-reviews/${r.id}`} className="font-medium hover:underline" onClick={(e) => e.stopPropagation()}>{r.title}</Link>
                        <p className="text-xs text-muted">{r.providers.map((p) => p.name).join(", ")}</p>
                        {r.my_pending > 0 && <p className="mt-1 text-xs font-medium text-prog">{r.my_pending} waiting for you</p>}
                      </td>
                      <td className={tbl.td}>
                        <div className="h-1.5 w-32 overflow-hidden rounded-full bg-paper" aria-hidden>
                          <div className="h-full bg-ink" style={{ width: `${(100 * done) / Math.max(1, r.total)}%` }} />
                        </div>
                        <p className="mt-1 text-xs text-muted">{done} of {r.total} decided</p>
                      </td>
                      <td className={`${tbl.td} text-muted`}>
                        {r.kept} kept, {r.revoked} removed
                        {r.removals_unverified > 0 && <span className="block text-xs text-warn">{r.removals_unverified} removals not yet confirmed</span>}
                      </td>
                      <td className={`${tbl.td} whitespace-nowrap text-muted`}>{fmtDate(r.due_date)}</td>
                      <td className={tbl.td}>
                        <Badge tone={r.status === "completed" ? "pass" : "prog"}>{r.status === "completed" ? `Completed ${fmtDate(r.completed_at)}` : "Open"}</Badge>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : data.available_systems.length ? (
          <Empty title="No access reviews yet" action={isAdmin && <Button onClick={() => { setProviders(data.available_systems.map((s) => s.provider)); setCreating(true); }}>Start access review</Button>}>
            ISO 27001 and SOC 2 auditors expect access to key systems to be reviewed every quarter.
          </Empty>
        ) : (
          <Empty title="Connect a system first" action={<Link href="/integrations" className="text-sm font-medium text-ink underline">Go to integrations</Link>}>
            Access reviews use the accounts synced from Google Workspace, Microsoft 365, GitHub or AWS.
          </Empty>
        )}
      </div>

      <Drawer
        open={creating}
        onClose={() => setCreating(false)}
        title="Start access review"
        footer={<><Button variant="ghost" onClick={() => setCreating(false)}>Cancel</Button><Button onClick={start} busy={busy} disabled={!providers.length || !title}>Start review</Button></>}
      >
        <FormError error={formError} />
        <Field label="Title">{(id) => <Input id={id} value={title} onChange={(e) => setTitle(e.target.value)} />}</Field>
        <fieldset className="space-y-2">
          <legend className="mb-1.5 text-[13px] font-medium">Systems to review</legend>
          {data.available_systems.map((s) => (
            <label key={s.provider} className="flex items-center gap-2.5 text-sm">
              <input
                type="checkbox"
                className="h-4 w-4 accent-ink"
                checked={providers.includes(s.provider)}
                onChange={(e) => setProviders(e.target.checked ? [...providers, s.provider] : providers.filter((p) => p !== s.provider))}
              />
              {s.name} <span className="text-muted">({s.accounts} active accounts)</span>
            </label>
          ))}
        </fieldset>
        <Field label="Due date">{(id) => <Input id={id} type="date" value={due} onChange={(e) => setDue(e.target.value)} />}</Field>
        <Field label="Reviewer when no manager is known" hint="Accounts go to each person's manager from your employee list. Anything else goes to this person (default: you).">
          {(id) => <MemberSelect id={id} value={reviewer} onChange={setReviewer} emptyLabel="Me" />}
        </Field>
      </Drawer>
    </>
  );
}
