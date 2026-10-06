"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { MemberSelect } from "@/components/pickers";
import { useSession } from "@/components/session";
import { Badge, Button, Checkbox, Drawer, Empty, Field, FormError, Input, LoadError, Loading, PageHeader, Select, Textarea, tbl, useToast } from "@/components/ui";
import { api, useApi } from "@/lib/api";
import { fmtDate, humanize, splitList } from "@/lib/format";
import type { Vendor } from "@/lib/types";

const TIER_TONE = { critical: "fail", high: "warn", medium: "prog", low: "idle" } as const;

const EMPTY = {
  name: "", website: "", services: "", tier: "medium", data_shared: "", is_processor: false, dpa_signed: false,
  data_location: "", certifications: "", status: "active", owner_id: "", last_assessed_at: "", next_review_date: "", notes: "",
};

export default function VendorsPage() {
  const { canWrite } = useSession();
  const toast = useToast();
  const router = useRouter();
  const { data, error, loading, reload } = useApi<Vendor[]>("/vendors");
  const [editing, setEditing] = useState<Vendor | "new" | null>(null);
  const [handledEdit, setHandledEdit] = useState(false);
  useEffect(() => {
    if (!data || handledEdit) return;
    setHandledEdit(true);
    const id = new URLSearchParams(window.location.search).get("edit");
    const v = id && data.find((x) => x.id === id);
    if (v) open(v);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data, handledEdit]);
  const [form, setForm] = useState(EMPTY);
  const [formError, setFormError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const today = new Date().toISOString().slice(0, 10);

  function open(v: Vendor | "new") {
    setFormError(null);
    setForm(
      v === "new"
        ? EMPTY
        : {
            ...v,
            owner_id: v.owner?.id ?? "",
            data_shared: v.data_shared.join(", "),
            certifications: v.certifications.join(", "),
            last_assessed_at: v.last_assessed_at ?? "",
            next_review_date: v.next_review_date ?? "",
          },
    );
    setEditing(v);
  }

  async function save() {
    setBusy(true);
    setFormError(null);
    const body = {
      ...form,
      owner_id: form.owner_id || null,
      data_shared: splitList(form.data_shared),
      certifications: splitList(form.certifications),
      last_assessed_at: form.last_assessed_at || null,
      next_review_date: form.next_review_date || null,
    };
    try {
      if (editing === "new") await api("/vendors", { method: "POST", json: body });
      else if (editing) await api(`/vendors/${editing.id}`, { method: "PUT", json: body });
      toast("Vendor saved");
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
    await api(`/vendors/${editing.id}`, { method: "DELETE" });
    toast("Vendor deleted");
    setEditing(null);
    reload();
  }

  if (loading && !data) return <Loading />;
  if (error || !data) return <LoadError error={error ?? "Could not load"} retry={reload} />;

  return (
    <>
      <PageHeader
        title="Vendors"
        description="Vendors that process personal data for you are Data Processors under DPDP. You stay responsible for them, so each needs a signed DPA."
        actions={canWrite && <Button onClick={() => open("new")}>Add vendor</Button>}
      />
      <div className="rounded-lg border border-line bg-surface">
        {data.length ? (
          <div className={tbl.wrap}>
            <table className={tbl.table}>
              <thead>
                <tr>
                  <th className={tbl.th}>Vendor</th>
                  <th className={tbl.th}>Tier</th>
                  <th className={tbl.th}>Personal data</th>
                  <th className={tbl.th}>Data location</th>
                  <th className={tbl.th}>Next review</th>
                </tr>
              </thead>
              <tbody>
                {data.map((v) => (
                  <tr key={v.id} className={`${tbl.row} cursor-pointer ${v.status === "offboarded" ? "opacity-60" : ""}`} onClick={() => router.push(`/vendors/${v.id}`)}>
                    <td className={tbl.td}>
                      <p className="font-medium">{v.name}</p>
                      <p className="max-w-[40ch] truncate text-xs text-muted">{v.services || humanize(v.status)}</p>
                    </td>
                    <td className={tbl.td}><Badge tone={TIER_TONE[v.tier]}>{humanize(v.tier)}</Badge></td>
                    <td className={tbl.td}>
                      {v.is_processor ? (
                        v.dpa_signed ? <Badge tone="pass">Processor, DPA signed</Badge> : <Badge tone="fail">Processor, no DPA</Badge>
                      ) : (
                        <span className="text-muted">No</span>
                      )}
                    </td>
                    <td className={`${tbl.td} text-muted`}>{v.data_location || "—"}</td>
                    <td className={`${tbl.td} whitespace-nowrap ${v.next_review_date && v.next_review_date < today ? "font-medium text-fail" : "text-muted"}`}>
                      {fmtDate(v.next_review_date)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <Empty title="No vendors yet" action={canWrite && <Button onClick={() => open("new")}>Add vendor</Button>}>
            Start with the services that hold customer data: cloud hosting, email, CRM, support desk, payments and analytics.
          </Empty>
        )}
      </div>

      <Drawer
        open={editing !== null}
        onClose={() => setEditing(null)}
        title={editing === "new" ? "Add vendor" : editing ? editing.name : ""}
        footer={
          canWrite && (
            <>
              {editing !== "new" && <Button variant="danger" onClick={remove} className="mr-auto">Delete</Button>}
              <Button variant="ghost" onClick={() => setEditing(null)}>Cancel</Button>
              <Button onClick={save} busy={busy} disabled={!form.name}>Save vendor</Button>
            </>
          )
        }
      >
        <FormError error={formError} />
        <Field label="Name">{(id) => <Input id={id} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />}</Field>
        <Field label="Website">{(id) => <Input id={id} value={form.website} onChange={(e) => setForm({ ...form, website: e.target.value })} placeholder="https://" />}</Field>
        <Field label="Services provided">{(id) => <Textarea id={id} value={form.services} onChange={(e) => setForm({ ...form, services: e.target.value })} />}</Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Risk tier">
            {(id) => (
              <Select id={id} value={form.tier} onChange={(e) => setForm({ ...form, tier: e.target.value })}>
                {["critical", "high", "medium", "low"].map((t) => <option key={t} value={t}>{humanize(t)}</option>)}
              </Select>
            )}
          </Field>
          <Field label="Status">
            {(id) => (
              <Select id={id} value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value })}>
                {["onboarding", "active", "offboarded"].map((t) => <option key={t} value={t}>{humanize(t)}</option>)}
              </Select>
            )}
          </Field>
        </div>
        <Checkbox label="Processes personal data on our behalf (Data Processor)" checked={form.is_processor} onChange={(v) => setForm({ ...form, is_processor: v })} />
        <Checkbox label="Data processing agreement signed" checked={form.dpa_signed} onChange={(v) => setForm({ ...form, dpa_signed: v })} />
        <Field label="Data shared" hint="Comma-separated, e.g. name, email, phone, payment data">{(id) => <Input id={id} value={form.data_shared} onChange={(e) => setForm({ ...form, data_shared: e.target.value })} />}</Field>
        <Field label="Data location" hint="Where the vendor stores your data, e.g. India (Mumbai), USA">{(id) => <Input id={id} value={form.data_location} onChange={(e) => setForm({ ...form, data_location: e.target.value })} />}</Field>
        <Field label="Certifications" hint="Comma-separated, e.g. ISO 27001, SOC 2 Type II">{(id) => <Input id={id} value={form.certifications} onChange={(e) => setForm({ ...form, certifications: e.target.value })} />}</Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Last assessed">{(id) => <Input id={id} type="date" value={form.last_assessed_at} onChange={(e) => setForm({ ...form, last_assessed_at: e.target.value })} />}</Field>
          <Field label="Next review">{(id) => <Input id={id} type="date" value={form.next_review_date} onChange={(e) => setForm({ ...form, next_review_date: e.target.value })} />}</Field>
        </div>
        <Field label="Owner">{(id) => <MemberSelect id={id} value={form.owner_id} onChange={(v) => setForm({ ...form, owner_id: v })} />}</Field>
        <Field label="Notes">{(id) => <Textarea id={id} value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} />}</Field>
      </Drawer>
    </>
  );
}
