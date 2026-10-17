"use client";

import { ShieldAlert } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import { Loading } from "@/components/ui";
import { api } from "@/lib/api";

interface Info { org_name: string; subject: string; sender: string; red_flags: string[]; enrolled: boolean }

/** Where a phishing-simulation link lands. The click is recorded by this page (not by the GET), so automated link
 * scanners in email gateways don't count as people clicking. */
export default function PhishLanding() {
  const { token } = useParams<{ token: string }>();
  const [info, setInfo] = useState<Info | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    api<Info>(`/public/phish/${token}`)
      .then((d) => {
        setInfo(d);
        api(`/public/phish/${token}/click`, { method: "POST" }).catch(() => {});
      })
      .catch(() => setFailed(true));
  }, [token]);

  if (failed) return <main className="mx-auto max-w-xl px-4 py-16 text-sm text-muted">This link isn&apos;t valid.</main>;
  if (!info) return <Loading />;
  return (
    <div className="min-h-screen bg-paper">
      <main className="mx-auto max-w-2xl px-4 py-12">
        <div className="rounded-lg border border-warn/40 bg-surface p-6 sm:p-8">
          <ShieldAlert size={32} className="text-warn" aria-hidden />
          <h1 className="mt-3 text-2xl font-bold tracking-tight">This was a phishing simulation</h1>
          <p className="mt-2 text-[15px] leading-relaxed">
            Don&apos;t worry: nothing happened and no information was collected. {info.org_name} runs these tests so everyone
            gets better at spotting real attacks. Clicking is common; what matters is learning the signs.
          </p>
          <div className="mt-6 rounded-md border border-line bg-paper p-4 text-sm">
            <p className="text-xs uppercase tracking-wide text-muted">The email you clicked</p>
            <p className="mt-1"><span className="text-muted">From:</span> {info.sender}</p>
            <p><span className="text-muted">Subject:</span> {info.subject}</p>
          </div>
          <h2 className="mt-6 font-semibold">What should have made you pause</h2>
          <ul className="mt-2 list-disc space-y-1.5 pl-5 text-[15px]">{info.red_flags.map((f) => <li key={f}>{f}</li>)}</ul>
          <h2 className="mt-6 font-semibold">Next time</h2>
          <ol className="mt-2 list-decimal space-y-1.5 pl-5 text-[15px]">
            <li>Pause when a message is urgent, unexpected or asks you to sign in, pay or share something.</li>
            <li>Check the sender&apos;s real address and hover over links before clicking.</li>
            <li>Verify through a channel you already trust, and report suspicious messages to the security team.</li>
          </ol>
          {info.enrolled && (
            <p className="mt-6 rounded-md bg-ink-50 px-4 py-3 text-sm">
              A short course, &quot;Spotting phishing and social engineering&quot;, has been added to your training.{" "}
              <Link href="/training/phishing" className="font-medium text-ink underline">Take it now</Link> (about 10 minutes).
            </p>
          )}
        </div>
      </main>
    </div>
  );
}
