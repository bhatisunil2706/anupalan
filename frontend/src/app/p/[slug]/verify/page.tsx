"use client";

import { useParams, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useRef, useState } from "react";

import { Loading } from "@/components/ui";
import { api } from "@/lib/api";

interface Result {
  status: "confirmed" | "already_confirmed";
  reference: string | null;
  due_days?: number;
  contact_email?: string;
}

function Verify() {
  const { slug } = useParams<{ slug: string }>();
  const token = useSearchParams().get("token") ?? "";
  const [result, setResult] = useState<Result | null>(null);
  const [error, setError] = useState<string | null>(null);
  const started = useRef(false);

  useEffect(() => {
    if (started.current) return;
    started.current = true;
    api<Result>(`/public/portal/${slug}/verify`, { method: "POST", json: { token } })
      .then(setResult)
      .catch((e) => setError(e instanceof Error ? e.message : "This link didn't work"));
  }, [slug, token]);

  if (!result && !error) return <Loading label="Confirming your request" />;

  return (
    <main className="mx-auto max-w-xl px-5 py-16">
      {error ? (
        <>
          <h1 className="text-xl font-bold">We couldn&apos;t confirm this request</h1>
          <p className="mt-2 text-sm text-muted">{error}</p>
          <a href={`/p/${slug}`} className="mt-4 inline-block text-sm font-medium text-ink underline">Start a new request</a>
        </>
      ) : (
        <>
          <h1 className="text-xl font-bold">{result!.status === "confirmed" ? "Your request is confirmed" : "This request was already confirmed"}</h1>
          {result!.reference && <p className="mt-2 text-sm">Your reference number is <span className="font-semibold">{result!.reference}</span>.</p>}
          {result!.status === "confirmed" && (
            <p className="mt-2 text-sm text-muted">
              We&apos;ll respond within {result!.due_days} days. If you have questions, email{" "}
              <a className="underline" href={`mailto:${result!.contact_email}`}>{result!.contact_email}</a> and quote your reference.
            </p>
          )}
        </>
      )}
    </main>
  );
}

export default function VerifyPage() {
  return (
    <Suspense fallback={<Loading />}>
      <Verify />
    </Suspense>
  );
}
