import "@fontsource-variable/public-sans";
import "./globals.css";

import type { Metadata } from "next";

import { ToastProvider } from "@/components/ui";
import { DemoBanner } from "@/demo/shim";

export const metadata: Metadata = {
  title: { default: "Pramaanly demo", template: "%s · Pramaanly demo" },
  description: "Live demo of Pramaanly, compliance automation for DPDP, CERT-In, RBI, ISO 27001 and SOC 2, with sample data",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en-IN">
      <body>
        <DemoBanner />
        <ToastProvider>{children}</ToastProvider>
      </body>
    </html>
  );
}
