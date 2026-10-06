"use client";

import {
  AlertOctagon,
  BadgeCheck,
  FileSearch,
  GraduationCap,
  Lock,
  Sparkles,
  CheckSquare,
  ClipboardCheck,
  Database,
  ScanSearch,
  UserCheck,
  Users,
  FileText,
  Gauge,
  Inbox,
  LayoutGrid,
  LogOut,
  Menu,
  Plug,
  Settings,
  ShieldAlert,
  Truck,
  X,
} from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useCallback, useEffect, useState, type ReactNode } from "react";

import { api } from "@/lib/api";
import type { Me, Member } from "@/lib/types";

import { SessionProvider } from "./session";
import { Loading, cx } from "./ui";

const APP_NAME = process.env.NEXT_PUBLIC_APP_NAME ?? "Anupalan";

const NAV: { group: string; items: { href: string; label: string; icon: typeof Gauge }[] }[] = [
  {
    group: "Overview",
    items: [
      { href: "/dashboard", label: "Dashboard", icon: Gauge },
      { href: "/tasks", label: "Tasks", icon: CheckSquare },
    ],
  },
  {
    group: "Compliance",
    items: [
      { href: "/frameworks", label: "Frameworks", icon: LayoutGrid },
      { href: "/controls", label: "Controls", icon: ClipboardCheck },
      { href: "/policies", label: "Policies", icon: FileText },
      { href: "/audit", label: "Audit requests", icon: FileSearch },
      { href: "/training", label: "Training", icon: GraduationCap },
      { href: "/assistant", label: "AI assistant", icon: Sparkles },
    ],
  },
  {
    group: "Automation",
    items: [
      { href: "/integrations", label: "Integrations", icon: Plug },
      { href: "/people", label: "People & accounts", icon: Users },
      { href: "/access-reviews", label: "Access reviews", icon: UserCheck },
    ],
  },
  {
    group: "DPDP",
    items: [
      { href: "/dpdp/inventory", label: "Data inventory", icon: Database },
      { href: "/dpdp/consent", label: "Consent records", icon: BadgeCheck },
      { href: "/dpdp/discovery", label: "Data discovery", icon: ScanSearch },
      { href: "/dpdp/requests", label: "Rights requests", icon: Inbox },
      { href: "/incidents", label: "Incidents", icon: AlertOctagon },
    ],
  },
  {
    group: "Risk",
    items: [
      { href: "/risks", label: "Risk register", icon: ShieldAlert },
      { href: "/vendors", label: "Vendors", icon: Truck },
    ],
  },
];

