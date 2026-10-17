"use client";

import { Download } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { ControlCodesPicker, MemberSelect } from "@/components/pickers";
import { PolicyEditor } from "@/components/policy-editor";
import { useSession } from "@/components/session";
import { Badge, Button, Field, Input, LoadError, Loading, Panel, useToast } from "@/components/ui";
import { api, useApi } from "@/lib/api";
import { fmtDate } from "@/lib/format";
import type { Policy } from "@/lib/types";

export default function PolicyPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const { canWrite, isAdmin } = useSession();
  const toast = useToast();
  const { data: p, error, loading, reload } = useApi<Policy>(`/policies/${id}`);
  const [editing, setEditing] = useState(false);
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [codes, setCodes] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (p && !editing) setCodes(p.control_codes);
  }, [p, editing]);

  // Warn before leaving with unsaved edits.
  const dirty = editing && !!p && (title !== p.title || body !== p.body_md);
  useEffect(() => {
    if (!dirty) return;
    const h = (e: BeforeUnloadEvent) => e.preventDefault();
    window.addEventListener("beforeunload", h);
    return () => window.removeEventListener("beforeunload", h);
  }, [dirty]);

  if (loading && !p) return <Loading />;
  if (error || !p) return <LoadError error={error ?? "Could not load"} retry={reload} />;

  async function run(fn: () => Promise<unknown>, msg: string, close = true) {
    setBusy(true);
    try {
      await fn();
      toast(msg);
      if (close) setEditing(false);
      reload();
    } catch (e) {
      toast(e instanceof Error ? e.message : "Failed", "error");
    } finally {
      setBusy(false);
    }
  }

  const patch = (json: Record<string, unknown>, msg: string, close = true) =>
    run(() => api(`/policies/${id}`, { method: "PATCH", json }), msg, close);

  function startEdit() {
    setTitle(p!.title);
    setBody(p!.body_md);
    setEditing(true);
  }

  function cancelEdit() {
    if (dirty && !confirm("Discard your changes?")) return;
    setEditing(false);
  }

  function downloadMd() {
    const blob = new Blob([p!.body_md], { type: "text/markdown" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `${p!.title.replace(/[^\w\- ]+/g, "").trim() || "policy"} v${p!.version}.md`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  }

  return (
    <>
      <nav className="mb-3 text-sm text-muted">
        <Link href="/policies" className="hover:underline">Policies</Link> / {p.title}
      </nav>
      <div className="grid grid-cols-1 gap-6 [&>*]:min-w-0 lg:grid-cols-[minmax(0,1fr)_300px]">
        {editing ? (
          <div className="space-y-3">
            <Input value={title} onChange={(e) => setTitle(e.target.value)} aria-label="Policy title" className="h-11 text-base font-semibold" />
            <PolicyEditor value={body} onChange={setBody} autoFocus />
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="text-xs text-muted">
                {p.status === "approved" ? `Saving creates draft version ${p.version + 1}. Version ${p.version} stays approved evidence until the new one is approved.` : "Changes are saved to this draft."}
              </p>
              <div className="flex gap-2">
                <Button variant="ghost" onClick={cancelEdit}>Cancel</Button>
                <Button busy={busy} disabled={!title.trim() || !dirty} onClick={() => patch({ title, body_md: body }, "Policy saved")}>
                  Save changes
                </Button>
              </div>
            </div>
          </div>
        ) : (
          <article className="rounded-lg border border-line bg-surface p-6 sm:p-8">
            <div className="prose-policy">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{p.body_md}</ReactMarkdown>
            </div>
          </article>
        )}

        <aside className="space-y-4">
          <Panel title="Status">
            <div className="space-y-3 text-sm">
              <div className="flex items-center justify-between">
                <Badge tone={p.status === "approved" ? "pass" : "warn"}>{p.status === "approved" ? "Approved" : "Draft"}</Badge>
                <span className="text-muted">Version {p.version}</span>
              </div>
              {p.approved_at && (
                <p className="text-muted">
                  Approved by {p.approved_by?.full_name} on {fmtDate(p.approved_at)}. Review due {fmtDate(p.review_due)}.
                </p>
              )}
              {p.status === "approved" && <p className="text-muted">{p.acknowledged_count} of {p.member_count} people have acknowledged this version.</p>}
              <div className="flex flex-col gap-2 pt-1">
                {p.status === "approved" && !p.acknowledged_by_me && (
                  <Button busy={busy} onClick={() => run(() => api(`/policies/${id}/acknowledge`, { method: "POST" }), "Thanks, acknowledgment recorded")}>
                    I have read this policy
                  </Button>
                )}
                {p.acknowledged_by_me && <p className="text-sm text-pass">You acknowledged this version.</p>}
                {isAdmin && p.status === "draft" && !editing && (
                  <Button busy={busy} onClick={() => run(() => api(`/policies/${id}/approve`, { method: "POST" }), "Policy approved")}>
                    Approve version {p.version}
                  </Button>
                )}
                {canWrite && !editing && <Button variant="secondary" onClick={startEdit}>Edit policy</Button>}
                {!editing && (
                  <Button variant="ghost" onClick={downloadMd}>
                    <Download size={14} aria-hidden /> Download (.md)
                  </Button>
                )}
              </div>
            </div>
          </Panel>
          <Panel title="Owner">
            <MemberSelect
              value={p.owner?.id ?? ""}
              disabled={!canWrite}
              emptyLabel="No owner"
              onChange={(v) => patch(v ? { owner_id: v } : { clear_owner: true }, "Owner updated", false)}
            />
          </Panel>
          <Panel title="Supports controls">
            <Field label="Controls" hint={canWrite ? "Approving the policy adds it as evidence on these controls." : undefined} className="[&>label]:sr-only">
              {() => (
                <ControlCodesPicker
                  value={codes}
                  disabled={!canWrite}
                  onChange={(next) => {
                    setCodes(next);
                    patch({ control_codes: next }, "Linked controls updated", false);
                  }}
                />
              )}
            </Field>
            {!canWrite && !codes.length && <p className="text-sm text-muted">None linked</p>}
          </Panel>
          {isAdmin && (
            <Button
              variant="danger"
              className="w-full"
              onClick={async () => {
                if (!confirm("Delete this policy? Its acknowledgments are deleted too.")) return;
                await api(`/policies/${id}`, { method: "DELETE" });
                router.push("/policies");
              }}
            >
              Delete policy
            </Button>
          )}
        </aside>
      </div>
    </>
  );
}
