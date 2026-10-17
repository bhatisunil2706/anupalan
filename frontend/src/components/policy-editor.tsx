"use client";

import { TableKit } from "@tiptap/extension-table";
import { Placeholder } from "@tiptap/extensions";
import { EditorContent, useEditor, useEditorState, type Editor } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import {
  Bold,
  FileUp,
  Heading1,
  Heading2,
  Heading3,
  Italic,
  Link2,
  List,
  ListOrdered,
  Minus,
  Quote,
  Redo2,
  Table as TableIcon,
  Undo2,
} from "lucide-react";
import { marked } from "marked";
import TurndownService from "turndown";
import { tables } from "turndown-plugin-gfm";
import { useEffect, useRef, useState } from "react";

import { upload } from "@/lib/api";

// ------------------------------------------------------------------ Markdown <-> HTML
// Policies are stored as Markdown so exports, AI and the auditor pack stay simple. The editor works in HTML; the
// schema keeps only headings, paragraphs, lists, tables, quotes, links and basic marks, so pasted or imported HTML
// can't carry scripts or styles into a policy.

const turndown = new TurndownService({ headingStyle: "atx", bulletListMarker: "-", codeBlockStyle: "fenced", emDelimiter: "*" });
turndown.use(tables);
turndown.addRule("cellParagraph", {
  filter: (node) => node.nodeName === "P" && !!node.parentNode && ["TH", "TD"].includes(node.parentNode.nodeName),
  replacement: (content, node) => (node.previousSibling ? "<br>" : "") + content.replace(/\n+/g, " "),
});
turndown.addRule("tightListItem", {
  filter: "li",
  replacement: (content, node, options) => {
    const parent = node.parentNode as HTMLElement | null;
    let prefix = `${options.bulletListMarker} `;
    if (parent?.nodeName === "OL") {
      const start = Number(parent.getAttribute("start") || 1);
      prefix = `${start + Array.prototype.indexOf.call(parent.children, node)}. `;
    }
    const body = content.replace(/^\n+/, "").replace(/\n+$/, "\n").replace(/\n/gm, "\n" + " ".repeat(prefix.length));
    return prefix + body.trimEnd() + (node.nextSibling ? "\n" : "");
  },
});

export function mdToHtml(md: string): string {
  return marked.parse(md || "", { async: false, gfm: true }) as string;
}

/** Markdown tables need a header row; Google Docs and Word tables usually have none, so promote the first row. */
function normaliseTables(root: HTMLElement) {
  root.querySelectorAll("colgroup").forEach((c) => c.remove());
  root.querySelectorAll("table").forEach((table) => {
    table.removeAttribute("style");
    const first = table.querySelector("tr");
    if (!first || first.querySelector("th")) return;
    first.querySelectorAll("td").forEach((td) => {
      const th = table.ownerDocument.createElement("th");
      th.innerHTML = td.innerHTML;
      td.replaceWith(th);
    });
  });
}

export function htmlToMd(html: string): string {
  const doc = new DOMParser().parseFromString(html, "text/html"); // inert document: nothing runs
  normaliseTables(doc.body);
  return turndown.turndown(doc.body).replace(/\n{3,}/g, "\n\n").trim() + "\n";
}

const LOCAL_TYPES = /\.(md|markdown|txt|html?)$/i;
const SERVER_TYPES = /\.(docx|pdf)$/i;
export const IMPORT_ACCEPT = ".docx,.pdf,.md,.markdown,.txt,.html,.htm";

/** Read a document into editor HTML. Word and PDF are converted on the server; text formats are read here. */
export async function importDocument(file: File): Promise<{ html: string; title: string; warnings: string[] }> {
  const title = file.name.replace(/\.[^.]+$/, "").replace(/[_-]+/g, " ").trim();
  if (file.size > 10 * 1024 * 1024) throw new Error("Files up to 10 MB can be imported");
  if (SERVER_TYPES.test(file.name)) {
    const fd = new FormData();
    fd.set("file", file);
    return upload<{ html: string; title: string; warnings: string[] }>("/policies/import", fd);
  }
  if (!LOCAL_TYPES.test(file.name)) throw new Error("Use a .docx, .pdf, .md, .txt or .html file");
  const text = await file.text();
  if (/\.html?$/i.test(file.name)) {
    const doc = new DOMParser().parseFromString(text, "text/html"); // inert document: nothing runs
    return { html: doc.body.innerHTML, title: doc.title || title, warnings: [] };
  }
  if (/\.txt$/i.test(file.name)) {
    const esc = (s: string) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
    const html = text.split(/\n\s*\n/).map((b) => `<p>${esc(b.trim()).replace(/\n/g, "<br>")}</p>`).join("");
    return { html, title, warnings: [] };
  }
  return { html: mdToHtml(text), title, warnings: [] };
}

// ------------------------------------------------------------------ editor

