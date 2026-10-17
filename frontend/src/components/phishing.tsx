"use client";

import { Fish, Plus, Send } from "lucide-react";
import { useState } from "react";

import { Badge, Button, Checkbox, Drawer, Empty, Field, FormError, Input, LoadError, Loading, Panel, tbl, useToast } from "@/components/ui";
import { api, useApi } from "@/lib/api";
import { fmtDate, fmtDateTime } from "@/lib/format";

interface Template { slug: string; name: string; difficulty: string; sender: string; subject: string; preview: string }
interface Campaign {
  id: string; name: string; template_slug: string; template_name: string; difficulty: string; departments: string[];
  status: "draft" | "sending" | "sent" | "closed"; enroll_clickers: boolean; sent_at: string | null; closed_at: string | null;
  created_at: string; sent: number; clicked: number; click_rate: number; eligible?: number;
}
interface CampaignDetail extends Campaign {
  subject: string; sender: string; red_flags: string[];
  results: { sent: number; failed: number; clicked: number; click_rate: number;
    departments: { department: string; sent: number; clicked: number; click_rate: number }[];
    targets: { email: string; full_name: string; department: string; sent_at: string | null; clicked_at: string | null; error: string }[] };
}

const STATUS = { draft: { label: "Draft", tone: "idle" }, sending: { label: "Sending", tone: "prog" }, sent: { label: "Running", tone: "warn" }, closed: { label: "Closed", tone: "pass" } } as const;

