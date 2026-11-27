"use client";

import Link from "next/link";
import { useState } from "react";

import { MemberSelect } from "@/components/pickers";
import { useSession } from "@/components/session";
import { Badge, Button, ButtonLink, Checkbox, Drawer, Field, FormError, Input, Panel, Select, Textarea, cx, useToast } from "@/components/ui";
import { api, useApi } from "@/lib/api";
import { fmtDateTime, localToIso, nowLocal } from "@/lib/format";
import type { Incident, RegulatorOption, UserBrief } from "@/lib/types";

const EMPTY = {
  title: "", description: "", severity: "sev3", category: "", detected_at: "",
  certin_reportable: false, personal_data_breach: false, lead_id: "", regulators: [] as string[],
};

/** The "Report an incident" form, used on the dashboard and the Incidents page. Anyone except auditors can report. */
export function ReportIncidentDrawer({
  open,
  onClose,
  onReported,
}: {
  open: boolean;
  onClose: () => void;
  /** Called after a successful report. If omitted, the drawer shows a confirmation with a link to the incident. */
  onReported?: (i: Incident) => void;
}) {
  const { isAdmin } = useSession();
  const { data: regulators } = useApi<RegulatorOption[]>(open ? "/incident-regulators" : null);
  const [form, setForm] = useState(() => ({ ...EMPTY, detected_at: nowLocal() }));
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState<Incident | null>(null);

  function close() {
    onClose();
    setForm({ ...EMPTY, detected_at: nowLocal() });
    setError(null);
    setDone(null);
  }

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      const i = await api<Incident>("/incidents", {
        method: "POST",
        json: { ...form, detected_at: localToIso(form.detected_at), lead_id: form.lead_id || null },
      });
      if (onReported) onReported(i);
      else setDone(i);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not report the incident");
    } finally {
      setBusy(false);
    }
  }

  if (done)
    return (
      <Drawer
        open={open}
        onClose={close}
        title="Incident reported"
        footer={<><Button variant="ghost" onClick={close}>Done</Button><ButtonLink href={`/incidents/${done.id}`} variant="primary">Open INC-{done.number}</ButtonLink></>}
      >
        <div className="rounded-md border border-pass/30 bg-pass-50 px-4 py-3">
          <p className="text-sm font-semibold">INC-{done.number} has been reported</p>
          <p className="mt-1 text-sm text-muted">{done.title}</p>
        </div>
        <ul className="list-disc space-y-2 pl-5 text-sm text-muted">
          <li>Your organisation&apos;s admins have been alerted{done.certin_reportable || done.personal_data_breach ? ", and the regulatory clocks are running" : ""}.</li>
          <li>You&apos;ll get every update about this incident by email, in a single thread with the subject <span className="font-medium text-text">INC-{done.number}: {done.title}</span>.</li>
          <li>Add anything you remember later as an update on the incident page.</li>
        </ul>
      </Drawer>
    );

  return (
    <Drawer
      open={open}
      onClose={close}
      title="Report an incident"
      footer={<><Button variant="ghost" onClick={close}>Cancel</Button><Button onClick={submit} busy={busy} disabled={!form.title.trim()}>Report incident</Button></>}
    >
      <p className="text-sm text-muted">
        Report anything suspicious straight away, even if you&apos;re not sure it&apos;s serious. Some incidents must be reported to CERT-In within 6 hours of being noticed.
      </p>
      <FormError error={error} />
      <Field label="What happened">{(id) => <Input id={id} value={form.title} maxLength={300} onChange={(e) => setForm({ ...form, title: e.target.value })} placeholder="e.g. I clicked a link in a suspicious email" />}</Field>
      <Field label="Details" hint="What you saw, which systems or data are involved, and anything you've already done. Avoid pasting passwords or customers' personal data.">
        {(id) => <Textarea id={id} rows={4} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />}
      </Field>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Noticed at (IST)">{(id) => <Input id={id} type="datetime-local" value={form.detected_at} onChange={(e) => setForm({ ...form, detected_at: e.target.value })} />}</Field>
        <Field label="How serious does it look?">
          {(id) => (
            <Select id={id} value={form.severity} onChange={(e) => setForm({ ...form, severity: e.target.value })}>
              <option value="sev3">SEV-3: suspicious, not sure yet</option>
              <option value="sev2">SEV-2: likely compromise, limited impact</option>
              <option value="sev1">SEV-1: confirmed breach or major outage</option>
            </Select>
          )}
        </Field>
      </div>
      <Field label="Category" hint="Optional">{(id) => <Input id={id} value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })} placeholder="e.g. Phishing, Lost device, Data leak, Ransomware" />}</Field>
      <Checkbox
        label="Personal data may be involved"
        hint="Customer, employee or other people's data may have been seen, copied, changed or lost. Starts the DPDP clock. If unsure, tick it: the incident lead can change it."
        checked={form.personal_data_breach}
        onChange={(v) => setForm({ ...form, personal_data_breach: v })}
      />
      <Checkbox
        label="Reportable to CERT-In"
        hint="For example unauthorised access, system compromise, data leak, ransomware, or attacks on servers or cloud accounts. Starts the 6-hour clock."
        checked={form.certin_reportable}
        onChange={(v) => setForm({ ...form, certin_reportable: v })}
      />
      {(regulators ?? []).filter((r) => r.suggested).map((r) => (
        <Checkbox
          key={r.key}
          label={r.label}
          hint={`${r.hint} Tick it for any cyber incident that affects your regulated business.`}
          checked={form.regulators.includes(r.key)}
          onChange={(v) => setForm({ ...form, regulators: v ? [...form.regulators, r.key] : form.regulators.filter((k) => k !== r.key) })}
        />
      ))}
      {isAdmin && <Field label="Incident lead" hint="Optional. The lead receives every update by email.">{(id) => <MemberSelect id={id} value={form.lead_id} onChange={(v) => setForm({ ...form, lead_id: v })} />}</Field>}
    </Drawer>
  );
}

