const IST = "Asia/Kolkata";

export function fmtDate(value: string | null | undefined): string {
  if (!value) return "—";
  const d = value.length === 10 ? new Date(`${value}T00:00:00`) : new Date(value);
  return d.toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });
}

export function fmtDateTime(value: string | null | undefined): string {
  if (!value) return "—";
  return new Date(value).toLocaleString("en-IN", {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: IST,
    timeZoneName: "short",
  });
}

/** "in 3h 20m", "2d overdue" style countdown. */
export function countdown(target: string | Date, now = new Date()): { text: string; overdue: boolean } {
  const ms = new Date(target).getTime() - now.getTime();
  const overdue = ms < 0;
  const abs = Math.abs(ms);
  const mins = Math.floor(abs / 60000);
  const days = Math.floor(mins / 1440);
  const hours = Math.floor((mins % 1440) / 60);
  const m = mins % 60;
  const span = days > 0 ? `${days}d ${hours}h` : hours > 0 ? `${hours}h ${m}m` : `${m}m`;
  return { text: overdue ? `${span} overdue` : `${span} left`, overdue };
}

export function bytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(0)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}

export function humanize(s: string): string {
  const t = s.replace(/_/g, " ");
  return t.charAt(0).toUpperCase() + t.slice(1);
}

export function splitList(s: string): string[] {
  return s.split(",").map((x) => x.trim()).filter(Boolean);
}

/** datetime-local input value (IST wall clock) -> ISO with +05:30 offset. */
export function localToIso(local: string): string {
  return `${local.length === 16 ? `${local}:00` : local}+05:30`;
}

export function isoToLocal(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(new Date(iso).getTime() + 330 * 60000);
  return d.toISOString().slice(0, 16);
}

export function nowLocal(): string {
  return isoToLocal(new Date().toISOString());
}
