"use client";

import { useSession } from "./session";
import { Select } from "./ui";

/** Member picker. Value is a user id or "" for unassigned. */
export function MemberSelect({
  id,
  value,
  onChange,
  emptyLabel = "Unassigned",
  disabled,
}: {
  id?: string;
  value: string;
  onChange: (v: string) => void;
  emptyLabel?: string;
  disabled?: boolean;
}) {
  const { members } = useSession();
  return (
    <Select id={id} value={value} onChange={(e) => onChange(e.target.value)} disabled={disabled}>
      <option value="">{emptyLabel}</option>
      {members
        .filter((m) => m.role !== "auditor")
        .map((m) => (
          <option key={m.user.id} value={m.user.id}>
            {m.user.full_name}
          </option>
        ))}
    </Select>
  );
}
