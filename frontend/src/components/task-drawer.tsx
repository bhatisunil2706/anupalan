"use client";

import { useState } from "react";

import { MemberSelect } from "./pickers";
import { Button, Drawer, Field, FormError, Input, Select, Textarea } from "./ui";
import { api } from "@/lib/api";

export function TaskDrawer({ open, controlId, onClose, onDone }: { open: boolean; controlId?: string; onClose: () => void; onDone: () => void }) {
  const [form, setForm] = useState({ title: "", description: "", assignee_id: "", due_date: "", priority: "medium" });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function save() {
    setBusy(true);
    setError(null);
    try {
      await api("/tasks", {
        method: "POST",
        json: { ...form, control_id: controlId ?? null, assignee_id: form.assignee_id || null, due_date: form.due_date || null },
      });
      setForm({ title: "", description: "", assignee_id: "", due_date: "", priority: "medium" });
      onDone();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Drawer open={open} onClose={onClose} title="Add task" footer={<><Button variant="ghost" onClick={onClose}>Cancel</Button><Button onClick={save} busy={busy} disabled={!form.title}>Add task</Button></>}>
      <FormError error={error} />
      <Field label="Title">{(id) => <Input id={id} value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} />}</Field>
      <Field label="Details">{(id) => <Textarea id={id} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />}</Field>
      <Field label="Assignee">{(id) => <MemberSelect id={id} value={form.assignee_id} onChange={(v) => setForm({ ...form, assignee_id: v })} />}</Field>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Due date">{(id) => <Input id={id} type="date" value={form.due_date} onChange={(e) => setForm({ ...form, due_date: e.target.value })} />}</Field>
        <Field label="Priority">
          {(id) => (
            <Select id={id} value={form.priority} onChange={(e) => setForm({ ...form, priority: e.target.value })}>
              <option value="low">Low</option><option value="medium">Medium</option><option value="high">High</option>
            </Select>
          )}
        </Field>
      </div>
    </Drawer>
  );
}
