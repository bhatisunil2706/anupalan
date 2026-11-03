"""Indian financial-sector frameworks: tiered RBI requirements and the move off the repealed 2023 Direction."""
from sqlalchemy import select, text

from app.models import AuditLog, Framework, OrgFramework, Requirement
from app.services.compliance import condition_holds
from app.services.content import load_content, migrate_retired_frameworks

FINANCIAL = {"rbi_cyber", "rbi_dpsc", "rbi_pso", "rbi_pa", "rbi_digital_lending", "rbi_it_outsourcing",
             "irdai_cyber", "ifsca_cyber", "sebi_cscrf"}


def test_condition_expressions():
    assert condition_holds(None, {}) and condition_holds("", {"x": True})
    assert condition_holds("a", {"a": True}) and not condition_holds("a", {})
    assert condition_holds("!a", {}) and not condition_holds("!a", {"a": True})
    assert condition_holds("!a&!b", {}) and not condition_holds("!a&!b", {"b": True})
    assert condition_holds("a|b", {"b": True}) and not condition_holds("a|b", {})


def test_financial_frameworks_are_listed_together(owner):
    cat = {f["code"]: f for f in owner.get("/api/frameworks").json()}
    assert FINANCIAL <= set(cat)
    assert {cat[c]["group"] for c in FINANCIAL} == {"India: financial regulators"}


def _applicable(owner, code):
    reqs = owner.get(f"/api/frameworks/{code}").json()["requirements"]
    return {r["ref"] for r in reqs if r["status"] != "not_applicable"}, {r["ref"] for r in reqs}


def test_rbi_tiers_follow_the_nbfc_layer(owner):
    owner.post("/api/frameworks/rbi_cyber/enable")
    full, all_refs = _applicable(owner, "rbi_cyber")
    assert {"SOC.1", "GOV.4", "CYB.14", "INC.1"} <= full and "OUT.1" not in full  # Middle Layer and above / banks

    owner.patch("/api/org", json={"profile": {"rbi_nbfc_small": True}})
    small, _ = _applicable(owner, "rbi_cyber")
    assert small == {r for r in all_refs if r.startswith("BAS.")}  # baseline only

    owner.patch("/api/org", json={"profile": {"rbi_nbfc_small": False, "rbi_nbfc_bl_large": True}})
    mid, _ = _applicable(owner, "rbi_cyber")
    assert {"GOV.1", "INC.1", "OUT.1", "CYB.16"} <= mid and not {"SOC.1", "GOV.4", "CYB.14"} & mid

    # The regulator-reporting and crisis-plan controls are provisioned.
    codes = {c["code"] for c in owner.get("/api/controls").json()}
    assert {"INC-06", "FIN-01", "FIN-02", "FIN-12"} <= codes


def test_orgs_on_the_repealed_2023_direction_are_moved(owner, admin_engine):
    # Recreate the retired framework and put the organisation on it, as an existing customer would be.
    with admin_engine.begin() as conn:
        org_id = conn.execute(text("SELECT id FROM organizations LIMIT 1")).scalar()
        fw_id = conn.execute(text(
            "INSERT INTO frameworks (id, code, name, short_name, version, region, publisher, description, "
            "source_url, content_version, review_status) VALUES (gen_random_uuid(), 'rbi_itgrc', 'Old', 'RBI IT', "
            "'2023', 'India', 'RBI', '', '', '0.1.0', 'draft') RETURNING id")).scalar()
        conn.execute(text("INSERT INTO requirements (id, framework_id, ref, section, title, guidance, \"order\") "
                          "VALUES (gen_random_uuid(), :f, 'GOV.1', '', 'x', '', 0)"), {"f": fw_id})
        conn.execute(text("INSERT INTO org_frameworks (id, org_id, framework_id, created_at, updated_at) "
                          "VALUES (gen_random_uuid(), :o, :f, now(), now())"), {"o": org_id, "f": fw_id})
    from sqlalchemy.orm import Session

    with Session(admin_engine) as db:
        assert migrate_retired_frameworks(db) == [str(org_id)]
        db.commit()
        assert db.scalar(select(Framework).where(Framework.code == "rbi_itgrc")) is None
        new = db.scalar(select(Framework).where(Framework.code == "rbi_cyber"))
        assert db.scalar(select(OrgFramework).where(OrgFramework.org_id == org_id,
                                                    OrgFramework.framework_id == new.id))
        assert db.scalar(select(AuditLog).where(AuditLog.org_id == org_id, AuditLog.action == "framework.replaced"))
        assert migrate_retired_frameworks(db) == []  # idempotent
        # Loading content again is safe too.
        load_content(db)
        assert db.scalar(select(Requirement).join(Framework).where(Framework.code == "rbi_cyber",
                                                                  Requirement.ref == "INC.1"))
    assert "rbi_cyber" in {f["code"] for f in owner.get("/api/frameworks").json() if f["enabled"]}
