import type { ReactNode } from "react";

const APP_NAME = process.env.NEXT_PUBLIC_APP_NAME ?? "Anupalan";

export function AuthFrame({ title, subtitle, children }: { title: string; subtitle?: ReactNode; children: ReactNode }) {
  return (
    <div className="grid min-h-screen lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]">
      <aside className="hidden flex-col justify-between bg-ink p-10 text-white lg:flex">
        <p className="text-lg font-bold">{APP_NAME}</p>
        <div className="max-w-sm">
          <p className="text-[26px] font-bold leading-tight tracking-[-0.01em]">
            One set of controls for DPDP, CERT-In, ISO 27001 and SOC 2.
          </p>
          <p className="mt-4 text-sm leading-relaxed text-white/65">
            Track every obligation, collect evidence automatically and keep regulator deadlines in view, from the
            6-hour CERT-In clock to the DPDP 72-hour breach report.
          </p>
        </div>
        <p className="text-xs text-white/40">Data hosted in India</p>
      </aside>
      <main className="flex items-center justify-center px-5 py-12">
        <div className="w-full max-w-sm">
          <p className="mb-8 text-lg font-bold text-ink lg:hidden">{APP_NAME}</p>
          <h1 className="text-[22px] font-bold tracking-[-0.01em]">{title}</h1>
          {subtitle && <p className="mt-1 text-sm text-muted">{subtitle}</p>}
          <div className="mt-6">{children}</div>
        </div>
      </main>
    </div>
  );
}
