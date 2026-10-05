"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { MemberSelect } from "@/components/pickers";
import { useSession } from "@/components/session";
import { Badge, Button, Checkbox, Drawer, Empty, Field, FormError, Input, LoadError, Loading, PageHeader, Select, Textarea, tbl } from "@/components/ui";
import { api, useApi } from "@/lib/api";
import { SEVERITY } from "@/lib/constants";
import { fmtDateTime, humanize, localToIso, nowLocal } from "@/lib/format";
import type { Incident } from "@/lib/types";

export default function IncidentsPage() {
  const router = useRouter();
  const { canWrite } = useSession();
  const { data, error, loading, reload } = useApi<Incident[]>("/incidents");
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState({
    title: "", description: "", severity: "sev3", category: "", detected_at: nowLocal(),
    certin_reportable: false, personal_data_breach: false, lead_id: "",
  });
  const [formError, setFormError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function create() {
    setBusy(true);
    setFormError(null);
    try {
      const i = await api<Incident>("/incidents", {
        method: "POST",
        json: { ...form, detected_at: localToIso(form.detected_at), lead_id: form.lead_id || null },
      });
      router.push(`/incidents/${i.id}`);
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
        title="Incidents"
        description="Record security incidents and personal data breaches. Reporting clocks start from the time the incident was noticed."
        actions={canWrite && <Button onClick={() => setCreating(true)}>Report incident</Button>}
      />
      <div className="rounded-lg border border-line bg-surface">
        {data.length ? (
          <div className={tbl.wrap}>
            <table className={tbl.table}>
              <thead>
                <tr>
                  <th className={tbl.th}>Incident</th>
                  <th className={tbl.th}>Severity</th>
                  <th className={tbl.th}>Noticed</th>
                  <th className={tbl.th}>Reporting</th>
                  <th className={tbl.th}>Status</th>
                </tr>
              </thead>
              <tbody>
                {data.map((i) => (
                  <tr key={i.id} className={tbl.row}>
                    <td className={tbl.td}>
                      <Link href={`/incidents/${i.id}`} className="hover:underline">
                        <span className="text-xs font-semibold text-muted">INC-{i.number}</span>
                        <span className="block font-medium">{i.title}</span>
                      </Link>
                    </td>
                    <td className={tbl.td}><Badge tone={SEVERITY[i.severity].tone}>{SEVERITY[i.severity].label}</Badge></td>
                    <td className={`${tbl.td} whitespace-nowrap text-muted`}>{fmtDateTime(i.detected_at)}</td>
                    <td className={tbl.td}>
                      <div className="flex flex-wrap gap-1">
                        {i.certin_reportable && <Badge tone={i.certin_reported_at ? "pass" : "fail"}>CERT-In {i.certin_reported_at ? "reported" : "pending"}</Badge>}
                        {i.personal_data_breach && <Badge tone={i.dpb_detailed_reported_at ? "pass" : "fail"}>DPDP {i.dpb_detailed_reported_at ? "reported" : "pending"}</Badge>}
                        {!i.certin_reportable && !i.personal_data_breach && <span className="text-muted">None required</span>}
                      </div>
                    </td>
                    <td className={`${tbl.td} text-muted`}>{humanize(i.status)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <Empty title="No incidents recorded">Report an incident as soon as it is noticed. The CERT-In clock is 6 hours.</Empty>
        )}
      </div>

      <Drawer
        open={creating}
        onClose={() => setCreating(false)}
        title="Report an incident"
        footer={<><Button variant="ghost" onClick={() => setCreating(false)}>Cancel</Button><Button onClick={create} busy={busy} disabled={!form.title}>Report incident</Button></>}
      >
        <FormError error={formError} />
        <Field label="What happened">{(id) => <Input id={id} value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} placeholder="e.g. Support inbox credentials phished" />}</Field>
        <Field label="Details">{(id) => <Textarea id={id} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />}</Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Noticed at (IST)">{(id) => <Input id={id} type="datetime-local" value={form.detected_at} onChange={(e) => setForm({ ...form, detected_at: e.target.value })} />}</Field>
          <Field label="Severity">
            {(id) => (
              <Select id={id} value={form.severity} onChange={(e) => setForm({ ...form, severity: e.target.value })}>
                <option value="sev1">SEV-1: confirmed breach or major outage</option>
                <option value="sev2">SEV-2: likely compromise, limited impact</option>
                <option value="sev3">SEV-3: suspicious event</option>
              </Select>
            )}
          </Field>
        </div>
        <Field label="Category">{(id) => <Input id={id} value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })} placeholder="e.g. Phishing, Data leak, Ransomware" />}</Field>
        <Checkbox
          label="Reportable to CERT-In"
          hint="Annexure I types include targeted scanning, system compromise, unauthorised access, data breach or leak, ransomware and attacks on cloud or critical systems."
          checked={form.certin_reportable}
          onChange={(v) => setForm({ ...form, certin_reportable: v })}
        />
        <Checkbox
          label="Personal data breach"
          hint="Starts the DPDP clock: inform the Board and affected people without delay, detailed report to the Board within 72 hours."
          checked={form.personal_data_breach}
          onChange={(v) => setForm({ ...form, personal_data_breach: v })}
        />
        <Field label="Incident lead">{(id) => <MemberSelect id={id} value={form.lead_id} onChange={(v) => setForm({ ...form, lead_id: v })} />}</Field>
      </Drawer>
    </>
  );
}
