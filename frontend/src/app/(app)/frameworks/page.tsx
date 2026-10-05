"use client";

import Link from "next/link";
import { useState } from "react";

import { Seal } from "@/components/seal";
import { useSession } from "@/components/session";
import { Badge, Button, LoadError, Loading, PageHeader, useToast } from "@/components/ui";
import { api, useApi } from "@/lib/api";
import type { FrameworkCatalogItem, Readiness } from "@/lib/types";

export default function FrameworksPage() {
  const { isAdmin } = useSession();
  const toast = useToast();
  const catalog = useApi<FrameworkCatalogItem[]>("/frameworks");
  const readiness = useApi<Readiness[]>("/frameworks/readiness");
  const [busy, setBusy] = useState<string | null>(null);

  async function toggle(fw: FrameworkCatalogItem) {
    if (fw.enabled && !confirm(`Turn off ${fw.name}? Your controls and evidence stay, but it leaves your dashboard.`)) return;
    setBusy(fw.code);
    try {
      const r = await api<{ controls_created?: number }>(`/frameworks/${fw.code}/enable`, { method: fw.enabled ? "DELETE" : "POST" });
      toast(fw.enabled ? `${fw.short_name} turned off` : `${fw.short_name} turned on, ${r.controls_created ?? 0} new controls added`);
      await Promise.all([catalog.reload(), readiness.reload()]);
    } catch (e) {
      toast(e instanceof Error ? e.message : "Failed", "error");
    } finally {
      setBusy(null);
    }
  }

  if (catalog.loading && !catalog.data) return <Loading />;
  if (catalog.error || !catalog.data) return <LoadError error={catalog.error ?? "Could not load"} retry={catalog.reload} />;
  const byCode = Object.fromEntries((readiness.data ?? []).map((r) => [r.code, r]));

  return (
    <>
      <PageHeader
        title="Frameworks"
        description="Each framework's requirements map to your shared controls. Turning one on adds only the controls you don't have yet."
      />
      <div className="space-y-3">
        {catalog.data.map((fw) => {
          const r = byCode[fw.code];
          return (
            <article key={fw.code} className="flex flex-col gap-5 rounded-lg border border-line bg-surface p-5 sm:flex-row sm:items-center">
              <div className="w-28 shrink-0">
                {fw.enabled && r ? (
                  <Seal percent={r.percent} size={88} label="" />
                ) : (
                  <div className="flex h-[88px] w-[88px] items-center justify-center rounded-full border-2 border-dashed border-line text-xs text-muted">
                    Off
                  </div>
                )}
              </div>
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <h2 className="text-base font-semibold">
                    {fw.enabled ? <Link href={`/frameworks/${fw.code}`} className="hover:underline">{fw.name}</Link> : fw.name}
                  </h2>
                  <Badge tone="ink">{fw.region}</Badge>
                  {fw.review_status === "draft" && <Badge tone="warn">Content in review</Badge>}
                </div>
                <p className="mt-1 max-w-[75ch] text-sm leading-relaxed text-muted">{fw.description}</p>
                <p className="mt-2 text-xs text-muted">
                  {fw.requirement_count} requirements
                  {r ? `, ${r.met} met, ${r.partial} in progress` : ""}
                  {r?.not_applicable_requirements ? `, ${r.not_applicable_requirements} not applicable to you` : ""}
                </p>
              </div>
              <div className="flex shrink-0 gap-2">
                {fw.enabled && (
                  <Link href={`/frameworks/${fw.code}`} className="inline-flex h-9 items-center rounded-md border border-line px-4 text-sm font-medium hover:border-ink/40">
                    View requirements
                  </Link>
                )}
                {isAdmin && (
                  <Button variant={fw.enabled ? "ghost" : "primary"} busy={busy === fw.code} onClick={() => toggle(fw)}>
                    {fw.enabled ? "Turn off" : "Turn on"}
                  </Button>
                )}
              </div>
            </article>
          );
        })}
      </div>
    </>
  );
}
