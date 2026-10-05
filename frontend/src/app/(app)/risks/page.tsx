"use client";

import { useState } from "react";

import { MemberSelect } from "@/components/pickers";
import { useSession } from "@/components/session";
import { Badge, Button, Drawer, Empty, Field, FormError, Input, LoadError, Loading, PageHeader, Panel, Select, Textarea, cx, tbl, useToast } from "@/components/ui";
import { api, useApi } from "@/lib/api";
import { fmtDate, humanize, splitList } from "@/lib/format";
import type { Risk } from "@/lib/types";

const LEVEL = (score: number) =>
  score >= 15 ? { label: "High", tone: "fail" as const } : score >= 8 ? { label: "Medium", tone: "warn" as const } : { label: "Low", tone: "pass" as const };

const CELL = (score: number) => (score >= 15 ? "bg-fail-50" : score >= 8 ? "bg-warn-50" : "bg-pass-50");

const EMPTY = {
  title: "", description: "", category: "", likelihood: 3, impact: 3, treatment: "mitigate", treatment_plan: "",
  status: "open", owner_id: "", control_codes: "", review_date: "",
};

export default function RisksPage() {
  const { canWrite } = useSession();
  const toast = useToast();
  const { data, error, loading, reload } = useApi<Risk[]>("/risks");
  const [editing, setEditing] = useState<Risk | "new" | null>(null);
  const [form, setForm] = useState(EMPTY);
  const [formError, setFormError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  function open(r: Risk | "new") {
    setFormError(null);
    setForm(
      r === "new"
        ? EMPTY
        : { ...r, owner_id: r.owner?.id ?? "", control_codes: r.control_codes.join(", "), review_date: r.review_date ?? "" },
    );
    setEditing(r);
  }

  async function save() {
    setBusy(true);
    setFormError(null);
    const body = { ...form, owner_id: form.owner_id || null, review_date: form.review_date || null, control_codes: splitList(form.control_codes).map((c) => c.toUpperCase()) };
    try {
      if (editing === "new") await api("/risks", { method: "POST", json: body });
      else if (editing) await api(`/risks/${editing.id}`, { method: "PUT", json: body });
      toast("Risk saved");
      setEditing(null);
      reload();
    } catch (e) {
      setFormError(e instanceof Error ? e.message : "Failed");
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    if (!editing || editing === "new" || !confirm("Delete this risk?")) return;
    await api(`/risks/${editing.id}`, { method: "DELETE" });
    toast("Risk deleted");
    setEditing(null);
    reload();
  }

  if (loading && !data) return <Loading />;
  if (error || !data) return <LoadError error={error ?? "Could not load"} retry={reload} />;
  const active = data.filter((r) => r.status !== "closed");

  return (
    <>
      <PageHeader
        title="Risk register"
        description="Score each risk by likelihood and impact from 1 to 5, decide how to treat it, and link the controls that reduce it."
        actions={canWrite && <Button onClick={() => open("new")}>Add risk</Button>}
      />
      <div className="grid grid-cols-1 gap-6 [&>*]:min-w-0 lg:grid-cols-[280px_minmax(0,1fr)]">
        <Panel title="Open risks by score">
          <div className="flex gap-2">
            <span className="flex items-center text-xs text-muted [writing-mode:vertical-rl] rotate-180">Impact</span>
            <div className="flex-1">
              <div className="grid grid-cols-5 gap-1">
                {[5, 4, 3, 2, 1].flatMap((imp) =>
                  [1, 2, 3, 4, 5].map((lik) => {
                    const n = active.filter((r) => r.impact === imp && r.likelihood === lik).length;
                    return (
                      <div key={`${imp}-${lik}`} className={cx("flex aspect-square items-center justify-center rounded-sm text-xs font-semibold", CELL(imp * lik))} title={`Likelihood ${lik}, impact ${imp}`}>
                        {n || ""}
                      </div>
                    );
                  }),
                )}
              </div>
              <p className="mt-1.5 text-center text-xs text-muted">Likelihood</p>
            </div>
          </div>
        </Panel>

        <div className="rounded-lg border border-line bg-surface">
          {data.length ? (
            <div className={tbl.wrap}>
              <table className={tbl.table}>
                <thead>
                  <tr>
                    <th className={tbl.th}>Risk</th>
                    <th className={tbl.th}>Score</th>
                    <th className={tbl.th}>Treatment</th>
                    <th className={tbl.th}>Owner</th>
                    <th className={tbl.th}>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {data.map((r) => {
                    const lvl = LEVEL(r.score);
                    return (
                      <tr key={r.id} className={`${tbl.row} cursor-pointer`} onClick={() => open(r)}>
                        <td className={tbl.td}>
                          <p className="font-medium">{r.title}</p>
                          {r.category && <p className="text-xs text-muted">{r.category}</p>}
                        </td>
                        <td className={tbl.td}><Badge tone={lvl.tone}>{r.score} {lvl.label}</Badge></td>
                        <td className={`${tbl.td} text-muted`}>{humanize(r.treatment)}</td>
                        <td className={`${tbl.td} text-muted`}>{r.owner?.full_name ?? "—"}</td>
                        <td className={`${tbl.td} text-muted`}>{humanize(r.status)}{r.review_date ? `, review ${fmtDate(r.review_date)}` : ""}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          ) : (
            <Empty title="No risks recorded" action={canWrite && <Button onClick={() => open("new")}>Add risk</Button>}>
              ISO 27001 and SOC 2 both expect a documented risk assessment at least once a year.
            </Empty>
          )}
        </div>
      </div>

      <Drawer
        open={editing !== null}
        onClose={() => setEditing(null)}
        title={editing === "new" ? "Add risk" : "Edit risk"}
        footer={
          canWrite && (
            <>
              {editing !== "new" && <Button variant="danger" onClick={remove} className="mr-auto">Delete</Button>}
              <Button variant="ghost" onClick={() => setEditing(null)}>Cancel</Button>
              <Button onClick={save} busy={busy} disabled={!form.title}>Save risk</Button>
            </>
          )
        }
      >
        <FormError error={formError} />
        <Field label="Risk">{(id) => <Input id={id} value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} placeholder="e.g. Customer data exposed through misconfigured storage" />}</Field>
        <Field label="Description">{(id) => <Textarea id={id} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />}</Field>
        <Field label="Category">{(id) => <Input id={id} value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })} placeholder="e.g. Privacy, Cloud, People, Vendor" />}</Field>
        <div className="grid grid-cols-2 gap-3">
          {(["likelihood", "impact"] as const).map((k) => (
            <Field key={k} label={humanize(k)}>
              {(id) => (
                <Select id={id} value={form[k]} onChange={(e) => setForm({ ...form, [k]: Number(e.target.value) })}>
                  {[1, 2, 3, 4, 5].map((n) => <option key={n} value={n}>{n}</option>)}
                </Select>
              )}
            </Field>
          ))}
        </div>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Treatment">
            {(id) => (
              <Select id={id} value={form.treatment} onChange={(e) => setForm({ ...form, treatment: e.target.value })}>
                {["mitigate", "accept", "transfer", "avoid"].map((t) => <option key={t} value={t}>{humanize(t)}</option>)}
              </Select>
            )}
          </Field>
          <Field label="Status">
            {(id) => (
              <Select id={id} value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value })}>
                {["open", "treated", "closed"].map((t) => <option key={t} value={t}>{humanize(t)}</option>)}
              </Select>
            )}
          </Field>
        </div>
        <Field label="Treatment plan">{(id) => <Textarea id={id} value={form.treatment_plan} onChange={(e) => setForm({ ...form, treatment_plan: e.target.value })} />}</Field>
        <Field label="Linked controls" hint="Comma-separated control codes, e.g. NET-01, CRY-01">{(id) => <Input id={id} value={form.control_codes} onChange={(e) => setForm({ ...form, control_codes: e.target.value })} />}</Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Owner">{(id) => <MemberSelect id={id} value={form.owner_id} onChange={(v) => setForm({ ...form, owner_id: v })} />}</Field>
          <Field label="Review date">{(id) => <Input id={id} type="date" value={form.review_date} onChange={(e) => setForm({ ...form, review_date: e.target.value })} />}</Field>
        </div>
      </Drawer>
    </>
  );
}