export function PhishingTab() {
  const { data, error, loading, reload } = useApi<Campaign[]>("/training/phishing/campaigns");
  const [creating, setCreating] = useState(false);
  const [open, setOpen] = useState<string | null>(null);

  if (loading && !data) return <Loading />;
  if (error || !data) return <LoadError error={error ?? "Could not load"} retry={reload} />;
  const finished = data.filter((c) => c.sent > 0);
  const latest = finished[0];
  const avg = finished.length ? Math.round(finished.reduce((s, c) => s + c.click_rate, 0) / finished.length) : null;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <p className="max-w-[72ch] text-sm text-muted">
          Send realistic, harmless test emails to your own staff. Anyone who clicks sees a short lesson on the warning signs, and can be assigned the phishing course automatically. Emails come from this platform&apos;s address and only go to your company&apos;s email domains.
        </p>
        <Button onClick={() => setCreating(true)}><Plus size={14} aria-hidden /> New simulation</Button>
      </div>
      {finished.length > 0 && (
        <div className="grid gap-3 sm:grid-cols-3">
          <div className="rounded-lg border border-line bg-surface p-4"><p className="text-2xl font-bold">{latest.click_rate}%</p><p className="text-xs text-muted">Clicked in the latest simulation</p></div>
          <div className="rounded-lg border border-line bg-surface p-4"><p className="text-2xl font-bold">{avg}%</p><p className="text-xs text-muted">Average click rate ({finished.length} simulation{finished.length > 1 ? "s" : ""})</p></div>
          <div className="rounded-lg border border-line bg-surface p-4"><p className="text-2xl font-bold">{finished.reduce((s, c) => s + c.sent, 0)}</p><p className="text-xs text-muted">Test emails sent</p></div>
        </div>
      )}
      <div className="rounded-lg border border-line bg-surface">
        {data.length ? (
          <div className={tbl.wrap}>
            <table className={tbl.table}>
              <thead><tr><th className={tbl.th}>Simulation</th><th className={tbl.th}>Status</th><th className={tbl.th}>Sent</th><th className={tbl.th}>Clicked</th><th className={tbl.th}>Date</th></tr></thead>
              <tbody>
                {data.map((c) => (
                  <tr key={c.id} className={`${tbl.row} cursor-pointer`} onClick={() => setOpen(c.id)}>
                    <td className={tbl.td}><p className="font-medium">{c.name}</p><p className="text-xs text-muted">{c.template_name} · {c.difficulty}{c.departments.length ? ` · ${c.departments.join(", ")}` : " · everyone"}</p></td>
                    <td className={tbl.td}><Badge tone={STATUS[c.status].tone}>{STATUS[c.status].label}</Badge></td>
                    <td className={tbl.td}>{c.status === "draft" ? <span className="text-muted">{c.eligible} people</span> : c.sent}</td>
                    <td className={tbl.td}>{c.sent ? <Badge tone={c.click_rate > 20 ? "fail" : c.click_rate > 5 ? "warn" : "pass"}>{c.clicked} ({c.click_rate}%)</Badge> : "—"}</td>
                    <td className={`${tbl.td} text-xs text-muted`}>{c.sent_at ? fmtDate(c.sent_at) : `Created ${fmtDate(c.created_at)}`}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <Empty title="No simulations yet" action={<Button onClick={() => setCreating(true)}><Fish size={14} aria-hidden /> Create your first simulation</Button>}>
            Most companies run one every quarter, with harder templates as click rates fall.
          </Empty>
        )}
      </div>
      {creating && <NewCampaign onClose={() => setCreating(false)} onCreated={(id) => { setCreating(false); reload(); setOpen(id); }} />}
      {open && <CampaignDrawer id={open} onClose={() => setOpen(null)} onChanged={reload} />}
    </div>
  );
}

function NewCampaign({ onClose, onCreated }: { onClose: () => void; onCreated: (id: string) => void }) {
  const templates = useApi<Template[]>("/training/phishing/templates");
  const depts = useApi<string[]>("/training/departments");
  const [form, setForm] = useState({ name: `Phishing test ${new Date().toLocaleDateString("en-IN", { month: "short", year: "numeric" })}`, template_slug: "", departments: [] as string[], enroll_clickers: true });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function save() {
    setBusy(true);
    setError(null);
    try {
      const c = await api<Campaign>("/training/phishing/campaigns", { method: "POST", json: form });
      onCreated(c.id);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed");
      setBusy(false);
    }
  }
  const chosen = templates.data?.find((t) => t.slug === form.template_slug);

  return (
    <Drawer open onClose={onClose} title="New phishing simulation" wide footer={<><Button variant="ghost" onClick={onClose}>Cancel</Button><Button busy={busy} disabled={!form.template_slug || form.name.length < 3} onClick={save}>Save as draft</Button></>}>
      <FormError error={error} />
      <Field label="Name">{(id) => <Input id={id} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />}</Field>
      <fieldset>
        <legend className="mb-2 text-[13px] font-medium">Email template</legend>
        {templates.loading && !templates.data ? <Loading /> : (
          <div className="grid gap-2 sm:grid-cols-2">
            {(templates.data ?? []).map((t) => (
              <label key={t.slug} className={`cursor-pointer rounded-md border px-3 py-2.5 text-sm ${form.template_slug === t.slug ? "border-ink bg-ink-50/60" : "border-line hover:border-ink/40"}`}>
                <input type="radio" name="tpl" className="sr-only" checked={form.template_slug === t.slug} onChange={() => setForm({ ...form, template_slug: t.slug })} />
                <span className="flex items-center justify-between gap-2 font-medium">{t.name} <Badge tone={t.difficulty === "Hard" ? "fail" : t.difficulty === "Medium" ? "warn" : "pass"}>{t.difficulty}</Badge></span>
                <span className="mt-0.5 block text-xs text-muted">From &quot;{t.sender}&quot;: {t.subject}</span>
              </label>
            ))}
          </div>
        )}
      </fieldset>
      {chosen && (
        <div className="rounded-md border border-line bg-paper p-3 text-sm">
          <p className="text-xs text-muted">Preview</p>
          <p className="mt-1"><span className="text-muted">From:</span> {chosen.sender}</p>
          <p><span className="text-muted">Subject:</span> {chosen.subject}</p>
          <pre className="mt-2 whitespace-pre-wrap font-sans text-sm">{chosen.preview}</pre>
        </div>
      )}
      <fieldset>
        <legend className="mb-2 text-[13px] font-medium">Who receives it</legend>
        {(depts.data ?? []).length ? (
          <div className="space-y-1.5">
            <p className="text-xs text-muted">Leave all unticked to send to everyone.</p>
            {(depts.data ?? []).map((d) => <Checkbox key={d} label={d} checked={form.departments.includes(d)} onChange={(v) => setForm({ ...form, departments: v ? [...form.departments, d] : form.departments.filter((x) => x !== d) })} />)}
          </div>
        ) : <p className="text-sm text-muted">Everyone in your workspace and HR roster on your company&apos;s email domains.</p>}
      </fieldset>
      <Checkbox label="Assign the phishing course to anyone who clicks" hint="Due in 14 days; shows in their to-do list with the reason." checked={form.enroll_clickers} onChange={(v) => setForm({ ...form, enroll_clickers: v })} />
      <p className="rounded-md border border-warn/30 bg-warn-50 px-3 py-2 text-xs text-warn">Before launching, ask IT to allow-list this platform&apos;s sending address so the test emails aren&apos;t filtered, and let leadership know a test is running.</p>
    </Drawer>
  );
}

function CampaignDrawer({ id, onClose, onChanged }: { id: string; onClose: () => void; onChanged: () => void }) {
  const toast = useToast();
  const { data: c, error, loading, reload } = useApi<CampaignDetail>(`/training/phishing/campaigns/${id}`);
  const [busy, setBusy] = useState(false);

  async function act(path: string, method: string, msg: string, confirmText?: string) {
    if (confirmText && !confirm(confirmText)) return;
    setBusy(true);
    try {
      await api(`/training/phishing/campaigns/${id}${path}`, { method });
      toast(msg);
      onChanged();
      if (method === "DELETE") onClose();
      else setTimeout(reload, 600);
    } catch (e) {
      toast(e instanceof Error ? e.message : "Failed", "error");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Drawer open onClose={onClose} title={c?.name ?? "Simulation"} wide
      footer={c && (
        <>
          {c.status === "draft" && <Button variant="danger" className="mr-auto" onClick={() => act("", "DELETE", "Draft deleted", "Delete this draft?")}>Delete</Button>}
          {c.status === "draft" && <Button busy={busy} onClick={() => act("/launch", "POST", "Sending test emails", `Send the test email to ${c.eligible} people now?`)}><Send size={14} aria-hidden /> Launch to {c.eligible} people</Button>}
          {(c.status === "sent" || c.status === "sending") && <Button variant="secondary" busy={busy} onClick={() => act("/close", "POST", "Simulation closed")}>Close simulation</Button>}
        </>
      )}>
      {loading && !c ? <Loading /> : error || !c ? <LoadError error={error ?? "Could not load"} /> : (
        <>
          <div className="flex flex-wrap gap-2 text-sm">
            <Badge tone={STATUS[c.status].tone}>{STATUS[c.status].label}</Badge>
            <span className="text-muted">{c.template_name} · {c.difficulty} · from &quot;{c.sender}&quot;</span>
          </div>
          {c.status !== "draft" && (
            <div className="grid gap-3 sm:grid-cols-3">
              <div className="rounded-lg border border-line p-3"><p className="text-xl font-bold">{c.results.sent}</p><p className="text-xs text-muted">Delivered{c.results.failed ? `, ${c.results.failed} failed` : ""}</p></div>
              <div className="rounded-lg border border-line p-3"><p className="text-xl font-bold">{c.results.clicked}</p><p className="text-xs text-muted">Clicked the link</p></div>
              <div className="rounded-lg border border-line p-3"><p className={`text-xl font-bold ${c.results.click_rate > 20 ? "text-fail" : c.results.click_rate > 5 ? "text-warn" : "text-pass"}`}>{c.results.click_rate}%</p><p className="text-xs text-muted">Click rate</p></div>
            </div>
          )}
          {c.results.departments.length > 1 && (
            <Panel title="By department">
              <ul className="space-y-2">
                {c.results.departments.map((d) => (
                  <li key={d.department} className="text-sm">
                    <div className="flex justify-between"><span>{d.department}</span><span className="text-xs text-muted">{d.clicked}/{d.sent} clicked</span></div>
                    <div className="mt-1 h-2 overflow-hidden rounded bg-line"><div className={`h-full ${d.click_rate > 20 ? "bg-fail" : d.click_rate > 5 ? "bg-warn" : "bg-pass"}`} style={{ width: `${Math.max(2, d.click_rate)}%` }} /></div>
                  </li>
                ))}
              </ul>
            </Panel>
          )}
          <div>
            <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">What people should have spotted</p>
            <ul className="list-disc space-y-1 pl-5 text-sm">{c.red_flags.map((f) => <li key={f}>{f}</li>)}</ul>
          </div>
          {c.results.targets.length > 0 && (
            <div className={tbl.wrap}>
              <table className={tbl.table}>
                <thead><tr><th className={tbl.th}>Person</th><th className={tbl.th}>Result</th></tr></thead>
                <tbody>
                  {c.results.targets.map((t) => (
                    <tr key={t.email} className={tbl.row}>
                      <td className={tbl.td}><p className="font-medium">{t.full_name}</p><p className="text-xs text-muted">{t.email}{t.department ? ` · ${t.department}` : ""}</p></td>
                      <td className={tbl.td}>{t.error ? <Badge tone="idle">Not delivered</Badge> : t.clicked_at ? <><Badge tone="fail">Clicked</Badge><p className="mt-1 text-xs text-muted">{fmtDateTime(t.clicked_at)}</p></> : <Badge tone="pass">Didn&apos;t click</Badge>}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <p className="text-xs text-muted">Individual results are visible to admins only. Use them to coach, not to blame: people who report suspicious emails quickly are your best defence.</p>
        </>
      )}
    </Drawer>
  );
}
