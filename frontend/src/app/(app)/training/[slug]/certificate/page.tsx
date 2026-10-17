"use client";

import { ArrowLeft, Printer } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";

import { Button, LoadError, Loading } from "@/components/ui";
import { useApi } from "@/lib/api";
import { fmtDate } from "@/lib/format";

interface Cert { certificate_id: string; name: string; course: string; minutes: number; score: number; completed_at: string; valid_until: string; org_name: string }

export default function CertificatePage() {
  const { slug } = useParams<{ slug: string }>();
  const { data, error, loading } = useApi<Cert>(`/training/courses/${slug}/certificate`);
  if (loading && !data) return <Loading />;
  if (error || !data) return <LoadError error={error ?? "No certificate yet"} />;
  return (
    <div className="max-w-3xl">
      <div className="no-print mb-4 flex items-center justify-between">
        <Link href={`/training/${slug}`} className="inline-flex items-center gap-1 text-sm text-muted hover:text-text"><ArrowLeft size={14} /> Course</Link>
        <Button variant="secondary" onClick={() => window.print()}><Printer size={14} aria-hidden /> Print or save as PDF</Button>
      </div>
      <section id="certificate" className="rounded-lg border-[6px] border-double border-ink/70 bg-surface px-8 py-12 text-center sm:px-14">
        <p className="text-xs font-semibold uppercase tracking-[0.3em] text-muted">Certificate of completion</p>
        <p className="mt-8 text-sm text-muted">This certifies that</p>
        <p className="mt-2 text-3xl font-bold tracking-tight">{data.name}</p>
        <p className="mt-6 text-sm text-muted">has successfully completed</p>
        <p className="mt-2 text-xl font-semibold">{data.course}</p>
        <p className="mt-2 text-sm text-muted">with a score of {data.score}%</p>
        <div className="mx-auto mt-10 grid max-w-lg grid-cols-3 gap-4 border-t border-line pt-6 text-xs">
          <div><p className="text-muted">Completed</p><p className="mt-1 font-medium">{fmtDate(data.completed_at)}</p></div>
          <div><p className="text-muted">Valid until</p><p className="mt-1 font-medium">{fmtDate(data.valid_until)}</p></div>
          <div><p className="text-muted">Certificate ID</p><p className="mt-1 font-mono font-medium">{data.certificate_id}</p></div>
        </div>
        <p className="mt-8 text-sm font-medium">{data.org_name}</p>
        <p className="text-xs text-muted">Security awareness programme</p>
      </section>
    </div>
  );
}
