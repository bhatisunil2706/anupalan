"use client";

import { ClipboardPaste, FilePlus2, FileUp, PenLine } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { ControlCodesPicker, MemberSelect } from "@/components/pickers";
import { IMPORT_ACCEPT, PolicyEditor, htmlToMd, importDocument } from "@/components/policy-editor";
import { useSession } from "@/components/session";
import { Button, Field, FormError, Input, Panel } from "@/components/ui";
import { api } from "@/lib/api";
import type { Policy } from "@/lib/types";

type Start = "write" | "paste" | "upload";

export default function NewPolicyPage() {
  const router = useRouter();
  const { me, canWrite } = useSession();
  const [start, setStart] = useState<Start | null>(null);
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [owner, setOwner] = useState(me.user.id);
  const [codes, setCodes] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [importing, setImporting] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const how = new URLSearchParams(window.location.search).get("start");
    if (how === "write" || how === "paste" || how === "upload") setStart(how);
  }, []);

  async function onFile(file: File | undefined) {
    if (!file) return;
    setImporting(true);
    setError(null);
    try {
      const res = await importDocument(file);
      setBody(htmlToMd(res.html));
      if (!title) setTitle(res.title);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Import failed");
    } finally {
      setImporting(false);
    }
  }

  async function save() {
    if (!title.trim()) return setError("Give the policy a title");
    if (!body.trim()) return setError("The policy is empty");
    setBusy(true);
    setError(null);
    try {
      const p = await api<Policy>("/policies", { method: "POST", json: { title, body_md: body, control_codes: codes, owner_id: owner || null } });
      router.push(`/policies/${p.id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't save");
      setBusy(false);
    }
  }

  if (!canWrite) return <p className="text-sm text-muted">You don't have permission to create policies.</p>;

  const showEditor = start === "write" || start === "paste" || (start === "upload" && body);

  return (
    <>
      <nav className="mb-3 text-sm text-muted">
        <Link href="/policies" className="hover:underline">Policies</Link> / New policy
      </nav>
      <h1 className="mb-1 text-[22px] font-bold tracking-[-0.01em]">New policy</h1>
      <p className="mb-6 max-w-[70ch] text-sm text-muted">
        Bring the policy you already have, or write a new one. It's saved as a draft; an admin approves it, and then everyone is asked to read and acknowledge it.
      </p>

      {!showEditor && (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <StartCard icon={FileUp} title="Upload a document" body="Word (.docx), PDF, Markdown, text or HTML. We convert it so you can edit it here." onClick={() => { setStart("upload"); fileRef.current?.click(); }} busy={importing} />
          <StartCard icon={ClipboardPaste} title="Paste from Google Docs or Word" body="Copy the whole document and paste. Headings, lists and tables are kept." onClick={() => setStart("paste")} />
          <StartCard icon={PenLine} title="Write from scratch" body="A simple editor with headings, lists and tables. No formatting codes needed." onClick={() => setStart("write")} />
          <StartCard icon={FilePlus2} title="Start from a template" body="Ready-made policies for Indian companies that reference DPDP and CERT-In." href="/policies?templates=1" />
        </div>
      )}
      <input ref={fileRef} type="file" accept={IMPORT_ACCEPT} className="hidden" aria-label="Upload a policy document" onChange={(e) => onFile(e.target.files?.[0])} />
      {!showEditor && <div className="mt-4"><FormError error={error} /></div>}
      {start === "upload" && !body && !importing && (
        <p className="mt-3 text-sm text-muted">
          No file chosen. <button type="button" onClick={() => fileRef.current?.click()} className="font-medium text-ink underline">Choose a file</button>
        </p>
      )}

      {showEditor && (
        <div className="grid grid-cols-1 gap-6 [&>*]:min-w-0 lg:grid-cols-[minmax(0,1fr)_300px]">
          <div className="space-y-3">
            <Input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Policy title, e.g. Information Security Policy" aria-label="Policy title" className="h-11 text-base font-semibold" />
            {start === "paste" && !body && (
              <p className="rounded-md border border-prog/30 bg-prog-50 px-3 py-2 text-sm text-prog">
                Open your document, select all (Ctrl/Cmd + A), copy, then click in the box below and paste (Ctrl/Cmd + V).
              </p>
            )}
            <PolicyEditor value={body} onChange={setBody} autoFocus={start !== "upload"} onImported={(i) => !title && setTitle(i.title)} />
          </div>
          <aside className="space-y-4">
            <Panel title="Details">
              <div className="space-y-4">
                <Field label="Owner" hint="Responsible for keeping it up to date.">
                  {(id) => <MemberSelect id={id} value={owner} onChange={setOwner} emptyLabel="No owner" />}
                </Field>
                <Field label="Supports controls" hint="Approving the policy adds it as evidence on these controls.">
                  {() => <ControlCodesPicker value={codes} onChange={setCodes} />}
                </Field>
              </div>
            </Panel>
            <FormError error={error} />
            <div className="flex gap-2">
              <Button variant="ghost" onClick={() => router.push("/policies")}>Cancel</Button>
              <Button className="flex-1" busy={busy} onClick={save}>Save as draft</Button>
            </div>
          </aside>
        </div>
      )}
    </>
  );
}

function StartCard({
  icon: Icon,
  title,
  body,
  onClick,
  href,
  busy,
}: {
  icon: typeof FileUp;
  title: string;
  body: string;
  onClick?: () => void;
  href?: string;
  busy?: boolean;
}) {
  const inner = (
    <>
      <Icon size={20} className="text-ink" aria-hidden />
      <p className="mt-3 font-semibold">{busy ? "Converting…" : title}</p>
      <p className="mt-1 text-sm leading-relaxed text-muted">{body}</p>
    </>
  );
  const cls = "block rounded-lg border border-line bg-surface p-4 text-left transition-colors hover:border-ink/40 disabled:opacity-60";
  return href ? (
    <Link href={href} className={cls}>{inner}</Link>
  ) : (
    <button type="button" onClick={onClick} disabled={busy} className={cls}>{inner}</button>
  );
}