interface IncidentEvent {
  id: string;
  kind: string;
  message: string;
  created_at: string;
  user: UserBrief | null;
}

interface Activity {
  events: IncidentEvent[];
  followers: UserBrief[];
  following: boolean;
  reported_by: UserBrief | null;
}

const KIND: Record<string, { label: string; dot: string }> = {
  reported: { label: "Reported", dot: "bg-fail" },
  note: { label: "Update", dot: "bg-ink" },
  status: { label: "Status", dot: "bg-prog" },
  severity: { label: "Severity", dot: "bg-warn" },
  lead: { label: "Lead", dot: "bg-ink" },
  regulatory: { label: "Regulatory", dot: "bg-pass" },
  classification: { label: "Classification", dot: "bg-warn" },
  details: { label: "Edited", dot: "bg-line" },
};

/** Timeline of an incident with a box to post updates ("timeline"), or who gets the email updates ("followers"). */
export function IncidentActivity({ incident, version, part }: { incident: Incident; version: number; part: "timeline" | "followers" }) {
  const { canWrite } = useSession();
  const toast = useToast();
  const { data, reload } = useApi<Activity>(`/incidents/${incident.id}/activity?v=${version}`);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);

  async function post() {
    setBusy(true);
    try {
      await api(`/incidents/${incident.id}/updates`, { method: "POST", json: { message } });
      setMessage("");
      toast("Update posted and emailed to followers");
      reload();
    } catch (e) {
      toast(e instanceof Error ? e.message : "Failed", "error");
    } finally {
      setBusy(false);
    }
  }

  async function toggleFollow() {
    try {
      await api(`/incidents/${incident.id}/follow`, { method: data?.following ? "DELETE" : "POST" });
      toast(data?.following ? "You'll no longer get email updates" : "You'll get every update by email");
      reload();
    } catch (e) {
      toast(e instanceof Error ? e.message : "Failed", "error");
    }
  }

  if (part === "timeline")
    return (
      <Panel title="Timeline">
        {canWrite && (
          <div className="mb-5 space-y-2">
            <Textarea
              aria-label="Post an update"
              rows={3}
              maxLength={5000}
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              placeholder="Post an update: what you found, what you did, what happens next"
            />
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="text-xs text-muted">Updates are emailed to everyone following this incident.</p>
              <Button size="sm" onClick={post} busy={busy} disabled={!message.trim()}>Post update</Button>
            </div>
          </div>
        )}
        {data ? (
          <ol className="relative space-y-4 border-l border-line pl-5">
            {data.events.map((e) => {
              const k = KIND[e.kind] ?? { label: e.kind, dot: "bg-line" };
              return (
                <li key={e.id} className="relative">
                  <span className={cx("absolute -left-[25px] top-1.5 h-2.5 w-2.5 rounded-full ring-4 ring-surface", k.dot)} aria-hidden />
                  <p className="text-xs text-muted">
                    <span className="font-semibold text-text">{e.user?.full_name ?? "Pramaanly"}</span> · {k.label} · {fmtDateTime(e.created_at)}
                  </p>
                  <p className={cx("mt-0.5 whitespace-pre-wrap text-sm", e.kind === "details" && "text-muted")}>{e.message}</p>
                </li>
              );
            })}
            {!data.events.length && <li className="text-sm text-muted">No activity recorded yet.</li>}
          </ol>
        ) : (
          <p className="text-sm text-muted">Loading…</p>
        )}
      </Panel>
    );

  return (
      <Panel title="Email updates" className="mt-6">
        <p className="text-sm text-muted">
          Followers get every update in one email thread: <span className="font-medium text-text">{incident.email_subject || `INC-${incident.number}: ${incident.title}`}</span>
        </p>
        {data && (
          <>
            <ul className="mt-3 space-y-1.5">
              {data.followers.map((u) => (
                <li key={u.id} className="flex items-center justify-between gap-2 text-sm">
                  <span className="truncate">{u.full_name}</span>
                  <span className="flex shrink-0 gap-1">
                    {incident.lead?.id === u.id && <Badge tone="ink">Lead</Badge>}
                    {data.reported_by?.id === u.id && <Badge tone="idle">Reporter</Badge>}
                  </span>
                </li>
              ))}
              {!data.followers.length && <li className="text-sm text-muted">Nobody follows this incident; admins get the emails.</li>}
            </ul>
            <Button size="sm" variant="secondary" className="mt-4 w-full" onClick={toggleFollow}>
              {data.following ? "Stop email updates" : "Follow by email"}
            </Button>
          </>
        )}
      </Panel>
  );
}

/** Small "Open incidents" list for the dashboard. */
export function OpenIncidents({ items }: { items: { id: string; number: number; title: string; severity: string; status: string; detected_at: string }[] }) {
  if (!items.length) return <p className="px-4 py-4 text-sm text-muted">No open incidents.</p>;
  return (
    <ul>
      {items.map((i) => (
        <li key={i.id} className="border-b border-line last:border-0">
          <Link href={`/incidents/${i.id}`} className="flex items-center gap-3 px-4 py-3 hover:bg-ink-50/40">
            <Badge tone={i.severity === "sev1" ? "fail" : i.severity === "sev2" ? "warn" : "idle"}>{i.severity.toUpperCase().replace("SEV", "SEV-")}</Badge>
            <span className="min-w-0 flex-1">
              <span className="block truncate text-sm font-medium">INC-{i.number} {i.title}</span>
              <span className="text-xs text-muted">Noticed {fmtDateTime(i.detected_at)} · {i.status[0].toUpperCase() + i.status.slice(1)}</span>
            </span>
          </Link>
        </li>
      ))}
    </ul>
  );
}
