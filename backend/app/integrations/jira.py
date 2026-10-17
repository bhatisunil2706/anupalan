"""Jira Cloud: two-way task and risk sync.

Tasks: platform tasks become Jira issues; closing the issue closes the task.
Risks: every new risk gets a Jira issue (summary, score, treatment plan); the issue's status flows back (done = treated,
reopened = open), and issues matching a JQL filter (e.g. labels = risk) are imported into the risk register.
"""
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
    description = ("Creates Jira issues for compliance tasks and risks, pulls their status back, and imports risks "
                   "logged in Jira.")
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
        Field("sync_risks", "Create a Jira issue for every new risk (yes/no)", required=False, default="yes"),
        Field("risk_issue_type", "Issue type for risks", required=False, default="Task",
              help="Use 'Risk' if your project has that issue type"),
        Field("risk_import_jql", "Import risks from Jira matching this JQL (optional)", required=False,
              help='For example: project = SEC AND labels = risk'),
    ]
    tests = []
    syncs_tasks = True
    syncs_risks = True

    def __init__(self, config: dict, secrets: dict, client: httpx.Client | None = None, timeout: float = 30):
        super().__init__(config, secrets)
        self.base = guarded_base_url(config.get("site", ""), allowed_suffixes=(".atlassian.net", ".jira.com"))
        self.project = (config.get("project_key") or "").strip().upper()
        if not re.fullmatch(r"[A-Z][A-Z0-9_]{1,19}", self.project):
            raise ConnectorError("Enter a valid project key, for example SEC")
        auth = base64.b64encode(f"{config.get('email', '').strip()}:{secrets.get('api_token', '')}".encode()).decode()
        self.headers = {"Authorization": f"Basic {auth}", "Accept": "application/json"}
        self.client = client or httpx.Client(timeout=timeout)

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

    # ------------------------------------------------------------------ risks

    @property
    def risk_sync_enabled(self) -> bool:
        return str(self.config.get("sync_risks", "yes")).strip().lower() in ("yes", "y", "true", "1", "on")

    def _risk_fields(self, risk, app_url: str) -> dict:
        score = risk.likelihood * risk.impact
        level = "high" if score >= 15 else "medium" if score >= 8 else "low"
        lines = [
            risk.description or "",
            f"Risk score: {score} ({level}) = likelihood {risk.likelihood} x impact {risk.impact}",
            f"Treatment: {risk.treatment}" + (f". Plan: {risk.treatment_plan}" if risk.treatment_plan else ""),
        ]
        if risk.control_codes:
            lines.append("Controls: " + ", ".join(risk.control_codes))
        lines.append(f"Managed in Anupalan: {app_url}")
        return {"summary": f"[Risk] {risk.title}"[:250], "description": _adf("\n\n".join(x for x in lines if x)),
                "labels": ["risk", "anupalan", f"risk-{level}"]}

    def create_risk_issue(self, risk, app_url: str) -> None:
        fields = {"project": {"key": self.project},
                  "issuetype": {"name": self.config.get("risk_issue_type") or "Task"},
                  **self._risk_fields(risk, app_url)}
        if risk.review_date:
            fields["duedate"] = risk.review_date.isoformat()
        r = self._req("POST", "/rest/api/3/issue", json={"fields": fields})
        if r.status_code >= 400:
            raise ConnectorError(f"Jira refused to create the risk issue ({r.status_code}). Check the risk issue type "
                                 "exists in the project.")
        key = r.json()["key"]
        risk.external_ref, risk.external_url = key, f"{self.base}/browse/{key}"
        risk.external_status = "To Do"
        risk.external_synced_at = datetime.now(timezone.utc)

    def update_risk_issue(self, risk, app_url: str) -> None:
        fields = self._risk_fields(risk, app_url)
        r = self._req("PUT", f"/rest/api/3/issue/{risk.external_ref}", json={"fields": fields})
        if r.status_code >= 400 and r.status_code != 404:
            raise ConnectorError(f"Jira refused the update to {risk.external_ref} ({r.status_code}).")

    def _search(self, jql: str, fields: list[str], limit: int = 100) -> list[dict]:
        out, token = [], None
        while len(out) < limit:
            body = {"jql": jql, "fields": fields, "maxResults": min(100, limit - len(out))}
            if token:
                body["nextPageToken"] = token
            r = self._req("POST", "/rest/api/3/search/jql", json=body)
            if r.status_code == 400:
                raise ConnectorError("Jira couldn't run the JQL: " + "; ".join(r.json().get("errorMessages", []))[:300])
            r.raise_for_status()
            data = r.json()
            out += data.get("issues", [])
            token = data.get("nextPageToken")
            if not token or data.get("isLast", True):
                break
        return out

    @staticmethod
    def _apply_status(risk, issue: dict) -> bool:
        status = (issue.get("fields") or {}).get("status") or {}
        cat = (status.get("statusCategory") or {}).get("key")
        risk.external_status = (status.get("name") or "")[:100]
        risk.external_synced_at = datetime.now(timezone.utc)
        if cat == "done" and risk.status == "open":
            risk.status = "treated"
            return True
        if cat in ("new", "indeterminate") and risk.status == "treated":
            risk.status = "open"  # reopened in Jira
            return True
        return False

    def sync_risks(self, db: Session, org_id: uuid.UUID, app_url: str = "") -> dict:
        from app.models import Membership, Risk, Task, User

        pushed = updated = imported = 0
        url = (app_url or "").rstrip("/") + "/risks"
        if self.risk_sync_enabled:
            new = db.scalars(select(Risk).where(Risk.org_id == org_id, Risk.external_ref == "",
                                                Risk.status != "closed").order_by(Risk.created_at)).all()
            for risk in new[:MAX_PER_SYNC]:
                self.create_risk_issue(risk, url)
                pushed += 1
            db.flush()
        linked = db.scalars(select(Risk).where(Risk.org_id == org_id, Risk.external_ref != "")).all()
        by_key = {r.external_ref: r for r in linked}
        keys = [k for k in by_key if re.fullmatch(r"[A-Z][A-Z0-9_]+-\d+", k)]
        for i in range(0, len(keys), 100):
            for issue in self._search(f"key in ({','.join(keys[i:i + 100])})", ["status"]):
                risk = by_key.get(issue.get("key"))
                if risk and self._apply_status(risk, issue):
                    updated += 1
        jql = (self.config.get("risk_import_jql") or "").strip()
        if jql:
            taken = set(by_key) | set(db.scalars(select(Task.external_ref).where(Task.org_id == org_id,
                                                                               Task.external_ref != "")))
            emails = {e.lower(): uid for uid, e in db.execute(
                select(User.id, User.email).join(Membership, Membership.user_id == User.id)
                .where(Membership.org_id == org_id, Membership.role != "auditor"))}
            for issue in self._search(jql, ["summary", "description", "status", "assignee", "duedate", "labels"],
                                      limit=200):
                if issue.get("key") in taken:
                    continue
                f = issue.get("fields") or {}
                assignee = (f.get("assignee") or {}).get("emailAddress") or ""
                risk = Risk(org_id=org_id, title=(f.get("summary") or issue["key"])[:300],
                            description=_adf_text(f.get("description"))[:20000], category="Imported from Jira",
                            source="jira", status="open", likelihood=3, impact=3, treatment="mitigate",
                            external_ref=issue["key"], external_url=f"{self.base}/browse/{issue['key']}",
                            owner_id=emails.get(assignee.lower()))
                self._apply_status(risk, issue)
                db.add(risk)
                imported += 1
        db.flush()
        return {"pushed": pushed, "updated": updated, "imported": imported}


def _adf_text(node) -> str:
    """Plain text from an Atlassian Document Format value (or a plain string from older APIs)."""
    if node is None:
        return ""
    if isinstance(node, str):
        return node
    parts: list[str] = []

    def walk(n):
        if isinstance(n, dict):
            if n.get("type") == "text":
                parts.append(n.get("text", ""))
            for c in n.get("content") or []:
                walk(c)
            if n.get("type") in ("paragraph", "heading", "listItem"):
                parts.append("\n")
        elif isinstance(n, list):
            for c in n:
                walk(c)

    walk(node)
    return re.sub(r"\n{3,}", "\n\n", "".join(parts)).strip()
