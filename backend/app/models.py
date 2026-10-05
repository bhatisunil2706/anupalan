"""Database models.

Two scopes:
- Global content (Framework, Requirement, ControlTemplate, Mapping, PolicyTemplate) is shared by all tenants
  and loaded from app/content.
- Tenant data carries org_id and must always be queried through an org-scoped filter (see app/deps.py).
"""
import uuid
from datetime import date, datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def uid() -> uuid.UUID:
    return uuid.uuid4()


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


# --------------------------------------------------------------------------------------
# Global content
# --------------------------------------------------------------------------------------


class Framework(Base):
    __tablename__ = "frameworks"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uid)
    code: Mapped[str] = mapped_column(String(50), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    short_name: Mapped[str] = mapped_column(String(50))
    version: Mapped[str] = mapped_column(String(50))
    region: Mapped[str] = mapped_column(String(50))
    publisher: Mapped[str] = mapped_column(String(200), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    source_url: Mapped[str] = mapped_column(String(500), default="")
    content_version: Mapped[str] = mapped_column(String(20), default="0.1.0")
    review_status: Mapped[str] = mapped_column(String(20), default="draft")

    requirements: Mapped[list["Requirement"]] = relationship(
        back_populates="framework", order_by="Requirement.order"
    )


class Requirement(Base):
    __tablename__ = "requirements"
    __table_args__ = (UniqueConstraint("framework_id", "ref"),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uid)
    framework_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("frameworks.id", ondelete="CASCADE"))
    ref: Mapped[str] = mapped_column(String(50))
    section: Mapped[str] = mapped_column(String(200), default="")
    title: Mapped[str] = mapped_column(String(300))
    guidance: Mapped[str] = mapped_column(Text, default="")
    # Org profile flag that must be true for this requirement to apply (None = always applies).
    condition: Mapped[str | None] = mapped_column(String(50), nullable=True)
    order: Mapped[int] = mapped_column(Integer, default=0)

    framework: Mapped[Framework] = relationship(back_populates="requirements")
    mappings: Mapped[list["Mapping"]] = relationship(back_populates="requirement")


class ControlTemplate(Base):
    __tablename__ = "control_templates"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uid)
    code: Mapped[str] = mapped_column(String(20), unique=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(100))
    frequency: Mapped[str] = mapped_column(String(20))
    evidence_hint: Mapped[str] = mapped_column(Text, default="")
    automatable: Mapped[bool] = mapped_column(Boolean, default=False)

    mappings: Mapped[list["Mapping"]] = relationship(back_populates="control_template")


class Mapping(Base):
    __tablename__ = "mappings"
    __table_args__ = (UniqueConstraint("requirement_id", "control_template_id"),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uid)
    requirement_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("requirements.id", ondelete="CASCADE"))
    control_template_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("control_templates.id", ondelete="CASCADE"))
    coverage: Mapped[str] = mapped_column(String(20), default="full")

    requirement: Mapped[Requirement] = relationship(back_populates="mappings")
    control_template: Mapped[ControlTemplate] = relationship(back_populates="mappings")


class PolicyTemplate(Base):
    __tablename__ = "policy_templates"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uid)
    slug: Mapped[str] = mapped_column(String(100), unique=True)
    title: Mapped[str] = mapped_column(String(200))
    body_md: Mapped[str] = mapped_column(Text)
    control_codes: Mapped[list] = mapped_column(JSON, default=list)
    review_months: Mapped[int] = mapped_column(Integer, default=12)


# --------------------------------------------------------------------------------------
# Identity and tenancy
# --------------------------------------------------------------------------------------


class User(TimestampMixin, Base):
    __tablename__ = "users"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uid)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(200))
    password_hash: Mapped[str] = mapped_column(String(300))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    memberships: Mapped[list["Membership"]] = relationship(back_populates="user")


