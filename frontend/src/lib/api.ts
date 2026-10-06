"use client";

import { useCallback, useEffect, useRef, useState } from "react";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

function messageFrom(body: unknown, fallback: string): string {
  if (body && typeof body === "object" && "detail" in body) {
    const d = (body as { detail: unknown }).detail;
    if (typeof d === "string") return d;
    if (Array.isArray(d) && d.length) {
      const first = d[0] as { loc?: unknown[]; msg?: string };
      const field = first.loc?.slice(-1)[0];
      return field ? `${String(field).replace(/_/g, " ")}: ${first.msg}` : first.msg ?? fallback;
    }
  }
  return fallback;
}

/** Double-submit CSRF token: the server sets it in a readable cookie; we echo it in a header. */
function csrfToken(): string {
  if (typeof document === "undefined") return "";
  const m = document.cookie.match(/(?:^|;\s*)(?:__Host-)?csrf=([^;]+)/);
  return m ? decodeURIComponent(m[1]) : "";
}

const UNSAFE = new Set(["POST", "PUT", "PATCH", "DELETE"]);
export const MFA_SETUP_REQUIRED = "MFA_SETUP_REQUIRED";

function headersFor(method: string, json: unknown, headers?: HeadersInit): Headers {
  const h = new Headers(headers);
  if (json !== undefined) h.set("Content-Type", "application/json");
  if (UNSAFE.has(method)) {
    const token = csrfToken();
    if (token) h.set("X-CSRF-Token", token);
  }
  return h;
}

export async function api<T = unknown>(path: string, init: RequestInit & { json?: unknown } = {}): Promise<T> {
  const { json, headers, ...rest } = init;
  const method = (rest.method ?? "GET").toUpperCase();
  const res = await fetch(`/api${path}`, {
    credentials: "same-origin",
    ...rest,
    headers: headersFor(method, json, headers),
    body: json !== undefined ? JSON.stringify(json) : rest.body,
  });
  if (res.status === 204) return undefined as T;
  const body = await res.json().catch(() => null);
  if (!res.ok) {
    const message = messageFrom(body, `Request failed (${res.status})`);
    if (typeof window !== "undefined") {
      if (res.status === 401 && !path.startsWith("/auth/") && !path.startsWith("/public/")) {
        window.location.href = "/login";
      } else if (res.status === 403 && message.startsWith(MFA_SETUP_REQUIRED) && !window.location.pathname.startsWith("/account")) {
        window.location.href = "/account/security?setup=mfa";
      }
    }
    throw new ApiError(res.status, message.replace(`${MFA_SETUP_REQUIRED}: `, ""));
  }
  return body as T;
}

/** Download a file from the API (keeps the session cookie; never opens a new tab with credentials in the URL). */
export async function download(path: string, fallbackName: string): Promise<void> {
  const res = await fetch(`/api${path}`, { credentials: "same-origin" });
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new ApiError(res.status, messageFrom(body, `Download failed (${res.status})`));
  }
  const cd = res.headers.get("content-disposition") ?? "";
  const name = /filename="?([^";]+)"?/.exec(cd)?.[1] ?? fallbackName;
  const url = URL.createObjectURL(await res.blob());
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

/** Multipart upload with the CSRF header. */
export function upload<T = unknown>(path: string, form: FormData, method = "POST"): Promise<T> {
  return api<T>(path, { method, body: form });
}

/** Fetch data on mount; returns data, error, loading and a reload function. */
export function useApi<T>(path: string | null) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(path !== null);
  const current = useRef(path);
  current.current = path;

  const load = useCallback(async () => {
    if (!path) return;
    setLoading(true);
    try {
      const result = await api<T>(path);
      if (current.current === path) {
        setData(result);
        setError(null);
      }
    } catch (e) {
      if (current.current === path) setError(e instanceof Error ? e.message : "Something went wrong");
    } finally {
      if (current.current === path) setLoading(false);
    }
  }, [path]);

  useEffect(() => {
    load();
  }, [load]);

  return { data, error, loading, reload: load, setData };
}
