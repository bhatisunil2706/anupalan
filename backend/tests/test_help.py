"""In-app documentation: content validity and the public /api/help endpoints."""
import re

from app.services import help as docs


def test_every_article_is_valid_and_links_resolve():
    assert docs.validate() >= 30
    for a in docs.articles().values():
        assert a.title and a.summary, a.slug
        assert a.section in docs.SECTIONS, a.slug
        assert re.fullmatch(r"[a-z0-9-]+", a.slug)
        # Raw HTML is never rendered by the frontend, and articles shouldn't rely on it.
        assert "<script" not in a.body_md.lower(), a.slug


def test_anchor_rule():
    assert docs.anchor("How readiness is calculated") == "how-readiness-is-calculated"
    assert docs.anchor("**Consent** API — v1 (beta)") == "consent-api-v1-beta"


def test_index_and_article(client):
    idx = client.get("/api/help").json()
    sections = [s["title"] for s in idx["sections"]]
    assert sections[0] == "Get started" and "Reference" in sections
    first = idx["sections"][0]["articles"][0]
    assert first["slug"] == "introduction"

    art = client.get("/api/help/api").json()
    assert art["title"] == "API reference"
    ids = {h["id"] for h in art["headings"]}
    assert {"consent-api", "evidence-api", "authentication"} <= ids
    assert art["prev"] and art["next"]
    assert "Authorization: Bearer" in art["body_md"]

    assert client.get("/api/help/introduction").json()["prev"] is None
    assert client.get("/api/help/does-not-exist").status_code == 404


def test_search(client):
    r = client.get("/api/help/search", params={"q": "CERT-In 6 hours"}).json()["results"]
    assert r and r[0]["slug"] in {"incidents", "dpdp-overview", "glossary"}
    assert all("snippet" in x for x in r)
    assert client.get("/api/help/search", params={"q": "zzzqqq-nothing"}).json()["results"] == []
    assert client.get("/api/help/search", params={"q": "a"}).status_code == 422


def test_contextual_help_for_pages(client):
    def slug(path):
        a = client.get("/api/help/for-page", params={"path": path}).json()["article"]
        return a and a["slug"]

    assert slug("/dashboard") == "dashboard"
    assert slug("/settings") == "organisation-settings"
    assert slug("/controls/123") == "controls"
    assert slug("/vendors/questionnaires/caiq") == "vendor-questionnaires"
    assert slug("/vendors/abc") == "vendors"
    assert slug("/evidence/review") == "evidence-review"
    assert slug("/nowhere") is None


def test_help_is_public_but_app_pages_are_not(client):
    assert client.get("/api/help").status_code == 200
    assert client.get("/api/auth/me").status_code == 401
