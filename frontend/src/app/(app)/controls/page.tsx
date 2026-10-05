"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";

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

      <div className="rounded-lg border border-line bg-surface">
        <div className={tbl.wrap}>
          <table className={tbl.table}>
            <thead>
              <tr>
                <th className={tbl.th}>Control</th>
                <th className={tbl.th}>Frameworks</th>
                <th className={tbl.th}>Owner</th>
                <th className={tbl.th}>Evidence</th>
                <th className={tbl.th}>Status</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((c) => (
                <tr key={c.id} className={`${tbl.row} cursor-pointer`} onClick={() => router.push(`/controls/${c.id}`)}>
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
                  <td className={`${tbl.td} whitespace-nowrap text-muted`}>{c.owner?.full_name ?? "—"}</td>
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
