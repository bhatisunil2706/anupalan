import "@fontsource-variable/public-sans";
import "./globals.css";

import type { Metadata } from "next";
import { connection } from "next/server";

import { ToastProvider } from "@/components/ui";

const APP_NAME = process.env.NEXT_PUBLIC_APP_NAME ?? "Pramaanly";

export const metadata: Metadata = {
  title: { default: APP_NAME, template: `%s · ${APP_NAME}` },
  description: "Compliance automation for DPDP, CERT-In, ISO 27001 and SOC 2",
};

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  await connection(); // render per request so every page gets a fresh CSP nonce
  return (
    <html lang="en-IN">
      <body>
        <ToastProvider>{children}</ToastProvider>
      </body>
    </html>
  );
}
