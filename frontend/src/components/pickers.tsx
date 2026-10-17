"use client";

import { useId, useState } from "react";

import { useApi } from "@/lib/api";
import type { Control } from "@/lib/types";

import { useSession } from "./session";
import { Input, Select } from "./ui";

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

/** Pick control codes (for linking a policy to the controls it supports). */
export function ControlCodesPicker({
  value,
  onChange,
  disabled,
}: {
  value: string[];
  onChange: (codes: string[]) => void;
  disabled?: boolean;
}) {
  const { data } = useApi<Control[]>("/controls");
  const [q, setQ] = useState("");
  const listId = useId();
  const byCode = new Map((data ?? []).map((c) => [c.code, c]));
  const add = (raw: string) => {
    const code = raw.trim().split(/\s/)[0]?.toUpperCase();
    if (!code || !byCode.has(code) || value.includes(code)) return;
    onChange([...value, code].sort());
    setQ("");
  };
  return (
    <div className="space-y-2">
      {value.length > 0 && (
        <ul className="flex flex-wrap gap-1.5">
          {value.map((code) => (
            <li key={code} className="inline-flex items-center gap-1 rounded-md border border-line bg-paper py-0.5 pl-2 pr-1 text-xs">
              <span className="font-semibold">{code}</span>
              <span className="max-w-[16ch] truncate text-muted">{byCode.get(code)?.title}</span>
              {!disabled && (
                <button type="button" aria-label={`Remove ${code}`} onClick={() => onChange(value.filter((c) => c !== code))} className="rounded px-1 text-muted hover:bg-fail-50 hover:text-fail">
                  ×
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
      {!disabled && (
        <>
          <Input
            list={listId}
            value={q}
            placeholder="Add a control: type a code or title"
            aria-label="Add a control"
            onChange={(e) => {
              setQ(e.target.value);
              if (byCode.has(e.target.value.split(" ")[0])) add(e.target.value);
            }}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                add(q);
              }
            }}
          />
          <datalist id={listId}>
            {(data ?? []).filter((c) => !value.includes(c.code)).map((c) => (
              <option key={c.id} value={`${c.code} ${c.title}`} />
            ))}
          </datalist>
        </>
      )}
    </div>
  );
}
