"""Demo data: three realistic companies with a login per role. Development and staging only.

python -m app.cli seed-demo [--password ...] [--reset]
"""
import random
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.api.routes.vendor_dd import score_answers
from app.integrations import REGISTRY
from app.integrations.base import AccountRecord
from app.models import (
    AccessReview,
    AccessReviewItem,
    Account,
    ConsentEvent,
    ConsentNotice,
    Control,
    DataAsset,
    Evidence,
    EvidenceRequest,
    Framework,
    Incident,
    Integration,
    Membership,
    Organization,
    OrgFramework,
    Person,
    PhishingCampaign,
    PhishingTarget,
    Policy,
    PolicyTemplate,
    QuestionnaireTemplate,
    RequestComment,
    RightsRequest,
    Risk,
    Task,
    TrainingCompletion,
    User,
    Vendor,
    VendorAssessment,
    VendorDocument,
)
from app.security import encrypt_json, hash_password, new_token
from app.services import audit, storage
from app.services.checks import record_check
from app.services.compliance import provision_controls
from app.services.integrations import sync_accounts
from app.services.platform_checks import run_feature_checks, run_platform_checks
from app.services.policies import approve_policy, create_policy_from_template
from app.services.training import ensure_assignments

DEMO_DOMAIN_SUFFIX = ".example"  # RFC 2606: never delivered
DEFAULT_PASSWORD = "Demo-Anupalan-2026!"  # nosec B105 - demo-only password, refused in production
NOW = datetime.now(timezone.utc)
TODAY = date.today()


@dataclass
class Ctx:
    org: Organization
    user: User
    role: str = "owner"

    @property
    def org_id(self):
        return self.org.id


