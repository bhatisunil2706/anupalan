"use client";

import { useState } from "react";

import { MemberSelect } from "@/components/pickers";
import { useSession } from "@/components/session";
import { Badge, Button, Checkbox, Drawer, Empty, Field, FormError, Input, LoadError, Loading, PageHeader, Select, Textarea, tbl, useToast } from "@/components/ui";
import { api, useApi } from "@/lib/api";
import { fmtDate, splitList } from "@/lib/format";
import type { DataAsset } from "@/lib/types";

const LEGITIMATE_USES = [
  "Data voluntarily provided for a specified purpose (s.7(a))",
  "State subsidies, benefits, services (s.7(b))",
  "Function of the State (s.7(c))",
  "Legal obligation to disclose to the State (s.7(d))",
  "Court order or judgment (s.7(e))",
  "Medical emergency (s.7(f))",
  "Epidemic or public health threat (s.7(g))",
  "Disaster or breakdown of public order (s.7(h))",
  "Employment purposes (s.7(i))",
];

const EMPTY = {
  name: "", description: "", systems: "", data_principals: "", data_categories: "", purposes: "",
  lawful_ground: "consent", legitimate_use: "", retention_period: "", processors: "", cross_border: false,
  transfer_countries: "", includes_children_data: false, owner_id: "", last_reviewed_at: "",
};

const LIST_FIELDS = ["systems", "data_principals", "data_categories", "processors", "transfer_countries"] as const;

