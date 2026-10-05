"use client";

import Link from "next/link";
import { useState } from "react";

import { useSession } from "@/components/session";
import { TaskDrawer } from "@/components/task-drawer";
import { Badge, Button, Empty, LoadError, Loading, PageHeader, Tabs, tbl, useToast } from "@/components/ui";
import { api, useApi } from "@/lib/api";
import { fmtDate } from "@/lib/format";
import type { Task } from "@/lib/types";

type View = "active" | "mine" | "done";

export default function TasksPage() {
  const { canWrite } = useSession();
  const toast = useToast();
  const [view, setView] = useState<View>("active");
  const path = view === "mine" ? "/tasks?status_filter=active&mine=true" : `/tasks?status_filter=${view}`;
  const { data, error, loading, reload } = useApi<Task[]>(path);
  const [adding, setAdding] = useState(false);
  const today = new Date().toISOString().slice(0, 10);

  async function setStatus(t: Task, status: Task["status"]) {
    try {
      await api(`/tasks/${t.id}`, { method: "PATCH", json: { status } });
      toast(status === "done" ? "Task completed" : "Task reopened");
      reload();
    } catch (e) {
      toast(e instanceof Error ? e.message : "Failed", "error");
    }
  }

  return (
    <>
      <PageHeader
        title="Tasks"
        description="Work to close gaps. Failing integration checks create tasks automatically and close them when the check passes."
        actions={canWrite && <Button onClick={() => setAdding(true)}>Add task</Button>}
      />
      <Tabs<View>
        tabs={[{ value: "active", label: "Open" }, { value: "mine", label: "Assigned to me" }, { value: "done", label: "Done" }]}
        value={view}
        onChange={setView}
      />
      {loading && !data ? (
        <Loading />
      ) : error || !data ? (
        <LoadError error={error ?? "Could not load"} retry={reload} />
      ) : (
        <div className="rounded-lg border border-line bg-surface">
          {data.length ? (
            <div className={tbl.wrap}>
              <table className={tbl.table}>
                <thead>
                  <tr>
                    <th className={`${tbl.th} w-10`}><span className="sr-only">Done</span></th>
                    <th className={tbl.th}>Task</th>
                    <th className={tbl.th}>Control</th>
                    <th className={tbl.th}>Assignee</th>
                    <th className={tbl.th}>Due</th>
                    <th className={tbl.th}>Priority</th>
                  </tr>
                </thead>
                <tbody>
                  {data.map((t) => {
                    const overdue = t.status !== "done" && t.due_date && t.due_date < today;
                    return (
                      <tr key={t.id} className={tbl.row}>
                        <td className={tbl.td}>
                          <input
                            type="checkbox"
                            aria-label={`Mark ${t.title} ${t.status === "done" ? "not done" : "done"}`}
                            checked={t.status === "done"}
                            disabled={!canWrite}
                            onChange={() => setStatus(t, t.status === "done" ? "open" : "done")}
                            className="h-4 w-4 accent-ink"
                          />
                        </td>
                        <td className={tbl.td}>
                          <p className={t.status === "done" ? "text-muted line-through" : "font-medium"}>{t.title}</p>
                          {t.description && <p className="mt-0.5 line-clamp-3 max-w-[60ch] whitespace-pre-line text-xs text-muted">{t.description}</p>}
                          {t.source.startsWith("test:") && <p className="mt-1 text-xs text-prog">From an automated check</p>}
                        </td>
                        <td className={tbl.td}>
                          {t.control_id ? <Link href={`/controls/${t.control_id}`} className="text-xs font-semibold text-ink hover:underline">{t.control_code}</Link> : "—"}
                        </td>
                        <td className={`${tbl.td} whitespace-nowrap text-muted`}>{t.assignee?.full_name ?? "—"}</td>
                        <td className={`${tbl.td} whitespace-nowrap ${overdue ? "font-medium text-fail" : "text-muted"}`}>
                          {fmtDate(t.due_date)}
                        </td>
                        <td className={tbl.td}>
                          <Badge tone={t.priority === "high" ? "fail" : t.priority === "medium" ? "warn" : "idle"}>{t.priority}</Badge>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          ) : (
            <Empty title={view === "done" ? "No completed tasks yet" : "No open tasks"}>
              {view !== "done" && "Tasks appear here when you add them or when an automated check fails."}
            </Empty>
          )}
        </div>
      )}
      <TaskDrawer open={adding} onClose={() => setAdding(false)} onDone={() => { setAdding(false); toast("Task added"); reload(); }} />
    </>
  );
}