class Organization(TimestampMixin, Base):
    __tablename__ = "organizations"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uid)
    name: Mapped[str] = mapped_column(String(200))
    sector: Mapped[str] = mapped_column(String(100), default="")
    employee_count: Mapped[str] = mapped_column(String(50), default="")
    country: Mapped[str] = mapped_column(String(2), default="IN")
    # Applicability flags, e.g. processes_children_data, is_significant_data_fiduciary,
    # uses_consent_manager, is_infra_provider, is_virtual_asset_provider.
    profile: Mapped[dict] = mapped_column(JSON, default=dict)
    onboarded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Internal target for responding to data principal requests (law caps grievances at 90 days).
    rights_request_sla_days: Mapped[int] = mapped_column(Integer, default=30)

    memberships: Mapped[list["Membership"]] = relationship(back_populates="organization")


ROLES = ("owner", "admin", "member", "auditor")


class Membership(TimestampMixin, Base):
    __tablename__ = "memberships"
    __table_args__ = (UniqueConstraint("user_id", "org_id"),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uid)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(20), default="member")

    user: Mapped[User] = relationship(back_populates="memberships")
    organization: Mapped[Organization] = relationship(back_populates="memberships")


class Invitation(TimestampMixin, Base):
    __tablename__ = "invitations"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uid)
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    email: Mapped[str] = mapped_column(String(320))
    role: Mapped[str] = mapped_column(String(20))
    token_hash: Mapped[str] = mapped_column(String(128), unique=True)
    invited_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class OrgFramework(TimestampMixin, Base):
    __tablename__ = "org_frameworks"
    __table_args__ = (UniqueConstraint("org_id", "framework_id"),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uid)
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    framework_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("frameworks.id", ondelete="CASCADE"))
    target_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    framework: Mapped[Framework] = relationship()


# --------------------------------------------------------------------------------------
# Controls, evidence, tasks
# --------------------------------------------------------------------------------------

CONTROL_STATUSES = ("not_started", "in_progress", "implemented", "not_applicable")


class Control(TimestampMixin, Base):
    __tablename__ = "controls"
    __table_args__ = (UniqueConstraint("org_id", "code"),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uid)
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    template_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("control_templates.id", ondelete="SET NULL"))
    code: Mapped[str] = mapped_column(String(20))
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    category: Mapped[str] = mapped_column(String(100), default="Custom")
    frequency: Mapped[str] = mapped_column(String(20), default="annual")
    status: Mapped[str] = mapped_column(String(20), default="not_started")
    owner_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    implementation_notes: Mapped[str] = mapped_column(Text, default="")
    na_justification: Mapped[str] = mapped_column(Text, default="")
    next_review_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    template: Mapped[ControlTemplate | None] = relationship()
    owner: Mapped[User | None] = relationship()


class Evidence(TimestampMixin, Base):
    __tablename__ = "evidence"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uid)
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    control_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("controls.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text, default="")
    kind: Mapped[str] = mapped_column(String(20))  # file | link | note | automated | policy
    source: Mapped[str] = mapped_column(String(50), default="manual")  # manual | integration:<provider> | policy
    url: Mapped[str] = mapped_column(String(1000), default="")
    file_key: Mapped[str] = mapped_column(String(500), default="")
    file_name: Mapped[str] = mapped_column(String(300), default="")
    content_type: Mapped[str] = mapped_column(String(100), default="")
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    valid_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    uploaded_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))

    uploaded_by: Mapped[User | None] = relationship()


TASK_STATUSES = ("open", "in_progress", "done")


class Task(TimestampMixin, Base):
    __tablename__ = "tasks"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uid)
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text, default="")
    control_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("controls.id", ondelete="SET NULL"))
    assignee_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="open")
    priority: Mapped[str] = mapped_column(String(10), default="medium")
    source: Mapped[str] = mapped_column(String(50), default="manual")  # manual | test:<key>
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    control: Mapped[Control | None] = relationship()
    assignee: Mapped[User | None] = relationship()