COMPANIES = [
    {
        "name": "Paisa Setu Fintech", "domain": "paisasetu.example", "sector": "Fintech (payments, NBFC partner)",
        "employees": "51-200", "frameworks": ["dpdp", "certin", "iso27001", "soc2"], "readiness": 0.72,
        "profile": {"uses_consent_manager": False}, "seed": 11,
        "people": [("Priya Sharma", "CEO & Co-founder", "Leadership", "owner"),
                   ("Arjun Mehta", "Head of Security", "Security", "admin"),
                   ("Neha Iyer", "Engineering Manager", "Engineering", "member"),
                   ("Kavya Reddy", "Partner, Sahni & Co (ISO auditor)", "External", "auditor")],
        "staff": [("Rahul Verma", "Backend Engineer", "Engineering"), ("Sneha Kulkarni", "Product Manager", "Product"),
                  ("Vikram Singh", "SRE", "Engineering"), ("Ananya Das", "Compliance Analyst", "Risk"),
                  ("Rohit Nair", "Customer Support Lead", "Operations"), ("Meera Joshi", "Finance Manager", "Finance"),
                  ("Aditya Rao", "Frontend Engineer", "Engineering"), ("Farhan Qureshi", "Data Analyst", "Product")],
        "leaver": ("Karan Malhotra", "Backend Engineer", "Engineering"),
        "vendors": [("Amazon Web Services", "critical", "Cloud hosting (ap-south-1)", True, ["ISO 27001", "SOC 2"]),
                    ("Razorpay", "critical", "Payment gateway", True, ["PCI DSS", "ISO 27001"]),
                    ("Freshworks", "high", "Customer support desk", True, ["ISO 27001", "SOC 2"]),
                    ("Signzy", "high", "Video KYC and identity verification", True, []),
                    ("Slack", "medium", "Internal chat", False, ["SOC 2"])],
        "assets": [("Customer KYC records", ["customers"], ["name", "pan", "aadhaar", "phone", "address", "photo"],
                    "KYC under RBI directions", "legitimate_use", "8 years after account closure (PMLA)"),
                   ("Payments and transactions", ["customers"], ["name", "bank_account", "upi", "phone"],
                    "Process payments and reconcile", "consent", "8 years"),
                   ("Marketing contacts", ["leads"], ["name", "email", "phone"], "Product updates and offers",
                    "consent", "Until consent is withdrawn"),
                   ("Employee records", ["employees"], ["name", "pan", "bank_account", "address"], "Payroll and HR",
                    "legitimate_use", "7 years after exit")],
    },
    {
        "name": "AarogyaLink Health", "domain": "aarogyalink.example", "sector": "Healthtech (teleconsultation)",
        "employees": "11-50", "frameworks": ["dpdp", "iso27001"], "readiness": 0.45,
        "profile": {"processes_children_data": True}, "seed": 23,
        "people": [("Dr. Sameer Kapoor", "Founder & CEO", "Leadership", "owner"),
                   ("Lakshmi Menon", "CTO", "Engineering", "admin"),
                   ("Imran Shaikh", "DevOps Engineer", "Engineering", "member"),
                   ("Deepa Pillai", "Lead Auditor, CertAssure India", "External", "auditor")],
        "staff": [("Pooja Bhatt", "Clinical Operations", "Clinical"), ("Nikhil Jain", "Full-stack Engineer",
                                                                     "Engineering"),
                  ("Shreya Ghosh", "Care Coordinator", "Clinical"), ("Manoj Patil", "Support Executive",
                                                                    "Operations")],
        "leaver": None,
        "vendors": [("Google Cloud", "critical", "Hosting and database (asia-south1)", True, ["ISO 27001", "SOC 2"]),
                    ("Twilio", "high", "Video consultation and SMS", True, ["ISO 27001", "SOC 2"]),
                    ("Zoho", "medium", "CRM and email", True, ["ISO 27001"]),
                    ("LabConnect Diagnostics", "high", "Lab test orders and reports", True, [])],
        "assets": [("Patient health records", ["patients", "children"], ["name", "health", "phone", "dob", "gender"],
                    "Provide teleconsultations and prescriptions", "consent", "3 years after last visit"),
                   ("Doctor profiles", ["doctors"], ["name", "email", "phone", "registration_number"],
                    "Run the marketplace", "consent", "Duration of contract + 1 year")],
    },
    {
        "name": "KiranaKart Commerce", "domain": "kiranakart.example", "sector": "E-commerce (quick commerce)",
        "employees": "201-500", "frameworks": ["dpdp", "certin", "soc2"], "readiness": 0.22,
        "profile": {}, "seed": 37,
        "people": [("Rajesh Gupta", "COO", "Leadership", "owner"),
                   ("Sunita Bose", "IT & Security Manager", "IT", "admin"),
                   ("Amit Tiwari", "Platform Engineer", "Engineering", "member")],
        "staff": [("Divya Agarwal", "Category Manager", "Business"), ("Harish Kumar", "Warehouse Lead",
                                                                     "Operations"),
                  ("Zoya Khan", "Marketing Manager", "Marketing")],
        "leaver": ("Gaurav Saxena", "Marketing Executive", "Marketing"),
        "vendors": [("Microsoft Azure", "critical", "Hosting (Central India)", True, ["ISO 27001", "SOC 2"]),
                    ("Shiprocket", "high", "Last-mile delivery partners", True, []),
                    ("MoEngage", "high", "Customer engagement and push", True, ["ISO 27001"]),
                    ("Gupshup", "medium", "WhatsApp and SMS messages", True, [])],
        "assets": [("Customer orders and addresses", ["customers"], ["name", "phone", "address", "email"],
                    "Deliver orders", "consent", "3 years"),
                   ("Delivery partner KYC", ["delivery partners"], ["name", "aadhaar", "bank_account", "phone"],
                    "Onboard and pay delivery partners", "legitimate_use", "Duration of engagement + 3 years")],
    },
]


def _email(name: str, domain: str) -> str:
    first = name.replace("Dr. ", "").split()[0].lower()
    return f"{first}@{domain}"


def _wipe(db: Session) -> None:
    """Delete demo organisations and users with database-level cascades."""
    db.execute(delete(Organization).where(Organization.name.in_([c["name"] for c in COMPANIES])))
    db.execute(delete(User).where(User.email.like(f"%{DEMO_DOMAIN_SUFFIX}")))
    db.flush()


def seed(db: Session, password: str = DEFAULT_PASSWORD, reset: bool = False) -> list[dict]:
    existing = db.scalar(select(Organization).where(Organization.name == COMPANIES[0]["name"]))
    if existing and not reset:
        raise RuntimeError("Demo data already exists. Run with --reset to recreate it.")
    _wipe(db)
    pw_hash = hash_password(password)
    out = []
    for spec in COMPANIES:
        out.append(_seed_company(db, spec, pw_hash))
        db.commit()
    return out


