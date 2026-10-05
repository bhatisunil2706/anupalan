import httpx
from sqlalchemy import select

from app.integrations.github import GitHubConnector
from app.models import Integration, Organization, Task
from app.security import encrypt_json
from app.services.integrations import apply_results


def github_transport(two_fa: bool, protected: bool):
    def handler(request: httpx.Request) -> httpx.Response:
        p = request.url.path
        if p == "/orgs/acme":
            return httpx.Response(200, json={"login": "acme", "two_factor_requirement_enabled": two_fa})
        if p == "/orgs/acme/repos":
            return httpx.Response(200, json=[
                {"name": "api", "default_branch": "main",
                 "security_and_analysis": {"secret_scanning": {"status": "enabled"}}},
                {"name": "old", "archived": True},
            ])
        if p == "/repos/acme/api/branches/main/protection":
            if protected:
                return httpx.Response(200, json={"required_pull_request_reviews": {"required_approving_review_count": 1}})
            return httpx.Response(404, json={})
        if p == "/repos/acme/api/vulnerability-alerts":
            return httpx.Response(204)
        if p == "/orgs/acme/members":
            return httpx.Response(200, json=[{"login": "a"}, {"login": "b"}])
        return httpx.Response(404)

    return httpx.MockTransport(handler)


def connector(two_fa=True, protected=True):
    client = httpx.Client(base_url="https://api.github.com", transport=github_transport(two_fa, protected))
    return GitHubConnector({"organization": "acme", "max_admins": "3"}, {"token": "t"}, client=client)


def test_github_checks():
    results = {r.key: r for r in connector(two_fa=True, protected=False).run()}
    assert results["github.org_2fa"].status == "pass"
    assert results["github.branch_protection"].status == "fail"
    assert results["github.branch_protection"].details["failing_repositories"] == ["api"]
    assert results["github.secret_scanning"].status == "pass"
    assert results["github.dependabot_alerts"].status == "pass"
    assert results["github.admin_count"].status == "pass"


def test_results_create_evidence_and_tasks_then_autoresolve(owner, db):
    org = db.scalar(select(Organization))
    integ = Integration(org_id=org.id, provider="github", config={"organization": "acme"},
                        secret_encrypted=encrypt_json({"token": "t"}))
    db.add(integ)
    db.commit()

    apply_results(db, integ, connector(two_fa=False, protected=True).run())
    db.commit()
    acc03 = next(c for c in owner.get("/api/controls").json() if c["code"] == "ACC-03")
    assert acc03["health"] == "failing"
    task = db.scalar(select(Task).where(Task.source == "test:github.org_2fa"))
    assert task is not None and task.status == "open" and task.priority == "high"
    sdl02 = next(c for c in owner.get("/api/controls").json() if c["code"] == "SDL-02")
    assert sdl02["valid_evidence"] == 1

    apply_results(db, integ, connector(two_fa=True, protected=True).run())
    db.commit()
    db.refresh(task)
    assert task.status == "done"
    acc03 = next(c for c in owner.get("/api/controls").json() if c["code"] == "ACC-03")
    assert acc03["health"] != "failing" and acc03["valid_evidence"] == 1


def test_integration_catalog(owner):
    providers = {i["provider"]: i for i in owner.get("/api/integrations").json()}
    assert {"aws", "github"} <= set(providers)
    assert providers["github"]["connection"] is None
    assert any(f["secret"] for f in providers["aws"]["fields"])
