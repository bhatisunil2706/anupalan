"use client";
// Static demo only: answers the app's /api calls from recorded sample data, so the real interface runs with no
// server. Any change (POST, PATCH, DELETE) is refused with a friendly message: nothing is ever saved.
import { useState } from "react";

const BASE = process.env.NEXT_PUBLIC_BASE_PATH ?? "";
const READ_ONLY = "This is a read-only demo with sample data, so changes aren't saved.";

function respond(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
}

if (typeof window !== "undefined" && !(window as unknown as { __demo?: boolean }).__demo) {
  (window as unknown as { __demo?: boolean }).__demo = true;
  const realFetch = window.fetch.bind(window);
  let index: Promise<Record<string, string>> | null = null;
  const loadIndex = () => (index ??= realFetch(`${BASE}/demo-data/index.json`).then((r) => r.json()));
  window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
    const raw = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
    const url = new URL(raw, window.location.href);
    if (url.origin !== window.location.origin || !url.pathname.startsWith("/api/")) return realFetch(input, init);
    const method = (init?.method ?? (input instanceof Request ? input.method : "GET")).toUpperCase();
    if (method !== "GET") return respond(403, { detail: READ_ONLY });
    const path = url.pathname.slice(4);
    const idx = await loadIndex();
    const params = new URLSearchParams(url.search);
    params.delete("v");
    const q = params.toString();
    const file = idx[path + url.search] ?? idx[q ? `${path}?${q}` : path] ?? idx[path];
    if (!file) return respond(404, { detail: "This part isn't available in the demo." });
    return realFetch(`${BASE}/demo-data/${file}`);
  };
}

export function DemoBanner() {
  const [open, setOpen] = useState(true);
  if (!open) return null;
  return (
    <div className="fixed bottom-5 left-1/2 z-30 flex max-w-[calc(100vw-2rem)] -translate-x-1/2 items-center gap-3 rounded-full bg-ink py-2 pl-4 pr-2 text-xs text-white shadow-lg">
      <span className="truncate">
        <strong>Live demo</strong> · sample data for a fictional company · changes aren&apos;t saved
      </span>
      <button className="shrink-0 rounded-full px-2 py-0.5 text-white/80 hover:bg-white/10 hover:text-white" onClick={() => setOpen(false)} aria-label="Hide demo notice">
        Hide
      </button>
    </div>
  );
}
