"use client";

import { useParams } from "next/navigation";
import { useState } from "react";

import { Button, Field, FormError, Input, Loading, Textarea, cx } from "@/components/ui";
import { api, useApi } from "@/lib/api";

interface PortalInfo {
  org_name: string;
  contact_name: string;
  contact_email: string;
  request_types: Record<string, string>;
}

export default function PrivacyRequestPage() {
  const { slug } = useParams<{ slug: string }>();
  const { data, error, loading } = useApi<PortalInfo>(`/public/portal/${slug}`);
  const [type, setType] = useState("");
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [details, setDetails] = useState("");
  const [website, setWebsite] = useState("");
  const [sent, setSent] = useState<{ dev_verify_url?: string } | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setFormError(null);
    try {
      setSent(await api(`/public/portal/${slug}/requests`, { method: "POST", json: { request_type: type, full_name: fullName, email, details, website } }));
    } catch (err) {
      setFormError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setBusy(false);
    }
  }

  if (loading) return <Loading />;
  if (error || !data)
    return (
      <main className="mx-auto max-w-xl px-5 py-16">
        <h1 className="text-xl font-bold">This page isn&apos;t available</h1>
        <p className="mt-2 text-sm text-muted">Check the link, or contact the company directly.</p>
      </main>
    );

  return (
    <main className="mx-auto max-w-xl px-5 py-12">
      <p className="text-sm font-semibold text-muted">{data.org_name}</p>
      <h1 className="mt-1 text-[26px] font-bold leading-tight tracking-[-0.01em]">Make a request about your personal data</h1>
      <p className="mt-2 text-sm leading-relaxed text-muted">
        Under India&apos;s Digital Personal Data Protection Act, 2023 you can ask {data.org_name} for a summary of your data, correct or erase it,
        withdraw consent, nominate someone, or raise a grievance. We&apos;ll email you a link to confirm it&apos;s you.
      </p>

      {sent ? (
        <div className="mt-8 rounded-lg border border-line bg-surface p-6">
          <h2 className="font-semibold">Check your email</h2>
          <p className="mt-1 text-sm text-muted">
            We sent a confirmation link to {email}. Your request is submitted once you open it. The link works for 24 hours.
          </p>
          {sent.dev_verify_url && (
            <p className="mt-4 rounded-md bg-warn-50 px-3 py-2 text-xs text-warn">
              Development mode, email isn&apos;t configured: <a className="underline" href={sent.dev_verify_url}>open the confirmation link</a>
            </p>
          )}
        </div>
      ) : (
        <form onSubmit={submit} className="mt-8 space-y-5">
          <FormError error={formError} />
          <fieldset>
            <legend className="mb-2 text-[13px] font-medium">What would you like to do?</legend>
            <div className="space-y-2">
              {Object.entries(data.request_types).map(([k, label]) => (
                <label key={k} className={cx("flex cursor-pointer items-center gap-3 rounded-md border px-4 py-3 text-sm", type === k ? "border-ink bg-ink-50/60" : "border-line bg-surface hover:border-ink/40")}>
                  <input type="radio" name="type" value={k} checked={type === k} onChange={() => setType(k)} className="h-4 w-4 accent-ink" required />
                  {label}
                </label>
              ))}
            </div>
          </fieldset>
          <Field label="Your full name">{(id) => <Input id={id} required autoComplete="name" value={fullName} onChange={(e) => setFullName(e.target.value)} />}</Field>
          <Field label="Email you use with us" hint="We use this to find your data and to confirm the request is from you.">
            {(id) => <Input id={id} type="email" required autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} />}
          </Field>
          <Field label="Details (optional)" hint="For example, what needs correcting, or the account or phone number you used.">
            {(id) => <Textarea id={id} value={details} onChange={(e) => setDetails(e.target.value)} maxLength={5000} />}
          </Field>
          <div className="hidden" aria-hidden>
            <label>Website<input tabIndex={-1} autoComplete="off" value={website} onChange={(e) => setWebsite(e.target.value)} /></label>
          </div>
          <Button type="submit" busy={busy} disabled={!type} className="w-full">Send request</Button>
        </form>
      )}

      <footer className="mt-10 border-t border-line pt-4 text-xs leading-relaxed text-muted">
        Privacy contact for {data.org_name}: {data.contact_name}, <a className="underline" href={`mailto:${data.contact_email}`}>{data.contact_email}</a>.
        If you&apos;re not satisfied with our response, you can complain to the Data Protection Board of India.
      </footer>
    </main>
  );
}
