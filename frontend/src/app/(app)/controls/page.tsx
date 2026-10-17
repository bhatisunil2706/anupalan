"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { MemberSelect } from "@/components/pickers";

import { useSession } from "@/components/session";
import {
  Badge,
  Button,
  Drawer,
  Empty,
  Field,
  FormError,
  HEALTH,
  HealthBadge,
  Input,
  LoadError,
  Loading,
  PageHeader,
  Select,
  Textarea,
  tbl,
  useToast,
} from "@/components/ui";
import { api, useApi } from "@/lib/api";
import type { Control, Health } from "@/lib/types";

export default function ControlsPage() {
  const router = useRouter();
  const { me, canWrite } = useSession();
  const { data, error, loading, reload } = useApi<Control[]>("/controls");
  const [q, setQ] = useState("");
  const [health, setHealth] = useState("");
  const [category, setCategory] = useState("");
  const [framework, setFramework] = useState("");
  const [owner, setOwner] = useState("");
  const [adding, setAdding] = useState(false);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [bulkOwner, setBulkOwner] = useState("");
  const [busy, setBusy] = useState(false);
  const toast = useToast();

  useEffect(() => {
    const o = new URLSearchParams(window.location.search).get("owner");
    if (o === "me" || o === "none") setOwner(o);
  }, []);

  async function setControlOwner(c: Control, userId: string) {
    try {
      await api(`/controls/${c.id}`, { method: "PATCH", json: userId ? { owner_id: userId } : { clear_owner: true } });
      toast(userId ? `${c.code} assigned` : `${c.code} unassigned`);
      reload();
    } catch (e) {
      toast(e instanceof Error ? e.message : "Failed", "error");
    }
  }

  async function bulk(json: Record<string, unknown>, msg: string) {
    setBusy(true);
    try {
      const r = await api<{ updated: number }>("/controls/bulk", { method: "POST", json: { ids: [...selected], ...json } });
      toast(`${r.updated} controls ${msg}`);
      setSelected(new Set());
      setBulkOwner("");
      reload();
    } catch (e) {
      toast(e instanceof Error ? e.message : "Failed", "error");
    } finally {
      setBusy(false);
    }
  }

  const categories = useMemo(() => [...new Set((data ?? []).map((c) => c.category))].sort(), [data]);
  const frameworks = useMemo(() => [...new Set((data ?? []).flatMap((c) => c.frameworks))].sort(), [data]);

  const rows = useMemo(
    () =>
      (data ?? []).filter(
        (c) =>
          (!health || c.health === health) &&
          (!category || c.category === category) &&
          (!framework || c.frameworks.includes(framework)) &&
          (!owner || (owner === "me" ? c.owner?.id === me.user.id : !c.owner)) &&
          (!q || `${c.code} ${c.title}`.toLowerCase().includes(q.toLowerCase())),
      ),
    [data, q, health, category, framework, owner, me.user.id],
  );

  const allShown = rows.length > 0 && rows.every((c) => selected.has(c.id));
  function toggle(id: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  if (loading && !data) return <Loading />;
  if (error || !data) return <LoadError error={error ?? "Could not load"} retry={reload} />;

  return (
    <>
      <PageHeader
        title="Controls"
        description="Each control is done once and counts for every framework it maps to. A control passes when it is implemented and has current evidence."
        actions={canWrite && <Button variant="secondary" onClick={() => setAdding(true)}>Add custom control</Button>}
      />
      <div className="mb-4 flex flex-wrap gap-2">
        <Input placeholder="Search code or title" value={q} onChange={(e) => setQ(e.target.value)} className="w-56" aria-label="Search controls" />
        <Select value={health} onChange={(e) => setHealth(e.target.value)} className="w-44" aria-label="Status">
          <option value="">All statuses</option>
          {(Object.keys(HEALTH) as Health[]).map((h) => <option key={h} value={h}>{HEALTH[h].label}</option>)}
        </Select>
        <Select value={framework} onChange={(e) => setFramework(e.target.value)} className="w-44" aria-label="Framework">
          <option value="">All frameworks</option>
          {frameworks.map((f) => <option key={f}>{f}</option>)}
        </Select>
        <Select value={category} onChange={(e) => setCategory(e.target.value)} className="w-48" aria-label="Category">
          <option value="">All categories</option>
          {categories.map((c) => <option key={c}>{c}</option>)}
        </Select>
        <Select value={owner} onChange={(e) => setOwner(e.target.value)} className="w-40" aria-label="Owner">
          <option value="">Any owner</option>
          <option value="me">Owned by me</option>
          <option value="none">No owner</option>
        </Select>
      </div>

      {canWrite && selected.size > 0 && (
        <div className="sticky top-2 z-10 mb-3 flex flex-wrap items-center gap-2 rounded-lg border border-ink/30 bg-ink-50 px-3 py-2 text-sm shadow-sm" role="region" aria-label="Bulk actions">
          <span className="font-medium">{selected.size} selected</span>
          <span className="mx-1 h-5 w-px bg-line" aria-hidden />
          <div className="w-48">
            <MemberSelect value={bulkOwner} onChange={setBulkOwner} emptyLabel="Choose a person…" />
          </div>
          <Button size="sm" disabled={!bulkOwner} busy={busy} onClick={() => bulk({ owner_id: bulkOwner }, "assigned")}>Assign</Button>
          <Button size="sm" variant="secondary" busy={busy} onClick={() => bulk({ clear_owner: true }, "unassigned")}>Remove owner</Button>
          <Select aria-label="Set status" className="w-40" value="" onChange={(e) => e.target.value && bulk({ status: e.target.value }, "updated")}>
            <option value="">Set status…</option>
            <option value="not_started">Not started</option>
            <option value="in_progress">In progress</option>
            <option value="implemented">Implemented</option>
          </Select>
          <button type="button" onClick={() => setSelected(new Set())} className="ml-auto text-muted hover:text-text">Clear selection</button>
        </div>
      )}

      <div className="rounded-lg border border-line bg-surface">
        <div className={tbl.wrap}>
          <table className={tbl.table}>
            <thead>
              <tr>
                {canWrite && (
                  <th className={`${tbl.th} w-10`}>
                    <input
                      type="checkbox"
                      aria-label="Select all shown controls"
                      className="h-4 w-4 accent-ink"
                      checked={allShown}
                      onChange={() => setSelected(allShown ? new Set() : new Set(rows.map((c) => c.id)))}
                    />
                  </th>
                )}
                <th className={tbl.th}>Control</th>
                <th className={tbl.th}>Frameworks</th>
                <th className={tbl.th}>Owner</th>
                <th className={tbl.th}>Evidence</th>
                <th className={tbl.th}>Status</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((c) => (
                <tr key={c.id} className={`${tbl.row} cursor-pointer ${selected.has(c.id) ? "bg-ink-50/60" : ""}`} onClick={() => router.push(`/controls/${c.id}`)}>
                  {canWrite && (
                    <td className={tbl.td} onClick={(e) => e.stopPropagation()}>
                      <input type="checkbox" aria-label={`Select ${c.code}`} className="h-4 w-4 accent-ink" checked={selected.has(c.id)} onChange={() => toggle(c.id)} />
                    </td>
                  )}
                  <td className={tbl.td}>
                    <Link href={`/controls/${c.id}`} className="block" onClick={(e) => e.stopPropagation()}>
                      <span className="text-xs font-semibold text-muted">{c.code}</span>
                      <span className="block font-medium">{c.title}</span>
                    </Link>
                  </td>
                  <td className={tbl.td}>
                    <div className="flex flex-wrap gap-1">
                      {c.frameworks.map((f) => <Badge key={f} tone="ink">{f}</Badge>)}
                    </div>
                  </td>
                  <td className={`${tbl.td} whitespace-nowrap text-muted`} onClick={(e) => canWrite && e.stopPropagation()}>
                    {canWrite ? (
                      <div className="w-40" title="Change owner">
                        <MemberSelect value={c.owner?.id ?? ""} onChange={(v) => setControlOwner(c, v)} emptyLabel="Unassigned" />
                      </div>
                    ) : (
                      c.owner?.full_name ?? "—"
                    )}
                  </td>
                  <td className={`${tbl.td} whitespace-nowrap text-muted`}>
                    {c.valid_evidence}/{c.total_evidence}
                    {c.automatable && <span className="ml-1.5 text-xs text-prog" title="Can be checked by an integration">auto</span>}
                  </td>
                  <td className={tbl.td}><HealthBadge health={c.health} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {!rows.length && <Empty title="No controls match these filters" />}
      </div>
      <p className="mt-3 text-xs text-muted">{rows.length} of {data.length} controls</p>

      <NewControl open={adding} onClose={() => setAdding(false)} onCreated={(id) => router.push(`/controls/${id}`)} />
    </>
  );
}

function NewControl({ open, onClose, onCreated }: { open: boolean; onClose: () => void; onCreated: (id: string) => void }) {
  const [form, setForm] = useState({ code: "", title: "", description: "", category: "Custom", frequency: "annual" });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function save() {
    setBusy(true);
    setError(null);
    try {
      const c = await api<Control>("/controls", { method: "POST", json: { ...form, code: form.code.toUpperCase() } });
      onCreated(c.id);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed");
      setBusy(false);
    }
  }

  return (
    <Drawer open={open} onClose={onClose} title="Add custom control" footer={<><Button variant="ghost" onClick={onClose}>Cancel</Button><Button onClick={save} busy={busy}>Add control</Button></>}>
      <FormError error={error} />
      <Field label="Code" hint="Letters, numbers and dashes, e.g. CUS-01">{(id) => <Input id={id} value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value })} />}</Field>
      <Field label="Title">{(id) => <Input id={id} value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} />}</Field>
      <Field label="Description">{(id) => <Textarea id={id} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />}</Field>
      <Field label="Review frequency">
        {(id) => (
          <Select id={id} value={form.frequency} onChange={(e) => setForm({ ...form, frequency: e.target.value })}>
            {["continuous", "monthly", "quarterly", "semiannual", "annual", "once"].map((f) => <option key={f} value={f}>{f}</option>)}
          </Select>
        )}
      </Field>
    </Drawer>
  );
}