export default function InventoryPage() {
  const { canWrite } = useSession();
  const toast = useToast();
  const { data, error, loading, reload } = useApi<DataAsset[]>("/dpdp/assets");
  const [editing, setEditing] = useState<DataAsset | "new" | null>(null);
  const [form, setForm] = useState(EMPTY);
  const [formError, setFormError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  function open(a: DataAsset | "new") {
    setFormError(null);
    if (a === "new") setForm(EMPTY);
    else {
      setForm({
        name: a.name, description: a.description, purposes: a.purposes, lawful_ground: a.lawful_ground,
        legitimate_use: a.legitimate_use, retention_period: a.retention_period, cross_border: a.cross_border,
        includes_children_data: a.includes_children_data, owner_id: a.owner?.id ?? "", last_reviewed_at: a.last_reviewed_at ?? "",
        systems: a.systems.join(", "), data_principals: a.data_principals.join(", "), data_categories: a.data_categories.join(", "),
        processors: a.processors.join(", "), transfer_countries: a.transfer_countries.join(", "),
      });
    }
    setEditing(a);
  }

  async function save() {
    setBusy(true);
    setFormError(null);
    const lists = Object.fromEntries(LIST_FIELDS.map((k) => [k, splitList(form[k])]));
    const body = { ...form, ...lists, owner_id: form.owner_id || null, last_reviewed_at: form.last_reviewed_at || null };
    try {
      if (editing === "new") await api("/dpdp/assets", { method: "POST", json: body });
      else if (editing) await api(`/dpdp/assets/${editing.id}`, { method: "PUT", json: body });
      toast("Processing activity saved");
      setEditing(null);
      reload();
    } catch (e) {
      setFormError(e instanceof Error ? e.message : "Failed");
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    if (!editing || editing === "new" || !confirm(`Delete ${editing.name}?`)) return;
    await api(`/dpdp/assets/${editing.id}`, { method: "DELETE" });
    setEditing(null);
    reload();
  }

  function exportCsv() {
    if (!data) return;
    const cols = ["name", "data_principals", "data_categories", "purposes", "lawful_ground", "legitimate_use", "systems", "processors", "retention_period", "cross_border", "transfer_countries", "includes_children_data", "last_reviewed_at"] as const;
    const esc = (v: unknown) => `"${String(Array.isArray(v) ? v.join("; ") : v ?? "").replace(/"/g, '""')}"`;
    const csv = [cols.join(","), ...data.map((a) => cols.map((c) => esc(a[c])).join(","))].join("\n");
    const url = URL.createObjectURL(new Blob([csv], { type: "text/csv" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = "dpdp-data-inventory.csv";
    link.click();
    URL.revokeObjectURL(url);
  }

  if (loading && !data) return <Loading />;
  if (error || !data) return <LoadError error={error ?? "Could not load"} retry={reload} />;

  return (
    <>
      <PageHeader
        title="Data inventory"
        description="Every way you process personal data, with its purpose and lawful ground. This is the base for your privacy notice, rights requests and breach response."
        actions={
          <>
            {data.length > 0 && <Button variant="secondary" onClick={exportCsv}>Export CSV</Button>}
            {canWrite && <Button onClick={() => open("new")}>Add processing activity</Button>}
          </>
        }
      />
      <div className="rounded-lg border border-line bg-surface">
        {data.length ? (
          <div className={tbl.wrap}>
            <table className={tbl.table}>
              <thead>
                <tr>
                  <th className={tbl.th}>Activity</th>
                  <th className={tbl.th}>Data principals</th>
                  <th className={tbl.th}>Lawful ground</th>
                  <th className={tbl.th}>Retention</th>
                  <th className={tbl.th}>Flags</th>
                  <th className={tbl.th}>Reviewed</th>
                </tr>
              </thead>
              <tbody>
                {data.map((a) => (
                  <tr key={a.id} className={`${tbl.row} cursor-pointer`} onClick={() => open(a)}>
                    <td className={tbl.td}>
                      <p className="font-medium">{a.name}</p>
                      <p className="max-w-[40ch] truncate text-xs text-muted">{a.data_categories.join(", ")}</p>
                    </td>
                    <td className={`${tbl.td} text-muted`}>{a.data_principals.join(", ") || "—"}</td>
                    <td className={tbl.td}>{a.lawful_ground === "consent" ? "Consent" : "Legitimate use"}</td>
                    <td className={`${tbl.td} text-muted`}>{a.retention_period || "—"}</td>
                    <td className={tbl.td}>
                      <div className="flex flex-wrap gap-1">
                        {a.cross_border && <Badge tone="warn">Abroad: {a.transfer_countries.join(", ") || "yes"}</Badge>}
                        {a.includes_children_data && <Badge tone="fail">Children</Badge>}
                        {a.processors.length > 0 && <Badge tone="ink">{a.processors.length} processors</Badge>}
                      </div>
                    </td>
                    <td className={`${tbl.td} whitespace-nowrap text-muted`}>{fmtDate(a.last_reviewed_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <Empty title="No processing activities yet" action={canWrite && <Button onClick={() => open("new")}>Add processing activity</Button>}>
            Start with customer sign-up, payments, marketing emails, support tickets and employee records.
          </Empty>
        )}
      </div>

      <Drawer
        wide
        open={editing !== null}
        onClose={() => setEditing(null)}
        title={editing === "new" ? "Add processing activity" : editing ? editing.name : ""}
        footer={
          canWrite && (
            <>
              {editing !== "new" && <Button variant="danger" onClick={remove} className="mr-auto">Delete</Button>}
              <Button variant="ghost" onClick={() => setEditing(null)}>Cancel</Button>
              <Button onClick={save} busy={busy} disabled={!form.name}>Save</Button>
            </>
          )
        }
      >
        <FormError error={formError} />
        <Field label="Name">{(id) => <Input id={id} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="e.g. Customer account sign-up" />}</Field>
        <Field label="Purposes" hint="Specific purposes, as listed in your notice.">{(id) => <Textarea id={id} value={form.purposes} onChange={(e) => setForm({ ...form, purposes: e.target.value })} />}</Field>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Data principals" hint="Comma-separated, e.g. customers, employees">{(id) => <Input id={id} value={form.data_principals} onChange={(e) => setForm({ ...form, data_principals: e.target.value })} />}</Field>
          <Field label="Data categories" hint="e.g. name, email, phone, Aadhaar last 4">{(id) => <Input id={id} value={form.data_categories} onChange={(e) => setForm({ ...form, data_categories: e.target.value })} />}</Field>
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Lawful ground">
            {(id) => (
              <Select id={id} value={form.lawful_ground} onChange={(e) => setForm({ ...form, lawful_ground: e.target.value })}>
                <option value="consent">Consent (s.6)</option>
                <option value="legitimate_use">Legitimate use (s.7)</option>
              </Select>
            )}
          </Field>
          {form.lawful_ground === "legitimate_use" && (
            <Field label="Which legitimate use">
              {(id) => (
                <Select id={id} value={form.legitimate_use} onChange={(e) => setForm({ ...form, legitimate_use: e.target.value })}>
                  <option value="">Choose one</option>
                  {LEGITIMATE_USES.map((u) => <option key={u}>{u}</option>)}
                </Select>
              )}
            </Field>
          )}
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Systems" hint="Where the data lives, comma-separated">{(id) => <Input id={id} value={form.systems} onChange={(e) => setForm({ ...form, systems: e.target.value })} />}</Field>
          <Field label="Processors" hint="Vendors that process it for you">{(id) => <Input id={id} value={form.processors} onChange={(e) => setForm({ ...form, processors: e.target.value })} />}</Field>
        </div>
        <Field label="Retention period">{(id) => <Input id={id} value={form.retention_period} onChange={(e) => setForm({ ...form, retention_period: e.target.value })} placeholder="e.g. Account lifetime + 90 days" />}</Field>
        <Checkbox label="Stored or accessed outside India" checked={form.cross_border} onChange={(v) => setForm({ ...form, cross_border: v })} />
        {form.cross_border && <Field label="Countries">{(id) => <Input id={id} value={form.transfer_countries} onChange={(e) => setForm({ ...form, transfer_countries: e.target.value })} />}</Field>}
        <Checkbox label="Includes children's data (under 18)" hint="Needs verifiable parental consent and no tracking or targeted ads." checked={form.includes_children_data} onChange={(v) => setForm({ ...form, includes_children_data: v })} />
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Owner">{(id) => <MemberSelect id={id} value={form.owner_id} onChange={(v) => setForm({ ...form, owner_id: v })} />}</Field>
          <Field label="Last reviewed">{(id) => <Input id={id} type="date" value={form.last_reviewed_at} onChange={(e) => setForm({ ...form, last_reviewed_at: e.target.value })} />}</Field>
        </div>
        <Field label="Notes">{(id) => <Textarea id={id} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />}</Field>
      </Drawer>
    </>
  );
}
