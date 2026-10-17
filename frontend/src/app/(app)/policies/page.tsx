"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { useSession } from "@/components/session";
import { Badge, Button, ButtonLink, Drawer, Empty, LoadError, Loading, PageHeader, tbl, useToast } from "@/components/ui";
import { api, useApi } from "@/lib/api";
import { fmtDate } from "@/lib/format";
import type { Policy } from "@/lib/types";

interface Template {
  slug: string;
  title: string;
  control_codes: string[];
  added: boolean;
}

export default function PoliciesPage() {
  const { canWrite } = useSession();
  const toast = useToast();
  const { data, error, loading, reload } = useApi<Policy[]>("/policies");
  const templates = useApi<Template[]>("/policies/templates");
  const [picking, setPicking] = useState(false);
  const today = new Date().toISOString().slice(0, 10);
  useEffect(() => {
    if (new URLSearchParams(window.location.search).get("templates")) setPicking(true);
  }, []);

  async function addTemplate(slug: string) {
    try {
      await api("/policies/from-template", { method: "POST", json: { slug } });
      toast("Policy added as a draft");
      reload();
      templates.reload();
    } catch (e) {
      toast(e instanceof Error ? e.message : "Failed", "error");
    }
  }

  if (loading && !data) return <Loading />;
  if (error || !data) return <LoadError error={error ?? "Could not load"} retry={reload} />;

  return (
    <>
      <PageHeader
        title="Policies"
        description="Approving a policy records it as evidence on the controls it supports. Everyone in the workspace is asked to acknowledge approved policies."
        actions={
          canWrite && (
            <div className="flex gap-2">
              <Button variant="secondary" onClick={() => setPicking(true)}>Add from template</Button>
              <ButtonLink href="/policies/new" variant="primary">New policy</ButtonLink>
            </div>
          )
        }
      />
      <div className="rounded-lg border border-line bg-surface">
        {data.length ? (
          <div className={tbl.wrap}>
            <table className={tbl.table}>
              <thead>
                <tr>
                  <th className={tbl.th}>Policy</th>
                  <th className={tbl.th}>Status</th>
                  <th className={tbl.th}>Acknowledged</th>
                  <th className={tbl.th}>Next review</th>
                  <th className={tbl.th}>Owner</th>
                </tr>
              </thead>
              <tbody>
                {data.map((p) => (
                  <tr key={p.id} className={tbl.row}>
                    <td className={tbl.td}>
                      <Link href={`/policies/${p.id}`} className="font-medium hover:underline">{p.title}</Link>
                      <span className="ml-2 text-xs text-muted">v{p.version}</span>
                    </td>
                    <td className={tbl.td}>
                      <Badge tone={p.status === "approved" ? "pass" : "warn"}>{p.status === "approved" ? "Approved" : "Draft"}</Badge>
                    </td>
                    <td className={`${tbl.td} text-muted`}>{p.status === "approved" ? `${p.acknowledged_count} of ${p.member_count}` : "—"}</td>
                    <td className={`${tbl.td} whitespace-nowrap ${p.review_due && p.review_due < today ? "font-medium text-fail" : "text-muted"}`}>
                      {fmtDate(p.review_due)}
                    </td>
                    <td className={`${tbl.td} text-muted`}>{p.owner?.full_name ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <Empty
            title="No policies yet"
            action={
              canWrite && (
                <div className="flex justify-center gap-2">
                  <ButtonLink href="/policies/new?start=upload" variant="primary">Upload your policy</ButtonLink>
                  <Button variant="secondary" onClick={() => setPicking(true)}>Use a template</Button>
                </div>
              )
            }
          >
            Already have policies in Word or Google Docs? Upload or paste them. Otherwise start from our templates, written for Indian companies with DPDP and CERT-In in mind.
          </Empty>
        )}
      </div>

      <Drawer open={picking} onClose={() => setPicking(false)} title="Policy templates">
        <ul className="space-y-2">
          {(templates.data ?? []).map((t) => (
            <li key={t.slug} className="flex items-center justify-between gap-3 rounded-md border border-line px-3 py-2.5">
              <div>
                <p className="text-sm font-medium">{t.title}</p>
                <p className="text-xs text-muted">Supports {t.control_codes.join(", ")}</p>
              </div>
              {t.added ? <Badge tone="pass">Added</Badge> : <Button size="sm" variant="secondary" onClick={() => addTemplate(t.slug)}>Add</Button>}
            </li>
          ))}
        </ul>
      </Drawer>
    </>
  );
}
