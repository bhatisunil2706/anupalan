"use client";

import { useState } from "react";

import { MemberSelect } from "@/components/pickers";
import { useSession } from "@/components/session";
import { Badge, Button, Checkbox, Drawer, Empty, Field, FormError, Input, LoadError, Loading, PageHeader, Select, Textarea, cx, tbl, useToast } from "@/components/ui";
import { api, useApi } from "@/lib/api";
import { countdown, fmtDate, humanize, localToIso, nowLocal } from "@/lib/format";
import type { RightsRequest } from "@/lib/types";

const TYPES = ["access", "correction", "erasure", "grievance", "nomination", "consent_withdrawal"];
const STATUS_TONE = { new: "ink", verifying: "warn", in_progress: "prog", completed: "pass", rejected: "idle" } as const;

export default function RequestsPage() {
  const { canWrite } = useSession();
  const toast = useToast();
  const { data, error, loading, reload } = useApi<RightsRequest[]>("/dpdp/requests");
  const [creating, setCreating] = useState(false);
  const [selected, setSelected] = useState<RightsRequest | null>(null);
  const [form, setForm] = useState({ request_type: "access", requester_name: "", requester_email: "", details: "", channel: "email", received_at: nowLocal(), assignee_id: "" });
  const [edit, setEdit] = useState({ status: "new", identity_verified: false, assignee_id: "", resolution: "" });
  const [formError, setFormError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function create() {
    setBusy(true);
    setFormError(null);
    try {
      await api("/dpdp/requests", { method: "POST", json: { ...form, received_at: localToIso(form.received_at), assignee_id: form.assignee_id || null } });
      toast("Request logged");
      setCreating(false);
      setForm({ ...form, requester_name: "", requester_email: "", details: "" });
      reload();
    } catch (e) {
      setFormError(e instanceof Error ? e.message : "Failed");
    } finally {
      setBusy(false);
    }
  }

  function openRequest(r: RightsRequest) {
    setFormError(null);
    setEdit({ status: r.status, identity_verified: r.identity_verified, assignee_id: r.assignee?.id ?? "", resolution: r.resolution });
    setSelected(r);
  }

  async function update() {
    if (!selected) return;
    setBusy(true);
    setFormError(null);
    try {
      await api(`/dpdp/requests/${selected.id}`, { method: "PATCH", json: { ...edit, assignee_id: edit.assignee_id || null } });
      toast("Request updated");
      setSelected(null);
      reload();
    } catch (e) {
      setFormError(e instanceof Error ? e.message : "Failed");
    } finally {
      setBusy(false);
    }
  }

  if (loading && !data) return <Loading />;
  if (error || !data) return <LoadError error={error ?? "Could not load"} retry={reload} />;

  return (
    <>
      <PageHeader
        title="Rights requests"
        description="Requests from data principals to access, correct or erase their data, nominate someone, withdraw consent or raise a grievance. The DPDP Rules cap grievance responses at 90 days; your internal target is shown as the due date."
        actions={canWrite && <Button onClick={() => setCreating(true)}>Log request</Button>}
      />
      <div className="rounded-lg border border-line bg-surface">
        {data.length ? (
          <div className={tbl.wrap}>
            <table className={tbl.table}>
              <thead>
                <tr>
                  <th className={tbl.th}>Request</th>
                  <th className={tbl.th}>From</th>
                  <th className={tbl.th}>Received</th>
                  <th className={tbl.th}>Due</th>
                  <th className={tbl.th}>Assignee</th>
                  <th className={tbl.th}>Status</th>
                </tr>
              </thead>
              <tbody>
                {data.map((r) => {
                  const open = !["completed", "rejected"].includes(r.status);
                  const cd = countdown(r.due_at);
                  return (
                    <tr key={r.id} className={`${tbl.row} cursor-pointer`} onClick={() => openRequest(r)}>
                      <td className={tbl.td}>
                        <span className="text-xs font-semibold text-muted">DPR-{r.number}</span>
                        <span className="block font-medium">{humanize(r.request_type)}</span>
                      </td>
                      <td className={tbl.td}>
                        {r.requester_name}
                        <span className="block text-xs text-muted">{r.requester_email}</span>
                      </td>
                      <td className={`${tbl.td} whitespace-nowrap text-muted`}>{fmtDate(r.received_at)}</td>
                      <td className={`${tbl.td} whitespace-nowrap`}>
                        {open ? <span className={cx("font-medium", cd.overdue ? "text-fail" : "text-text")}>{cd.text}</span> : <span className="text-muted">Closed {fmtDate(r.closed_at)}</span>}
                      </td>
                      <td className={`${tbl.td} text-muted`}>{r.assignee?.full_name ?? "—"}</td>
                      <td className={tbl.td}>
                        <Badge tone={STATUS_TONE[r.status]}>{humanize(r.status)}</Badge>
                        {!r.identity_verified && open && <span className="mt-1 block text-xs text-warn">Identity not verified</span>}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <Empty title="No requests yet" action={canWrite && <Button onClick={() => setCreating(true)}>Log request</Button>}>
            Log requests that arrive by email, form or support ticket so each one has an owner and a deadline.
          </Empty>
        )}
      </div>

      <Drawer
        open={creating}
        onClose={() => setCreating(false)}
        title="Log a rights request"
        footer={<><Button variant="ghost" onClick={() => setCreating(false)}>Cancel</Button><Button onClick={create} busy={busy} disabled={!form.requester_name || !form.requester_email}>Log request</Button></>}
      >
        <FormError error={formError} />
        <Field label="Type of request">
          {(id) => (
            <Select id={id} value={form.request_type} onChange={(e) => setForm({ ...form, request_type: e.target.value })}>
              {TYPES.map((t) => <option key={t} value={t}>{humanize(t)}</option>)}
            </Select>
          )}
        </Field>
        <Field label="Requester name">{(id) => <Input id={id} value={form.requester_name} onChange={(e) => setForm({ ...form, requester_name: e.target.value })} />}</Field>
        <Field label="Requester email">{(id) => <Input id={id} type="email" value={form.requester_email} onChange={(e) => setForm({ ...form, requester_email: e.target.value })} />}</Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Received (IST)">{(id) => <Input id={id} type="datetime-local" value={form.received_at} onChange={(e) => setForm({ ...form, received_at: e.target.value })} />}</Field>
          <Field label="Channel">
            {(id) => (
              <Select id={id} value={form.channel} onChange={(e) => setForm({ ...form, channel: e.target.value })}>
                {["email", "web form", "app", "support ticket", "phone", "post"].map((c) => <option key={c}>{c}</option>)}
              </Select>
            )}
          </Field>
        </div>
        <Field label="Details">{(id) => <Textarea id={id} value={form.details} onChange={(e) => setForm({ ...form, details: e.target.value })} />}</Field>
        <Field label="Assign to">{(id) => <MemberSelect id={id} value={form.assignee_id} onChange={(v) => setForm({ ...form, assignee_id: v })} />}</Field>
      </Drawer>

      <Drawer
        open={selected !== null}
        onClose={() => setSelected(null)}
        title={selected ? `DPR-${selected.number}: ${humanize(selected.request_type)}` : ""}
        footer={canWrite && <><Button variant="ghost" onClick={() => setSelected(null)}>Cancel</Button><Button onClick={update} busy={busy}>Save</Button></>}
      >
        {selected && (
          <>
            <FormError error={formError} />
            <dl className="grid grid-cols-2 gap-3 rounded-md bg-paper p-3 text-sm">
              <div><dt className="text-xs text-muted">From</dt><dd>{selected.requester_name}<br />{selected.requester_email}</dd></div>
              <div><dt className="text-xs text-muted">Received</dt><dd>{fmtDate(selected.received_at)} via {selected.channel}</dd></div>
              <div><dt className="text-xs text-muted">Internal due date</dt><dd>{fmtDate(selected.due_at)}</dd></div>
              <div><dt className="text-xs text-muted">Legal limit (90 days)</dt><dd>{fmtDate(selected.legal_due_at)}</dd></div>
            </dl>
            {selected.details && <p className="whitespace-pre-wrap text-sm">{selected.details}</p>}
            <Checkbox label="Identity verified" hint="Confirm the requester is the data principal before releasing or erasing data." checked={edit.identity_verified} onChange={(v) => setEdit({ ...edit, identity_verified: v })} />
            <Field label="Status">
              {(id) => (
                <Select id={id} value={edit.status} onChange={(e) => setEdit({ ...edit, status: e.target.value })} disabled={!canWrite}>
                  {Object.keys(STATUS_TONE).map((s) => <option key={s} value={s}>{humanize(s)}</option>)}
                </Select>
              )}
            </Field>
            <Field label="Assignee">{(id) => <MemberSelect id={id} value={edit.assignee_id} onChange={(v) => setEdit({ ...edit, assignee_id: v })} disabled={!canWrite} />}</Field>
            <Field label="Resolution" hint="What you did and what you told the requester. Include your privacy contact in the reply (DPDP Rules R.9).">
              {(id) => <Textarea id={id} value={edit.resolution} onChange={(e) => setEdit({ ...edit, resolution: e.target.value })} disabled={!canWrite} />}
            </Field>
          </>
        )}
      </Drawer>
    </>
  );
}