# --------------------------------------------------------------------------------------
# Policies
# --------------------------------------------------------------------------------------


class Policy(TimestampMixin, Base):
    __tablename__ = "policies"
    __table_args__ = (UniqueConstraint("org_id", "slug"),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uid)
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    slug: Mapped[str] = mapped_column(String(100))
    title: Mapped[str] = mapped_column(String(200))
    body_md: Mapped[str] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(20), default="draft")  # draft | approved
    control_codes: Mapped[list] = mapped_column(JSON, default=list)
    owner_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    approved_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    review_due: Mapped[date | None] = mapped_column(Date, nullable=True)

    owner: Mapped[User | None] = relationship(foreign_keys=[owner_id])
    approved_by: Mapped[User | None] = relationship(foreign_keys=[approved_by_id])


class PolicyAcknowledgment(Base):
    __tablename__ = "policy_acknowledgments"
    __table_args__ = (UniqueConstraint("policy_id", "user_id", "version"),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uid)
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    policy_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("policies.id", ondelete="CASCADE"))
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    version: Mapped[int] = mapped_column(Integer)
    acknowledged_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


# --------------------------------------------------------------------------------------
# Risks and vendors
# --------------------------------------------------------------------------------------


class Risk(TimestampMixin, Base):
    __tablename__ = "risks"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uid)
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text, default="")
    category: Mapped[str] = mapped_column(String(100), default="")
    likelihood: Mapped[int] = mapped_column(Integer, default=3)  # 1..5
    impact: Mapped[int] = mapped_column(Integer, default=3)  # 1..5
    treatment: Mapped[str] = mapped_column(String(20), default="mitigate")  # mitigate|accept|transfer|avoid
    treatment_plan: Mapped[str] = mapped_column(Text, default="")
    residual_likelihood: Mapped[int | None] = mapped_column(Integer, nullable=True)
    residual_impact: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="open")  # open | treated | closed
    owner_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    control_codes: Mapped[list] = mapped_column(JSON, default=list)
    review_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    owner: Mapped[User | None] = relationship()


class Vendor(TimestampMixin, Base):
    __tablename__ = "vendors"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uid)
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    website: Mapped[str] = mapped_column(String(300), default="")
    services: Mapped[str] = mapped_column(Text, default="")
    tier: Mapped[str] = mapped_column(String(20), default="medium")  # critical|high|medium|low
    data_shared: Mapped[list] = mapped_column(JSON, default=list)
    is_processor: Mapped[bool] = mapped_column(Boolean, default=False)
    dpa_signed: Mapped[bool] = mapped_column(Boolean, default=False)
    data_location: Mapped[str] = mapped_column(String(200), default="")
    certifications: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(20), default="active")  # onboarding|active|offboarded
    owner_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    last_assessed_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    next_review_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="")

    owner: Mapped[User | None] = relationship()


# --------------------------------------------------------------------------------------
# DPDP module
# --------------------------------------------------------------------------------------


class DataAsset(TimestampMixin, Base):
    """A personal data processing activity (record of processing)."""

    __tablename__ = "data_assets"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uid)
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    systems: Mapped[list] = mapped_column(JSON, default=list)
    data_principals: Mapped[list] = mapped_column(JSON, default=list)  # customers, employees, ...
    data_categories: Mapped[list] = mapped_column(JSON, default=list)
    purposes: Mapped[str] = mapped_column(Text, default="")
    lawful_ground: Mapped[str] = mapped_column(String(30), default="consent")  # consent | legitimate_use
    legitimate_use: Mapped[str] = mapped_column(String(200), default="")
    retention_period: Mapped[str] = mapped_column(String(200), default="")
    processors: Mapped[list] = mapped_column(JSON, default=list)  # vendor names
    cross_border: Mapped[bool] = mapped_column(Boolean, default=False)
    transfer_countries: Mapped[list] = mapped_column(JSON, default=list)
    includes_children_data: Mapped[bool] = mapped_column(Boolean, default=False)
    owner_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    last_reviewed_at: Mapped[date | None] = mapped_column(Date, nullable=True)

    owner: Mapped[User | None] = relationship()


