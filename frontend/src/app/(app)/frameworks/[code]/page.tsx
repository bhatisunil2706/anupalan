"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useMemo, useState } from "react";

import { Badge, HealthBadge, Input, LoadError, Loading, PageHeader, Select, cx } from "@/components/ui";
import { useApi } from "@/lib/api";
import type { RequirementRow } from "@/lib/types";

interface Detail {
  framework: { code: string; name: string; short_name: string; description: string; source_url: string; review_status: string; enabled: boolean };
  requirements: RequirementRow[];
}

const STATUS = {
  met: { label: "Met", tone: "pass" },
  partial: { label: "In progress", tone: "prog" },
  not_met: { label: "Not met", tone: "idle" },
  not_applicable: { label: "Not applicable", tone: "idle" },
} as const;

export default function FrameworkDetailPage() {
  const { code } = useParams<{ code: string }>();
  const { data, error, loading, reload } = useApi<Detail>(`/frameworks/${code}`);
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");
  const [open, setOpen] = useState<string | null>(null);

  const groups = useMemo(() => {
    const rows = (data?.requirements ?? []).filter(
      (r) =>
        (!status || r.status === status) &&
        (!q || `${r.ref} ${r.title} ${r.guidance}`.toLowerCase().includes(q.toLowerCase())),
    );
    const out: [string, RequirementRow[]][] = [];
    for (const r of rows) {
      const last = out[out.length - 1];
      if (last && last[0] === r.section) last[1].push(r);
      else out.push([r.section, [r]]);
    }
    return out;
  }, [data, q, status]);

  if (loading && !data) return <Loading />;
  if (error || !data) return <LoadError error={error ?? "Could not load"} retry={reload} />;
  const fw = data.framework;

  if (!fw.enabled)
    return (
      <PageHeader title={fw.name} description={<>This framework is off. <Link href="/frameworks" className="text-ink underline">Turn it on</Link> to track it.</>} />
    );

  const counts = data.requirements.reduce<Record<string, number>>((a, r) => ({ ...a, [r.status]: (a[r.status] ?? 0) + 1 }), {});

  return (
    <>
      <PageHeader
        title={fw.name}
        description={
          <>
            {counts.met ?? 0} met, {counts.partial ?? 0} in progress, {counts.not_met ?? 0} not met
            {counts.not_applicable ? `, ${counts.not_applicable} not applicable` : ""}.{" "}
            {fw.source_url && (
              <a href={fw.source_url} target="_blank" rel="noreferrer" className="text-ink underline">
                Official source
              </a>
            )}
          </>
        }
      />
      {fw.review_status === "draft" && (
        <p className="mb-4 rounded-md border border-warn/25 bg-warn-50 px-3 py-2 text-sm text-warn">
          This framework&apos;s guidance text is written by our team and is still being reviewed against the official text. Check the
          official source before relying on it.
        </p>
      )}
      <div className="mb-4 flex flex-wrap gap-2">
        <Input placeholder="Search requirements" value={q} onChange={(e) => setQ(e.target.value)} className="max-w-xs" aria-label="Search requirements" />
        <Select value={status} onChange={(e) => setStatus(e.target.value)} className="max-w-[180px]" aria-label="Filter by status">
          <option value="">All statuses</option>
          {Object.entries(STATUS).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
        </Select>
      </div>

      <div className="space-y-6">
        {groups.map(([section, rows]) => (
          <section key={section} className="rounded-lg border border-line bg-surface">
            <h2 className="border-b border-line px-4 py-2.5 text-sm font-semibold">{section}</h2>
            <ul>
              {rows.map((r) => {
                const s = STATUS[r.status];
                const isOpen = open === r.id;
                return (
                  <li key={r.id} className={cx("border-b border-line last:border-0", r.status === "not_applicable" && "opacity-60")}>
                    <button
                      onClick={() => setOpen(isOpen ? null : r.id)}
                      aria-expanded={isOpen}
                      className="flex w-full items-start gap-3 px-4 py-3 text-left hover:bg-ink-50/40"
                    >
                      <span className="w-20 shrink-0 pt-0.5 text-xs font-semibold text-muted">{r.ref}</span>
                      <span className="min-w-0 flex-1 text-sm">{r.title}</span>
                      <Badge tone={s.tone}>{s.label}</Badge>
                    </button>
                    {isOpen && (
                      <div className="space-y-3 px-4 pb-4 pl-[108px]">
                        <p className="max-w-[72ch] text-sm leading-relaxed text-muted">{r.guidance}</p>
                        {r.status === "not_applicable" && (
                          <p className="text-xs text-muted">Applies only if your profile says so. Change it in Settings.</p>
                        )}
                        <ul className="space-y-1.5">
                          {r.controls.map((c) => (
                            <li key={c.id}>
                              <Link href={`/controls/${c.id}`} className="flex items-center gap-3 text-sm hover:underline">
                                <span className="w-14 text-xs font-semibold text-muted">{c.code}</span>
                                <span className="flex-1">{c.title}</span>
                                <HealthBadge health={c.health} />
                              </Link>
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </li>
                );
              })}
            </ul>
          </section>
        ))}
        {!groups.length && <p className="text-sm text-muted">No requirements match these filters.</p>}
      </div>
    </>
  );
}