def _seed_company(db: Session, spec: dict, pw_hash: str) -> dict:
    rnd = random.Random(spec["seed"])  # nosec B311 - deterministic demo data
    org = Organization(id=uuid.uuid4(), name=spec["name"], sector=spec["sector"], employee_count=spec["employees"],
                       profile=spec["profile"], portal_enabled=True,
                       portal_slug=spec["domain"].split(".")[0], privacy_contact_name="Grievance Officer",
                       privacy_contact_email=f"privacy@{spec['domain']}", session_idle_minutes=120)
    db.add(org)
    db.flush()
    users, logins = {}, []
    for name, _title, _dept, role in spec["people"]:
        u = User(id=uuid.uuid4(), email=_email(name, spec["domain"]), full_name=name, password_hash=pw_hash,
                 email_verified_at=NOW, password_changed_at=NOW)
        db.add(u)
        db.flush()
        db.add(Membership(user_id=u.id, org_id=org.id, role=role,
                          expires_at=NOW + timedelta(days=90) if role == "auditor" else None))
        users[role] = u
        logins.append({"role": role, "email": u.email, "name": name})
    db.flush()
    owner, admin = users["owner"], users.get("admin", users["owner"])
    member = users.get("member", admin)
    ctx = Ctx(org=org, user=owner)
    audit.record(db, ctx, "org.created", org, demo=True)

    # frameworks, controls, policies
    for fw in db.scalars(select(Framework).where(Framework.code.in_(spec["frameworks"]))):
        db.add(OrgFramework(org_id=org.id, framework_id=fw.id, target_date=TODAY + timedelta(days=120)))
    db.flush()
    provision_controls(db, org)
    for tpl in db.scalars(select(PolicyTemplate)):
        create_policy_from_template(db, ctx, tpl, skip_existing=True)
    ensure_assignments(db, org.id)
    org.onboarded_at = NOW - timedelta(days=75)
    audit.record(db, ctx, "org.onboarded", org, frameworks=spec["frameworks"])
    db.flush()

    controls = db.scalars(select(Control).where(Control.org_id == org.id).order_by(Control.code)).all()
    owners = [owner, admin, member]
    readiness = spec["readiness"]
    for c in controls:
        c.owner_id = rnd.choice(owners).id
        roll = rnd.random()
        if roll < readiness:
            c.status = "implemented"
            c.implementation_notes = _impl_note(c.code, spec)
            db.add(Evidence(org_id=org.id, control_id=c.id, kind="note", source="manual",
                            title=f"{c.title}: how we do it", description=c.implementation_notes,
                            uploaded_by_id=c.owner_id, collected_at=NOW - timedelta(days=rnd.randint(5, 60)),
                            valid_until=TODAY + timedelta(days=rnd.randint(-10, 300))))
        elif roll < readiness + 0.18:
            c.status = "in_progress"
        if c.code in ("PRV-12", "CIN-01", "CIN-02") and not spec["profile"].get("is_significant_data_fiduciary"):
            c.status, c.na_justification = "not_applicable", "Not notified as SDF / not an infrastructure provider."
    # one real (encrypted) evidence file
    acc = next((c for c in controls if c.code == "ACC-03"), None)
    if acc:
        key, name, size = storage.save_bytes(org.id, "mfa-enforcement-report.csv",
                                             b"user,mfa\n" + b"".join(f"{_email(p[0], spec['domain'])},enforced\n"
                                                                      .encode() for p in spec["people"]))
        db.add(Evidence(org_id=org.id, control_id=acc.id, kind="file", source="manual", title="MFA enforcement report",
                        file_key=key, file_name=name, size_bytes=size, content_type="text/csv",
                        uploaded_by_id=admin.id, valid_until=TODAY + timedelta(days=90)))
    policies = db.scalars(select(Policy).where(Policy.org_id == org.id).order_by(Policy.title)).all()
    for p in policies[: int(len(policies) * readiness)]:
        approve_policy(db, ctx, p)
        audit.record(db, ctx, "policy.approved", p)

    # people, identity accounts and simulated connector results
    staff = [(n, t, d) for n, t, d, r in spec["people"] if r != "auditor"] + spec["staff"]
    for i, (name, title, dept) in enumerate(staff):
        db.add(Person(org_id=org.id, source="demo", employee_id=f"E{100 + i}", email=_email(name, spec["domain"]),
                      full_name=name, title=title, department=dept, status="active",
                      manager_email=owner.email, join_date=TODAY - timedelta(days=rnd.randint(60, 1200))))
    if spec["leaver"]:
        name, title, dept = spec["leaver"]
        db.add(Person(org_id=org.id, source="demo", employee_id="E099", email=_email(name, spec["domain"]),
                      full_name=name, title=title, department=dept, status="exited",
                      join_date=TODAY - timedelta(days=500), exit_date=TODAY - timedelta(days=12)))
    db.flush()
    idp = "google_workspace" if "Google" in " ".join(v[0] for v in spec["vendors"]) or rnd.random() < 0.5 \
        else "microsoft365"
    integ = Integration(org_id=org.id, provider=idp, config={"demo": True}, secret_encrypted=encrypt_json({}),
                        status="connected", last_synced_at=NOW - timedelta(hours=3))
    db.add(integ)
    db.flush()
    records = [AccountRecord(external_id=f"acct-{i}", email=_email(n, spec["domain"]), name=n,
                             is_admin=i < 2, is_active=True, mfa_enabled=rnd.random() > 0.15,
                             last_login_at=NOW - timedelta(days=rnd.randint(0, 20)))
               for i, (n, *_rest) in enumerate(staff + ([spec["leaver"]] if spec["leaver"] else []))]
    sync_accounts(db, integ, records)
    connector = REGISTRY[idp]
    for t in connector.tests:
        status = "pass" if rnd.random() < readiness + 0.15 else "fail"
        record_check(db, org.id, integration_id=integ.id, source_name=f"{connector.name} (demo)", key=t.key,
                     title=t.title, control_codes=t.control_codes, status=status,
                     summary="Simulated result for the demo workspace" if status == "pass"
                     else "Simulated finding: 2 users without MFA (demo)")
    run_platform_checks(db, org)

    # risks
    for title, cat, lik, imp, codes in [
        ("Phishing leads to account takeover of a production admin", "People", 4, 5, ["ACC-03", "HR-03"]),
        ("Customer personal data exposed through a misconfigured storage bucket", "Cloud", 2, 5, ["ACC-06"]),
        ("Key vendor breach affects our customers' data", "Vendors", 3, 4, ["VEN-01", "VEN-02"]),
        ("Missed 6-hour CERT-In reporting window", "Compliance", 2, 4, ["INC-02"]),
        ("Ransomware on employee laptops", "Endpoints", 3, 4, ["AST-05", "OPS-01"]),
    ]:
        risk = Risk(org_id=org.id, title=title, category=cat, likelihood=lik, impact=imp, owner_id=admin.id,
                    control_codes=codes, treatment="mitigate", status=rnd.choice(["open", "treated"]),
                    residual_likelihood=max(1, lik - 2), residual_impact=imp, review_date=TODAY + timedelta(days=90),
                    treatment_plan="Tracked through the linked controls.")
        if readiness >= 0.7:  # simulated Jira links (no real Jira behind the demo)
            n = 101 + len([r for r in db.new if isinstance(r, Risk)])
            risk.external_ref = f"SEC-{n}"
            risk.external_url = f"https://jira.{spec['domain']}/browse/SEC-{n}"
            risk.external_status = "Done" if risk.status == "treated" else rnd.choice(["To Do", "In Progress"])
            risk.external_synced_at = NOW - timedelta(minutes=rnd.randint(5, 300))
        db.add(risk)

    # vendors, documents and questionnaires
    tpl = db.scalar(select(QuestionnaireTemplate).where(QuestionnaireTemplate.slug == "vendor-security-baseline"))
    tpls = {t.slug: t for t in db.scalars(select(QuestionnaireTemplate))}
    for i, (vname, tier, services, processor, certs) in enumerate(spec["vendors"]):
        v = Vendor(org_id=org.id, name=vname, tier=tier, services=services, is_processor=processor,
                   dpa_signed=processor and i % 3 != 2, data_location="India" if i % 2 == 0 else "India, Singapore",
                   certifications=certs, owner_id=admin.id, status="active",
                   last_assessed_at=TODAY - timedelta(days=200 + 40 * i) if i < 3 else None,
                   next_review_date=TODAY + timedelta(days=[20, 160, -5, 300, 90][i % 5]))
        db.add(v)
        db.flush()
        if certs:
            key, name, size = storage.save_bytes(org.id, f"{vname.lower().replace(' ', '-')}-iso27001.pdf",
                                                 b"%PDF-1.4\n% demo certificate\n")
            db.add(VendorDocument(org_id=org.id, vendor_id=v.id, kind="iso27001", title="ISO 27001 certificate",
                                  file_key=key, file_name=name, size_bytes=size, uploaded_by_id=admin.id,
                                  valid_until=TODAY + timedelta(days=[25, 400, -3, 200, 600][i % 5])))
        if tpl and i in (1, 3):
            t = tpls.get("standard-full" if tier in ("critical", "high") else "standard-lite", tpl)

            def answer(q):
                if q["type"] == "yes_no":
                    good = q.get("good", "yes")
                    return good if rnd.random() < 0.85 else ("no" if good == "yes" else "yes")
                if q["type"] == "choice":
                    return q["options"][rnd.randint(0, min(1, len(q["options"]) - 1))]
                return "India (Mumbai, Hyderabad)"

            answers = {q["id"]: {"answer": answer(q), "comment": ""} for q in t.questions}
            score, rating, _ = score_answers(t.questions, answers)
            _, token_hash = new_token()
            db.add(VendorAssessment(org_id=org.id, vendor_id=v.id, template_slug=t.slug, template_title=t.title,
                                    questions=t.questions, token_hash=token_hash,
                                    sent_to_email=f"security@{vname.split()[0].lower()}.example", status="submitted",
                                    answers=answers, respondent_name=f"{vname} security team", score=score,
                                    rating=rating, submitted_at=NOW - timedelta(days=3), created_by_id=admin.id,
                                    expires_at=NOW + timedelta(days=18)))
        if i == 4 and "standard-lite" in tpls:
            t = tpls["standard-lite"]
            partial = {q["id"]: {"answer": q.get("good", "yes"), "comment": ""}
                       for q in t.questions[:20] if q["type"] == "yes_no"}
            _, token_hash = new_token()
            db.add(VendorAssessment(org_id=org.id, vendor_id=v.id, template_slug=t.slug, template_title=t.title,
                                    questions=t.questions, token_hash=token_hash, status="in_progress",
                                    answers=partial, sent_to_email=f"it@{vname.split()[0].lower()}.example",
                                    created_by_id=admin.id, expires_at=NOW + timedelta(days=2)))
        if tpl and i == 2:
            _, token_hash = new_token()
            db.add(VendorAssessment(org_id=org.id, vendor_id=v.id, template_slug="dpdp-processor",
                                    template_title=tpls["dpdp-processor"].title if "dpdp-processor" in tpls else "",
                                    questions=tpls["dpdp-processor"].questions if "dpdp-processor" in tpls else [],
                                    token_hash=token_hash, sent_to_email=f"dpo@{vname.split()[0].lower()}.example",
                                    status="sent", created_by_id=admin.id, expires_at=NOW + timedelta(days=14)))

    # DPDP: record of processing, notices, consent log, rights requests, incidents
    vendor_names = [v[0] for v in spec["vendors"]]
    for name, principals, cats, purpose, ground, retention in spec["assets"]:
        db.add(DataAsset(org_id=org.id, name=name, data_principals=principals, data_categories=cats,
                         purposes=purpose, lawful_ground=ground, retention_period=retention,
                         processors=vendor_names[:2], systems=["Core app", "Data warehouse"],
                         includes_children_data="children" in principals, owner_id=admin.id,
                         last_reviewed_at=TODAY - timedelta(days=30)))
    notice = ConsentNotice(org_id=org.id, key="signup", version=2, title=f"{spec['name']} sign-up consent",
                           body_md="We collect your name, phone and email to create your account. You can withdraw "
                                   "consent at any time from Settings > Privacy.",
                           purposes=[{"id": "account", "label": "Create and run your account", "required": True},
                                     {"id": "marketing", "label": "Offers by SMS, email and WhatsApp"},
                                     {"id": "analytics", "label": "Product analytics"}],
                           languages=["en", "hi"], status="published", published_at=NOW - timedelta(days=40))
    db.add(ConsentNotice(org_id=org.id, key="signup", version=1, title="Sign-up consent (2025)", body_md="Old",
                         purposes=notice.purposes, languages=["en"], status="retired",
                         published_at=NOW - timedelta(days=300)))
    db.add(notice)
    for n in range(int(240 * (0.5 + readiness))):
        when = NOW - timedelta(minutes=rnd.randint(10, 60 * 24 * 45))
        purposes = ["account"] + [p for p in ("marketing", "analytics") if rnd.random() < 0.6]
        db.add(ConsentEvent(org_id=org.id, event_id=f"demo-{n}", principal_id=f"cust-{10000 + n}",
                            notice_key="signup", notice_version=2, action="granted", purposes=purposes,
                            source=rnd.choice(["web", "app", "app", "web"]), language=rnd.choice(["en", "en", "hi"]),
                            occurred_at=when, received_at=when + timedelta(seconds=2)))
        if "marketing" in purposes and rnd.random() < 0.12:
            later = when + timedelta(days=rnd.randint(1, 10))
            if later < NOW:
                db.add(ConsentEvent(org_id=org.id, event_id=f"demo-{n}-w", principal_id=f"cust-{10000 + n}",
                                    notice_key="signup", notice_version=2, action="withdrawn",
                                    purposes=["marketing"], source="app", occurred_at=later,
                                    received_at=later + timedelta(seconds=2)))
    for num, (rtype, who, days_ago, status) in enumerate([
            ("erasure", "Ramesh Yadav", 25, "in_progress"), ("access", "Fatima Begum", 4, "new"),
            ("correction", "Suresh Pillai", 40, "completed")], start=1):
        received = NOW - timedelta(days=days_ago)
        db.add(RightsRequest(org_id=org.id, number=num, request_type=rtype, requester_name=who,
                             requester_email=f"{who.split()[0].lower()}@mail.example", channel="portal",
                             details="Submitted through the privacy portal.", received_at=received,
                             due_at=received + timedelta(days=30), legal_due_at=received + timedelta(days=90),
                             identity_verified=status != "new", status=status, assignee_id=admin.id,
                             closed_at=received + timedelta(days=9) if status == "completed" else None,
                             resolution="Corrected the address in the CRM." if status == "completed" else ""))
    detected = NOW - timedelta(days=21)
    db.add(Incident(org_id=org.id, number=1, title="Credential-stuffing attempts on customer login",
                    description="Spike of failed logins from a botnet; rate limits held, 3 accounts locked.",
                    severity="sev2", category="Unauthorised access attempt", detected_at=detected, status="closed",
                    lead_id=admin.id, certin_reportable=True, certin_due_at=detected + timedelta(hours=6),
                    certin_reported_at=detected + timedelta(hours=4), root_cause="Reused passwords from a third-"
                    "party breach.", actions_taken="Blocked IP ranges, forced resets, enabled breached-password "
                    "checks."))
    if readiness < 0.5:
        d2 = NOW - timedelta(hours=3)
        db.add(Incident(org_id=org.id, number=2, title="Laptop stolen from a delivery hub", severity="sev3",
                        description="Unencrypted laptop with order exports was stolen.", category="Device loss",
                        detected_at=d2, status="open", lead_id=admin.id, certin_reportable=False,
                        personal_data_breach=True, affected_principals_estimate=1200,
                        dpb_due_at=d2 + timedelta(hours=72)))

    # training
    for u in [x for r, x in users.items() if r != "auditor"]:
        for slug in ("security-essentials", "dpdp-basics", "phishing"):
            if rnd.random() < readiness + 0.25:
                db.add(TrainingCompletion(org_id=org.id, course_slug=slug, user_id=u.id, email=u.email,
                                          score=rnd.choice([80, 90, 100]), passed=True, source="platform",
                                          completed_at=NOW - timedelta(days=rnd.randint(3, 200))))

    # role-based assignments and a past phishing simulation
    assignments = ensure_assignments(db, org.id)
    depts = {d for _, _, d in staff}
    if "Engineering" in depts and "secure-development" in assignments:
        a = assignments["secure-development"]
        a.required, a.departments, a.required_since = True, ["Engineering"], TODAY - timedelta(days=45)
    if readiness >= 0.4:
        from app.services import training as tr

        campaign = PhishingCampaign(org_id=org.id, name="Overdue invoice test", template_slug="invoice-overdue",
                                    status="closed", enroll_clickers=True, created_by_id=admin.id,
                                    sent_at=NOW - timedelta(days=40), closed_at=NOW - timedelta(days=26))
        db.add(campaign)
        db.flush()
        for p in db.scalars(select(Person).where(Person.org_id == org.id, Person.status == "active")):
            _, th = new_token()
            clicked = rnd.random() < (0.12 if readiness >= 0.7 else 0.3)
            db.add(PhishingTarget(org_id=org.id, campaign_id=campaign.id, email=p.email, full_name=p.full_name,
                                  department=p.department, token_hash=th, sent_at=campaign.sent_at,
                                  clicked_at=campaign.sent_at + timedelta(minutes=rnd.randint(3, 600))
                                  if clicked else None))
            if clicked:
                tr.enroll(db, org.id, p.email, "phishing", "Clicked the 'Overdue invoice test' phishing simulation")

    # tasks, access review and an auditor request
    for title, prio, due in [("Collect signed DPAs from processors", "high", 10),
                             ("Run a tabletop exercise for the CERT-In playbook", "medium", 30),
                             ("Restore test of production backups", "medium", -2)]:
        db.add(Task(org_id=org.id, title=title, priority=prio, assignee_id=rnd.choice(owners).id,
                    due_date=TODAY + timedelta(days=due), source="manual"))
    review = AccessReview(org_id=org.id, title=f"Q{(TODAY.month - 1) // 3 + 1} {TODAY.year} access review",
                          providers=[idp], status="open", due_date=TODAY + timedelta(days=9), created_by_id=admin.id)
    db.add(review)
    db.flush()
    for a in db.scalars(select(Account).where(Account.org_id == org.id)):
        person = db.scalar(select(Person).where(Person.org_id == org.id, Person.email == a.email))
        db.add(AccessReviewItem(review_id=review.id, org_id=org.id, account_id=a.id, provider=a.provider,
                                external_id=a.external_id, email=a.email, name=a.name, is_admin=a.is_admin,
                                person_status=person.status if person else "unknown", reviewer_id=admin.id,
                                decision="pending"))
    auditor = users.get("auditor")
    if auditor:
        mfa = next((c for c in controls if c.code == "ACC-03"), None)
        for n, (title, status) in enumerate([("Evidence that MFA is enforced for all staff", "submitted"),
                                             ("Last two quarterly access reviews", "open"),
                                             ("Backup restore test results", "open")], start=1):
            req = EvidenceRequest(org_id=org.id, number=n, title=title, status=status, requested_by_id=auditor.id,
                                  assignee_id=admin.id, framework_code="iso27001", due_date=TODAY + timedelta(days=7),
                                  control_id=mfa.id if n == 1 and mfa else None,
                                  description="Please share evidence covering the full audit period.")
            db.add(req)
            db.flush()
            if n == 1:
                ev = db.scalar(select(Evidence).where(Evidence.control_id == mfa.id, Evidence.kind == "file"))
                if ev:
                    req.evidence_ids = [str(ev.id)]
                db.add(RequestComment(org_id=org.id, request_id=req.id, user_id=admin.id,
                                      body="Attached the IdP enforcement report exported this week."))
            audit.write(db, org_id=org.id, user_id=auditor.id, action="audit_request.created", entity=req,
                        detail={"ref": f"REQ-{n}"})
    db.flush()
    run_feature_checks(db, org, force=True)
    return {"org": org.name, "logins": logins}


IMPL_NOTES = {
    "ACC": "Enforced through our identity provider; access granted by role and reviewed quarterly.",
    "OPS": "Automated in CI/CD and monitored by the SRE on-call rotation.",
    "LOG": "Logs shipped to our SIEM in ap-south-1 and retained for 180 days.",
    "PRV": "Owned by the Grievance Officer; process documented in the privacy runbook.",
    "INC": "Covered by the incident response plan; CERT-In POC registered.",
    "HR": "Handled by People Ops during onboarding and offboarding.",
    "VEN": "Vendors are tiered and assessed before onboarding and annually.",
}


def _impl_note(code: str, spec: dict) -> str:
    return IMPL_NOTES.get(code.split("-")[0], f"Implemented at {spec['name']} and reviewed annually.")


def remove_demo(db: Session) -> None:
    _wipe(db)
    db.commit()