RIGHTS_REQUEST_TYPES = ("access", "correction", "erasure", "grievance", "nomination", "consent_withdrawal")
RIGHTS_REQUEST_STATUSES = ("new", "verifying", "in_progress", "completed", "rejected")


class RightsRequest(TimestampMixin, Base):
    __tablename__ = "rights_requests"
    __table_args__ = (UniqueConstraint("org_id", "number"),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uid)
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    number: Mapped[int] = mapped_column(Integer)
    request_type: Mapped[str] = mapped_column(String(30))
    requester_name: Mapped[str] = mapped_column(String(200))
    requester_email: Mapped[str] = mapped_column(String(320))
    details: Mapped[str] = mapped_column(Text, default="")
    channel: Mapped[str] = mapped_column(String(50), default="email")
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    legal_due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    identity_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(20), default="new")
    assignee_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    resolution: Mapped[str] = mapped_column(Text, default="")
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    assignee: Mapped[User | None] = relationship()


INCIDENT_STATUSES = ("open", "contained", "resolved", "closed")


class Incident(TimestampMixin, Base):
    __tablename__ = "incidents"
    __table_args__ = (UniqueConstraint("org_id", "number"),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uid)
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    number: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text, default="")
    severity: Mapped[str] = mapped_column(String(10), default="sev3")  # sev1|sev2|sev3
    category: Mapped[str] = mapped_column(String(100), default="")
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), default="open")
    lead_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))

    # CERT-In: report within 6 hours of noticing.
    certin_reportable: Mapped[bool] = mapped_column(Boolean, default=False)
    certin_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    certin_reported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # DPDP: personal data breach -> Board (without delay + detailed report within 72h) and Data Principals.
    personal_data_breach: Mapped[bool] = mapped_column(Boolean, default=False)
    affected_principals_estimate: Mapped[int | None] = mapped_column(Integer, nullable=True)
    dpb_initial_reported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    dpb_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    dpb_detailed_reported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    principals_notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    root_cause: Mapped[str] = mapped_column(Text, default="")
    actions_taken: Mapped[str] = mapped_column(Text, default="")
    lessons_learned: Mapped[str] = mapped_column(Text, default="")
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    lead: Mapped[User | None] = relationship()


# --------------------------------------------------------------------------------------
# Integrations
# --------------------------------------------------------------------------------------


class Integration(TimestampMixin, Base):
    __tablename__ = "integrations"
    __table_args__ = (UniqueConstraint("org_id", "provider"),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uid)
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    provider: Mapped[str] = mapped_column(String(50))
    config: Mapped[dict] = mapped_column(JSON, default=dict)  # non-secret settings
    secret_encrypted: Mapped[str] = mapped_column(Text, default="")  # Fernet-encrypted JSON
    status: Mapped[str] = mapped_column(String(20), default="connected")  # connected | error | disabled
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str] = mapped_column(Text, default="")


class TestResult(Base):
    __test__ = False  # not a pytest test class
    __tablename__ = "test_results"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uid)
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    integration_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("integrations.id", ondelete="CASCADE"))
    test_key: Mapped[str] = mapped_column(String(100))
    title: Mapped[str] = mapped_column(String(300))
    status: Mapped[str] = mapped_column(String(10))  # pass | fail | error
    control_codes: Mapped[list] = mapped_column(JSON, default=list)
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


# --------------------------------------------------------------------------------------
# Audit log
# --------------------------------------------------------------------------------------


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uid)
    org_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    action: Mapped[str] = mapped_column(String(100))
    entity_type: Mapped[str] = mapped_column(String(50), default="")
    entity_id: Mapped[str] = mapped_column(String(64), default="")
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    ip: Mapped[str] = mapped_column(String(64), default="")
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)

    user: Mapped[User | None] = relationship()
