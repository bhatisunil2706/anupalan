"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { Button, Checkbox, Field, FormError, Loading, Select, cx } from "@/components/ui";
import { api } from "@/lib/api";
import type { FrameworkCatalogItem, Me } from "@/lib/types";

const SECTORS = ["B2B SaaS", "IT services", "Fintech / payments", "NBFC / lending", "Insurance", "Healthtech", "Edtech", "E-commerce", "Other"];
const SIZES = ["1-50", "51-200", "201-500", "501-1000", "1000+"];
const STEPS = ["Company", "Frameworks", "What applies to you"];
// Suggested starting frameworks by sector; people can change the selection.
const SUGGEST: Record<string, string[]> = {
  "B2B SaaS": ["dpdp", "certin", "iso27001", "soc2"],
  "IT services": ["dpdp", "certin", "iso27001", "soc2"],
  "Fintech / payments": ["dpdp", "certin", "iso27001", "pci_dss"],
  "NBFC / lending": ["dpdp", "certin", "rbi_itgrc", "iso27001"],
  "Insurance": ["dpdp", "certin", "iso27001"],
  "Healthtech": ["dpdp", "certin", "iso27001", "hipaa"],
  "Edtech": ["dpdp", "certin", "iso27001"],
  "E-commerce": ["dpdp", "certin", "pci_dss"],
  "Other": ["dpdp", "certin"],
};

export default function OnboardingPage() {
  const router = useRouter();
  const [me, setMe] = useState<Me | null>(null);
  const [flags, setFlags] = useState<{ key: string; label: string; framework: string | null }[]>([]);
  const [frameworks, setFrameworks] = useState<FrameworkCatalogItem[]>([]);
  const [step, setStep] = useState(0);
  const [sector, setSector] = useState(SECTORS[0]);
  const [size, setSize] = useState(SIZES[1]);
  const [profile, setProfile] = useState<Record<string, boolean>>({});
  const [selected, setSelected] = useState<string[]>(["dpdp", "certin"]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const m = await api<Me>("/auth/me");
        if (m.onboarded) return router.replace("/dashboard");
        setMe(m);
        setFlags(await api("/org/profile-flags"));
        setFrameworks(await api("/frameworks"));
      } catch {
        router.replace("/login");
      }
    })();
  }, [router]);

  if (!me) return <Loading label="Preparing setup" />;
  const isAdmin = me.role === "owner" || me.role === "admin";
  const relevantFlags = flags.filter((f) => !f.framework || selected.includes(f.framework));

  async function finish() {
    setBusy(true);
    setError(null);
    try {
      await api("/org/onboarding", {
        method: "POST",
        json: { sector, employee_count: size, profile, framework_codes: selected },
      });
      router.replace("/dashboard");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Setup failed");
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto max-w-2xl px-5 py-12">
      <ol className="mb-8 flex gap-6 text-sm" aria-label="Setup steps">
        {STEPS.map((s, i) => (
          <li key={s} className={cx("flex items-center gap-2", i === step ? "font-semibold text-ink" : "text-muted")}>
            <span
              className={cx(
                "flex h-6 w-6 items-center justify-center rounded-full border text-xs",
                i <= step ? "border-ink bg-ink text-white" : "border-line",
              )}
            >
              {i + 1}
            </span>
            {s}
          </li>
        ))}
      </ol>

      {!isAdmin ? (
        <p className="text-sm text-muted">An admin of this workspace needs to finish setup before you can start.</p>
      ) : (
        <div className="rounded-lg border border-line bg-surface p-6">
          {step === 0 && (
            <div className="space-y-5">
              <div>
                <h1 className="text-xl font-bold">Tell us about your company</h1>
                <p className="mt-1 text-sm text-muted">We use this to suggest frameworks and size your controls.</p>
              </div>
              <Field label="Sector">
                {(id) => (
                  <Select id={id} value={sector} onChange={(e) => { setSector(e.target.value); setSelected(SUGGEST[e.target.value] ?? ["dpdp", "certin"]); }}>
                    {SECTORS.map((s) => <option key={s}>{s}</option>)}
                  </Select>
                )}
              </Field>
              <Field label="Number of employees">
                {(id) => (
                  <Select id={id} value={size} onChange={(e) => setSize(e.target.value)}>
                    {SIZES.map((s) => <option key={s}>{s}</option>)}
                  </Select>
                )}
              </Field>
            </div>
          )}

          {step === 2 && (
            <div className="space-y-5">
              <div>
                <h1 className="text-xl font-bold">Which of these apply to you?</h1>
                <p className="mt-1 text-sm text-muted">
                  These switch on extra obligations in the frameworks you picked. You can change them later in settings.
                </p>
              </div>
              {relevantFlags.length ? (
                <div className="space-y-6">
                  {frameworks.filter((fw) => relevantFlags.some((f) => f.framework === fw.code)).map((fw) => (
                    <fieldset key={fw.code} className="space-y-3">
                      <legend className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted">{fw.short_name}</legend>
                      {relevantFlags.filter((f) => f.framework === fw.code).map((f) => (
                        <Checkbox key={f.key} label={f.label} checked={!!profile[f.key]} onChange={(v) => setProfile({ ...profile, [f.key]: v })} />
                      ))}
                    </fieldset>
                  ))}
                </div>
              ) : (
                <p className="text-sm text-muted">Nothing extra to ask for the frameworks you picked.</p>
              )}
            </div>
          )}

          {step === 1 && (
            <div className="space-y-5">
              <div>
                <h1 className="text-xl font-bold">Choose your frameworks</h1>
                <p className="mt-1 text-sm text-muted">
                  Controls are shared, so work you do once counts towards every framework you pick.
                </p>
              </div>
              <div className="space-y-2">
                {frameworks.map((fw) => {
                  const on = selected.includes(fw.code);
                  return (
                    <label
                      key={fw.code}
                      className={cx(
                        "flex cursor-pointer items-start gap-3 rounded-md border px-4 py-3",
                        on ? "border-ink bg-ink-50/60" : "border-line hover:border-ink/40",
                      )}
                    >
                      <input
                        type="checkbox"
                        checked={on}
                        onChange={() => setSelected(on ? selected.filter((c) => c !== fw.code) : [...selected, fw.code])}
                        className="mt-1 h-4 w-4 accent-ink"
                      />
                      <span>
                        <span className="block text-sm font-semibold">
                          {fw.name} <span className="font-normal text-muted">({fw.region})</span>
                        </span>
                        <span className="mt-0.5 block text-xs leading-relaxed text-muted">{fw.description}</span>
                      </span>
                    </label>
                  );
                })}
              </div>
            </div>
          )}

          <div className="mt-4"><FormError error={error} /></div>
          <div className="mt-6 flex justify-between">
            <Button variant="ghost" onClick={() => setStep(step - 1)} disabled={step === 0}>
              Back
            </Button>
            {step < 2 ? (
              <Button onClick={() => setStep(step + 1)} disabled={step === 1 && !selected.length}>Continue</Button>
            ) : (
              <Button onClick={finish} busy={busy} disabled={!selected.length}>
                Set up workspace
              </Button>
            )}
          </div>
        </div>
      )}
      <p className="mt-4 text-xs text-muted">
        Setup creates your controls and draft policies. Nothing is shared outside your workspace.
      </p>
    </div>
  );
}