export function PolicyEditor({
  value,
  onChange,
  onImported,
  autoFocus,
}: {
  value: string;
  onChange: (md: string) => void;
  onImported?: (info: { title: string; warnings: string[] }) => void;
  autoFocus?: boolean;
}) {
  const [mode, setMode] = useState<"visual" | "markdown">("visual");
  const [source, setSource] = useState(value);
  const [importing, setImporting] = useState(false);
  const [notice, setNotice] = useState<{ tone: "ok" | "error"; text: string } | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const lastEmitted = useRef(value);

  const editor = useEditor({
    immediatelyRender: false,
    injectCSS: false, // our CSP blocks injected <style> tags; the rules live in globals.css
    autofocus: autoFocus ? "end" : false,
    extensions: [
      StarterKit.configure({
        heading: { levels: [1, 2, 3] },
        code: false,
        codeBlock: false,
        link: { openOnClick: false, autolink: true, protocols: ["http", "https", "mailto"], defaultProtocol: "https" },
      }),
      TableKit.configure({ table: { resizable: false } }),
      Placeholder.configure({ placeholder: "Write your policy here, or paste it from Google Docs or Word…" }),
    ],
    content: mdToHtml(value),
    editorProps: {
      attributes: { class: "prose-policy policy-editor min-h-[50vh] px-5 py-4 focus:outline-none", "aria-label": "Policy text" },
    },
    onUpdate: ({ editor }) => {
      const md = htmlToMd(editor.getHTML());
      lastEmitted.current = md;
      onChange(md);
    },
  });

  // Load new content from outside (switching policy, importing) without fighting the user's typing.
  useEffect(() => {
    if (!editor || value === lastEmitted.current) return;
    lastEmitted.current = value;
    editor.commands.setContent(mdToHtml(value), { emitUpdate: false });
    setSource(value);
  }, [editor, value]);

  function switchMode(next: "visual" | "markdown") {
    if (next === mode) return;
    if (next === "markdown") setSource(lastEmitted.current);
    else if (editor) {
      editor.commands.setContent(mdToHtml(source), { emitUpdate: false });
    }
    setMode(next);
  }

  async function onFile(file: File | undefined) {
    if (!file) return;
    setImporting(true);
    setNotice(null);
    try {
      const res = await importDocument(file);
      if (editor) {
        editor.commands.setContent(res.html, { emitUpdate: false });
        const md = htmlToMd(editor.getHTML());
        lastEmitted.current = md;
        setSource(md);
        onChange(md);
      }
      setMode("visual");
      setNotice({ tone: "ok", text: `Imported ${file.name}. Check the formatting, then save.${res.warnings.length ? " " + res.warnings.join(" ") : ""}` });
      onImported?.({ title: res.title, warnings: res.warnings });
    } catch (e) {
      setNotice({ tone: "error", text: e instanceof Error ? e.message : "Import failed" });
    } finally {
      setImporting(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  return (
    <div className="rounded-lg border border-line bg-surface">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line px-2 py-1.5">
        {mode === "visual" && editor ? <Toolbar editor={editor} /> : <span className="px-2 text-xs text-muted">Markdown source</span>}
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => fileRef.current?.click()}
            disabled={importing}
            className="inline-flex h-8 items-center gap-1.5 rounded-md border border-line px-2.5 text-[13px] font-medium hover:border-ink/40 disabled:text-muted"
          >
            <FileUp size={14} aria-hidden /> {importing ? "Importing…" : "Import file"}
          </button>
          <input ref={fileRef} type="file" accept={IMPORT_ACCEPT} className="hidden" aria-label="Import a document" onChange={(e) => onFile(e.target.files?.[0])} />
          <div role="group" aria-label="Editing mode" className="inline-flex rounded-md border border-line p-0.5">
            {(["visual", "markdown"] as const).map((m) => (
              <button
                key={m}
                type="button"
                aria-pressed={mode === m}
                onClick={() => switchMode(m)}
                className={`rounded px-2.5 py-1 text-[13px] font-medium ${mode === m ? "bg-ink text-white" : "text-muted hover:text-text"}`}
              >
                {m === "visual" ? "Editor" : "Markdown"}
              </button>
            ))}
          </div>
        </div>
      </div>
      {notice && (
        <p role="status" className={`border-b border-line px-4 py-2 text-xs ${notice.tone === "error" ? "bg-fail-50 text-fail" : "bg-pass-50 text-pass"}`}>
          {notice.text}
        </p>
      )}
      <div className={mode === "visual" ? "" : "hidden"}>
        <EditorContent editor={editor} />
      </div>
      {mode === "markdown" && (
        <textarea
          value={source}
          onChange={(e) => {
            setSource(e.target.value);
            lastEmitted.current = e.target.value;
            onChange(e.target.value);
          }}
          aria-label="Policy text (Markdown)"
          className="block min-h-[50vh] w-full resize-y rounded-b-lg bg-surface px-5 py-4 font-mono text-[13px] leading-relaxed focus:outline-none"
        />
      )}
      <p className="border-t border-line px-4 py-2 text-xs text-muted">
        Paste straight from Google Docs or Word: headings, lists, bold and tables are kept. Import reads .docx, .pdf, .md, .txt and .html.
      </p>
    </div>
  );
}

function Toolbar({ editor }: { editor: Editor }) {
  const s = useEditorState({
    editor,
    selector: ({ editor: e }) => ({
      h1: e.isActive("heading", { level: 1 }),
      h2: e.isActive("heading", { level: 2 }),
      h3: e.isActive("heading", { level: 3 }),
      bold: e.isActive("bold"),
      italic: e.isActive("italic"),
      bullet: e.isActive("bulletList"),
      ordered: e.isActive("orderedList"),
      quote: e.isActive("blockquote"),
      link: e.isActive("link"),
      table: e.isActive("table"),
      undo: e.can().undo(),
      redo: e.can().redo(),
    }),
  });
  const c = () => editor.chain().focus();

  function setLink() {
    const prev = (editor.getAttributes("link").href as string | undefined) ?? "";
    const url = window.prompt("Link address (https://…). Leave empty to remove the link.", prev);
    if (url === null) return;
    if (!url.trim()) return void c().extendMarkRange("link").unsetLink().run();
    if (!/^(https?:\/\/|mailto:)/i.test(url.trim())) return void window.alert("Use a link starting with https:// or mailto:");
    c().extendMarkRange("link").setLink({ href: url.trim() }).run();
  }

  const B = ({ on, label, onClick, children, disabled }: { on?: boolean; label: string; onClick: () => void; children: React.ReactNode; disabled?: boolean }) => (
    <button
      type="button"
      title={label}
      aria-label={label}
      aria-pressed={on}
      disabled={disabled}
      onMouseDown={(e) => e.preventDefault()}
      onClick={onClick}
      className={`rounded p-1.5 ${on ? "bg-ink text-white" : "text-muted hover:bg-ink-50 hover:text-text"} disabled:opacity-40`}
    >
      {children}
    </button>
  );
  const Sep = () => <span className="mx-1 h-5 w-px bg-line" aria-hidden />;

  return (
    <div className="flex flex-wrap items-center gap-0.5" role="toolbar" aria-label="Formatting">
      <B label="Heading 1" on={s.h1} onClick={() => c().toggleHeading({ level: 1 }).run()}><Heading1 size={16} /></B>
      <B label="Heading 2" on={s.h2} onClick={() => c().toggleHeading({ level: 2 }).run()}><Heading2 size={16} /></B>
      <B label="Heading 3" on={s.h3} onClick={() => c().toggleHeading({ level: 3 }).run()}><Heading3 size={16} /></B>
      <Sep />
      <B label="Bold" on={s.bold} onClick={() => c().toggleBold().run()}><Bold size={16} /></B>
      <B label="Italic" on={s.italic} onClick={() => c().toggleItalic().run()}><Italic size={16} /></B>
      <B label="Link" on={s.link} onClick={setLink}><Link2 size={16} /></B>
      <Sep />
      <B label="Bulleted list" on={s.bullet} onClick={() => c().toggleBulletList().run()}><List size={16} /></B>
      <B label="Numbered list" on={s.ordered} onClick={() => c().toggleOrderedList().run()}><ListOrdered size={16} /></B>
      <B label="Quote" on={s.quote} onClick={() => c().toggleBlockquote().run()}><Quote size={16} /></B>
      <B label="Divider" onClick={() => c().setHorizontalRule().run()}><Minus size={16} /></B>
      <B
        label={s.table ? "Delete table" : "Insert table"}
        on={s.table}
        onClick={() => (s.table ? c().deleteTable().run() : c().insertTable({ rows: 3, cols: 3, withHeaderRow: true }).run())}
      >
        <TableIcon size={16} />
      </B>
      {s.table && (
        <>
          <button type="button" onClick={() => c().addRowAfter().run()} className="rounded px-1.5 py-1 text-xs text-muted hover:bg-ink-50">+ row</button>
          <button type="button" onClick={() => c().addColumnAfter().run()} className="rounded px-1.5 py-1 text-xs text-muted hover:bg-ink-50">+ column</button>
          <button type="button" onClick={() => c().deleteRow().run()} className="rounded px-1.5 py-1 text-xs text-muted hover:bg-ink-50">− row</button>
        </>
      )}
      <Sep />
      <B label="Undo" disabled={!s.undo} onClick={() => c().undo().run()}><Undo2 size={16} /></B>
      <B label="Redo" disabled={!s.redo} onClick={() => c().redo().run()}><Redo2 size={16} /></B>
    </div>
  );
}
