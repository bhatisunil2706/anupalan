"""Jira Cloud: two-way task sync. Platform tasks become Jira issues; closing the issue closes the task."""
import base64
import re
import uuid
from datetime import datetime, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.integrations.base import Connector, ConnectorError, Field, guarded_base_url

PRIORITY_ORDER = {"low": 0, "medium": 1, "high": 2}
MAX_PER_SYNC = 50


def _adf(text: str) -> dict:
    """Plain text as an Atlassian Document Format document."""
    paragraphs = [p for p in text.split("\n\n") if p.strip()][:50] or [" "]
    return {"type": "doc", "version": 1, "content": [
        {"type": "paragraph", "content": [{"type": "text", "text": p[:5000]}]} for p in paragraphs]}


class JiraConnector(Connector):
    provider = "jira"
    name = "Jira"
    category = "Work tracking"
    description = "Creates Jira issues for compliance tasks and closes the task when the issue is done."
    setup_help = (
        "Create an API token at id.atlassian.com (Security > API tokens) for a user who can create issues in the "
        "project. Enter your site, e.g. https://acme.atlassian.net, and the project key, e.g. SEC."
    )
    fields = [
        Field("site", "Jira site URL", help="For example https://acme.atlassian.net"),
        Field("email", "Atlassian account email"),
        Field("api_token", "API token", secret=True),
        Field("project_key", "Project key", help="For example SEC"),
        Field("issue_type", "Issue type", required=False, default="Task"),
        Field("min_priority", "Sync tasks with priority at least (low/medium/high)", required=False, default="medium"),
    ]
    tests = []
    syncs_tasks = True

    def __init__(self, config: dict, secrets: dict, client: httpx.Client | None = None):
        super().__init__(config, secrets)
        self.base = guarded_base_url(config.get("site", ""), allowed_suffixes=(".atlassian.net", ".jira.com"))
        self.project = (config.get("project_key") or "").strip().upper()
        if not re.fullmatch(r"[A-Z][A-Z0-9_]{1,19}", self.project):
            raise ConnectorError("Enter a valid project key, for example SEC")
        auth = base64.b64encode(f"{config.get('email', '').strip()}:{secrets.get('api_token', '')}".encode()).decode()
        self.headers = {"Authorization": f"Basic {auth}", "Accept": "application/json"}
        self.client = client or httpx.Client(timeout=30)

    def _req(self, method: str, path: str, **kw) -> httpx.Response:
        r = self.client.request(method, f"{self.base}{path}", headers=self.headers, **kw)
        if r.status_code == 401:
            raise ConnectorError("Jira rejected the email and API token.")
        return r

    def verify(self) -> None:
        r = self._req("GET", f"/rest/api/3/project/{self.project}")
        if r.status_code == 404:
            raise ConnectorError(f"Project {self.project} not found, or the user can't see it.")
        r.raise_for_status()

    def sync_tasks(self, db: Session, org_id: uuid.UUID) -> dict:
        from app.models import Task

        floor = PRIORITY_ORDER.get(str(self.config.get("min_priority", "medium")).lower(), 1)
        created = closed = 0
        # push new open tasks
        pending = db.scalars(select(Task).where(Task.org_id == org_id, Task.status != "done", Task.external_ref == "")
                             .order_by(Task.created_at)).all()
        for t in [t for t in pending if PRIORITY_ORDER.get(t.priority, 1) >= floor][:MAX_PER_SYNC]:
            fields = {"project": {"key": self.project}, "summary": t.title[:250],
                      "issuetype": {"name": self.config.get("issue_type") or "Task"},
                      "description": _adf(f"{t.description}\n\nCreated by Anupalan. Task: {t.id}"),
                      "labels": ["compliance", "anupalan"]}
            if t.due_date:
                fields["duedate"] = t.due_date.isoformat()
            r = self._req("POST", "/rest/api/3/issue", json={"fields": fields})
            if r.status_code >= 400:
                raise ConnectorError(f"Jira refused to create an issue ({r.status_code}). Check the issue type "
                                     "and that the user can create issues in the project.")
            key = r.json()["key"]
            t.external_ref, t.external_url = key, f"{self.base}/browse/{key}"
            created += 1
        db.flush()
        # pull status of linked issues
        linked = db.scalars(select(Task).where(Task.org_id == org_id, Task.status != "done",
                                               Task.external_ref.like(f"{self.project}-%"))).all()
        by_key = {t.external_ref: t for t in linked}
        keys = list(by_key)
        for i in range(0, len(keys), 100):
            chunk = keys[i:i + 100]
            r = self._req("POST", "/rest/api/3/search/jql", json={
                "jql": f"key in ({','.join(chunk)})", "fields": ["status"], "maxResults": 100})
            r.raise_for_status()
            for issue in r.json().get("issues", []):
                cat = (((issue.get("fields") or {}).get("status") or {}).get("statusCategory") or {}).get("key")
                t = by_key.get(issue.get("key"))
                if t and cat == "done":
                    t.status, t.completed_at = "done", datetime.now(timezone.utc)
                    t.description += f"\n\nClosed in Jira ({issue['key']})."
                    closed += 1
        return {"created": created, "closed": closed}