export function AppShell({ children }: { children: ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const [me, setMe] = useState<Me | null>(null);
  const [members, setMembers] = useState<Member[]>([]);
  const [navOpen, setNavOpen] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const m = await api<Me>("/auth/me");
      if (!m.org_id) return router.replace("/login");
      if (m.mfa_setup_required && !window.location.pathname.startsWith("/account")) {
        return router.replace("/account/security?setup=mfa");
      }
      if (!m.onboarded && !m.mfa_setup_required) return router.replace("/onboarding");
      setMe(m);
      if (!m.mfa_setup_required) setMembers(await api<Member[]>("/org/members").catch(() => []));
    } catch {
      router.replace("/login");
    }
  }, [router]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  useEffect(() => setNavOpen(false), [pathname]);

  if (!me) return <Loading label="Opening your workspace" />;

  const orgName = me.memberships.find((m) => m.org_id === me.org_id)?.org_name ?? "";
  const canWrite = me.role !== "auditor";
  const isAdmin = me.role === "owner" || me.role === "admin";

  async function switchOrg(orgId: string) {
    await api("/auth/switch-org", { method: "POST", json: { org_id: orgId } });
    window.location.href = "/dashboard";
  }

  async function logout() {
    await api("/auth/logout", { method: "POST" });
    window.location.href = "/login";
  }

  const sidebar = (
    <nav className="flex h-full flex-col bg-ink text-white/80" aria-label="Main">
      <div className="px-5 pb-4 pt-5">
        <Link href="/dashboard" className="text-[17px] font-bold tracking-[-0.01em] text-white">
          {APP_NAME}
        </Link>
        {me.memberships.length > 1 ? (
          <select
            aria-label="Organisation"
            value={me.org_id ?? ""}
            onChange={(e) => switchOrg(e.target.value)}
            className="mt-2 w-full rounded bg-white/10 px-2 py-1.5 text-sm text-white"
          >
            {me.memberships.map((m) => (
              <option key={m.org_id} value={m.org_id} className="text-text">
                {m.org_name}
              </option>
            ))}
          </select>
        ) : (
          <p className="mt-1 truncate text-sm text-white/60">{orgName}</p>
        )}
      </div>
      <div className="flex-1 space-y-5 overflow-y-auto px-3 pb-4">
        {NAV.map((g) => (
          <div key={g.group}>
            <p className="px-2 pb-1 text-xs font-medium text-white/45">{g.group}</p>
            <ul>
              {g.items.map(({ href, label, icon: Icon }) => {
                const active = pathname === href || pathname.startsWith(`${href}/`);
                return (
                  <li key={href}>
                    <Link
                      href={href}
                      aria-current={active ? "page" : undefined}
                      className={cx(
                        "flex items-center gap-2.5 rounded-md px-2 py-1.5 text-sm",
                        active ? "bg-white/12 font-medium text-white" : "hover:bg-white/8 hover:text-white",
                      )}
                    >
                      <Icon size={16} strokeWidth={1.8} aria-hidden />
                      {label}
                    </Link>
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </div>
      <div className="border-t border-white/10 px-3 py-3">
        <Link
          href="/account/security"
          className={cx(
            "flex items-center gap-2.5 rounded-md px-2 py-1.5 text-sm hover:bg-white/8 hover:text-white",
            pathname.startsWith("/account") && "bg-white/12 text-white",
          )}
        >
          <Lock size={16} strokeWidth={1.8} aria-hidden />
          Account security
          {!me.mfa_enabled && me.auth_method !== "sso" && <span className="ml-auto h-2 w-2 rounded-full bg-warn" aria-label="MFA off" />}
        </Link>
        <Link
          href="/settings"
          className={cx(
            "flex items-center gap-2.5 rounded-md px-2 py-1.5 text-sm hover:bg-white/8 hover:text-white",
            pathname.startsWith("/settings") && "bg-white/12 text-white",
          )}
        >
          <Settings size={16} strokeWidth={1.8} aria-hidden />
          Settings
        </Link>
        <div className="mt-2 flex items-center justify-between gap-2 px-2">
          <div className="min-w-0">
            <p className="truncate text-sm text-white">{me.user.full_name}</p>
            <p className="truncate text-xs capitalize text-white/50">{me.role}</p>
          </div>
          <button onClick={logout} className="rounded p-1.5 hover:bg-white/10" aria-label="Sign out" title="Sign out">
            <LogOut size={16} />
          </button>
        </div>
      </div>
    </nav>
  );

  return (
    <SessionProvider value={{ me, members, canWrite, isAdmin, refresh }}>
      <div className="min-h-screen lg:pl-60">
        <aside className="fixed inset-y-0 left-0 hidden w-60 lg:block">{sidebar}</aside>
        {navOpen && (
          <div className="fixed inset-0 z-40 lg:hidden">
            <div className="absolute inset-0 bg-text/40" onClick={() => setNavOpen(false)} aria-hidden />
            <aside className="absolute inset-y-0 left-0 w-64">{sidebar}</aside>
            <button
              onClick={() => setNavOpen(false)}
              className="absolute left-[268px] top-4 rounded bg-surface p-1.5"
              aria-label="Close menu"
            >
              <X size={18} />
            </button>
          </div>
        )}
        <div className="sticky top-0 z-30 flex items-center gap-3 border-b border-line bg-surface px-4 py-3 lg:hidden">
          <button onClick={() => setNavOpen(true)} aria-label="Open menu" className="rounded p-1 hover:bg-ink-50">
            <Menu size={20} />
          </button>
          <span className="font-bold text-ink">{APP_NAME}</span>
        </div>
        <Banners me={me} />
        <main className="mx-auto max-w-[1200px] px-4 py-6 sm:px-6 lg:px-8 lg:py-8">{children}</main>
      </div>
    </SessionProvider>
  );
}

function Banners({ me }: { me: Me }) {
  const [sent, setSent] = useState(false);
  const items: ReactNode[] = [];
  if (me.mfa_setup_required) {
    items.push(<span key="mfa">Your organisation requires two-step verification. Set it up to continue.</span>);
  }
  if (!me.email_verified) {
    items.push(
      <span key="verify">
        Confirm your email address to invite teammates and receive alerts.{" "}
        <button
          className="font-medium underline"
          disabled={sent}
          onClick={async () => {
            await api("/auth/email/resend", { method: "POST" }).catch(() => undefined);
            setSent(true);
          }}
        >
          {sent ? "Link sent" : "Resend the link"}
        </button>
      </span>,
    );
  }
  if (me.access_expires_at) {
    items.push(
      <span key="expiry">
        Auditor access ends on {new Date(me.access_expires_at).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" })}.
      </span>,
    );
  }
  if (!items.length) return null;
  return (
    <div className="border-b border-warn/25 bg-warn-50 px-4 py-2 text-sm text-warn sm:px-6 lg:px-8" role="status">
      <div className="mx-auto flex max-w-[1200px] flex-col gap-1">{items}</div>
    </div>
  );
}
