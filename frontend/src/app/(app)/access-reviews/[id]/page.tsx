"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useMemo, useState } from "react";

import { useSession } from "@/components/session";
import { Badge, Button, Input, LoadError, Loading, Tabs, cx, tbl, useToast } from "@/components/ui";
import { api, useApi } from "@/lib/api";
import { fmtDate, fmtDateTime } from "@/lib/format";
import type { ReviewSummary } from "@/lib/types";

interface Item {
  id: string;
  system: string;
  email: string;
  name: string;
  is_admin: boolean;
  person_status: "active" | "exited" | "unknown";
  reviewer: string | null;
  reviewer_id: string | null;
  decision: "pending" | "keep" | "revoke";
  note: string;
  decided_by: string | null;
  decided_at: string | null;
  removal_verified_at: string | null;
  can_decide: boolean;
}

type View = "mine" | "pending" | "all";

export default function ReviewPage() {
  const { id } = useParams<{ id: string }>();
  const { me, isAdmin } = useSession();
  const toast = useToast();
  const { data, error, loading, reload, setData } = useApi<ReviewSummary & { items: Item[] }>(`/access-reviews/${id}`);
  const [view, setView] = useState<View>("mine");
  const [removing, setRemoving] = useState<string | null>(null);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);

  const items = useMemo(() => {
    const all = data?.items ?? [];
    if (view === "mine") return all.filter((i) => i.reviewer_id === me.user.id);
    if (view === "pending") return all.filter((i) => i.decision === "pending");
    return all;
  }, [data, view, me.user.id]);

  if (loading && !data) return <Loading />;
  if (error || !data) return <LoadError error={error ?? "Could not load"} retry={reload} />;

  async function decide(item: Item, decision: Item["decision"], note = "") {
    try {
      const r = await api<{ decision: string; removal_verified_at: string | null }>(`/access-reviews/${id}/items/${item.id}`, {
        method: "PATCH",
        json: { decision, note },
      });
      setData((d) =>
        d && {
          ...d,
          pending: d.pending + (item.decision === "pending" ? -1 : 0) + (decision === "pending" ? 1 : 0),
          items: d.items.map((i) => (i.id === item.id ? { ...i, decision, note, removal_verified_at: r.removal_verified_at, decided_by: me.user.full_name } : i)),
        },
      );
      setRemoving(null);
      setReason("");
      reload();
      if (decision === "revoke") toast(r.removal_verified_at ? "Already removed in the source system" : "Removal task created");
    } catch (e) {
      toast(e instanceof Error ? e.message : "Failed", "error");
    }
  }

  async function complete() {
    setBusy(true);
    try {
      await api(`/access-reviews/${id}/complete`, { method: "POST" });
      toast("Review completed and filed as evidence for ACC-05");
      reload();
    } catch (e) {
      toast(e instanceof Error ? e.message : "Failed", "error");
    } finally {
      setBusy(false);
    }
  }

  const decided = data.total - data.pending;
  const mineCount = data.items.filter((i) => i.reviewer_id === me.user.id).length;

  return (
    <>
      <nav className="mb-3 text-sm text-muted">
        <Link href="/access-reviews" className="hover:underline">Access reviews</Link> / {data.title}
      </nav>
      <header className="mb-6 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-[22px] font-bold tracking-[-0.01em]">{data.title}</h1>
          <p className="mt-1 text-sm text-muted">
            {data.providers.map((p) => p.name).join(", ")}. {decided} of {data.total} decided, {data.kept} kept, {data.revoked} removed.
            {data.status === "open" ? ` Due ${fmtDate(data.due_date)}.` : ` Completed ${fmtDate(data.completed_at)}.`}
          </p>
        </div>
        <div className="flex gap-2">
          <a href={`/api/access-reviews/${id}/export`} className="inline-flex h-9 items-center rounded-md border border-line bg-surface px-4 text-sm font-medium hover:border-ink/40">Export CSV</a>
          {isAdmin && data.status === "open" && (
            <Button onClick={complete} busy={busy} disabled={data.pending > 0} title={data.pending ? "Every account needs a decision first" : undefined}>
              Complete review
            </Button>
          )}
        </div>
      </header>

      <Tabs<View>
        tabs={[
          { value: "mine", label: `Assigned to me (${mineCount})` },
          { value: "pending", label: `Pending (${data.pending})` },
          { value: "all", label: `All (${data.total})` },
        ]}
        value={view}
        onChange={setView}
      />

      <div className="rounded-lg border border-line bg-surface">
        {items.length ? (
          <div className={tbl.wrap}>
            <table className={tbl.table}>
              <thead>
                <tr>
                  <th className={tbl.th}>Account</th>
                  <th className={tbl.th}>System</th>
                  <th className={tbl.th}>Reviewer</th>
                  <th className={tbl.th}>Decision</th>
                </tr>
              </thead>
              <tbody>
                {items.map((i) => (
                  <tr key={i.id} className={cx(tbl.row, i.person_status === "exited" && i.decision === "pending" && "bg-fail-50/50")}>
                    <td className={tbl.td}>
                      <p className="font-medium">{i.name || i.email}</p>
                      {i.email && i.name && <p className="text-xs text-muted">{i.email}</p>}
                      <div className="mt-1 flex flex-wrap gap-1">
                        {i.is_admin && <Badge tone="warn">Admin</Badge>}
                        {i.person_status === "exited" && <Badge tone="fail">Has left the company</Badge>}
                        {i.person_status === "unknown" && <Badge tone="idle">Not in employee list</Badge>}
                      </div>
                    </td>
                    <td className={`${tbl.td} text-muted`}>{i.system}</td>
                    <td className={`${tbl.td} text-muted`}>{i.reviewer ?? "—"}</td>
                    <td className={`${tbl.td} min-w-[260px]`}>
                      {removing === i.id ? (
                        <form
                          className="flex gap-2"
                          onSubmit={(e) => {
                            e.preventDefault();
                            decide(i, "revoke", reason);
                          }}
                        >
                          <Input autoFocus placeholder="Reason, e.g. left the team" value={reason} onChange={(e) => setReason(e.target.value)} aria-label="Reason for removing access" />
                          <Button size="sm" variant="danger" type="submit" disabled={!reason.trim()}>Remove</Button>
                          <Button size="sm" variant="ghost" type="button" onClick={() => setRemoving(null)}>Cancel</Button>
                        </form>
                      ) : i.decision === "pending" ? (
                        i.can_decide ? (
                          <div className="flex gap-2">
                            <Button size="sm" variant="secondary" onClick={() => decide(i, "keep")}>Keep access</Button>
                            <Button size="sm" variant="danger" onClick={() => { setRemoving(i.id); setReason(i.person_status === "exited" ? "Has left the company" : ""); }}>Remove access</Button>
                          </div>
                        ) : (
                          <span className="text-xs text-muted">Waiting for {i.reviewer ?? "reviewer"}</span>
                        )
                      ) : (
                        <div className="text-sm">
                          <Badge tone={i.decision === "keep" ? "pass" : "fail"}>{i.decision === "keep" ? "Keep" : "Remove"}</Badge>
                          {i.decision === "revoke" && (
                            <span className={cx("ml-2 text-xs", i.removal_verified_at ? "text-pass" : "text-warn")}>
                              {i.removal_verified_at ? `Removed, confirmed ${fmtDateTime(i.removal_verified_at)}` : "Waiting for removal"}
                            </span>
                          )}
                          {i.note && <p className="mt-1 text-xs text-muted">{i.note}</p>}
                          <p className="mt-0.5 text-xs text-muted">by {i.decided_by}</p>
                          {i.can_decide && (
                            <button className="mt-1 text-xs text-ink underline" onClick={() => decide(i, "pending")}>Change</button>
                          )}
                        </div>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="px-4 py-8 text-center text-sm text-muted">
            {view === "mine" ? "Nothing assigned to you in this review." : "Nothing to show."}
          </p>
        )}
      </div>
    </>
  );
}
