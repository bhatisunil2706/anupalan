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
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    password_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # TOTP multi-factor authentication. The secret is Fernet-encrypted; last_timestep blocks code replay.
    mfa_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    mfa_secret_encrypted: Mapped[str] = mapped_column(Text, default="")
    mfa_last_timestep: Mapped[int] = mapped_column(Integer, default=0)
    mfa_enabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

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

    # Notifications. Webhook URLs are secrets, stored encrypted as JSON {"slack": url, "teams": url}.
    notify_email: Mapped[bool] = mapped_column(Boolean, default=True)
    notify_webhooks_encrypted: Mapped[str] = mapped_column(Text, default="")

    # Public DPDP rights-request portal.
    portal_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    portal_slug: Mapped[str | None] = mapped_column(String(60), unique=True, nullable=True)
    privacy_contact_name: Mapped[str] = mapped_column(String(200), default="")
    privacy_contact_email: Mapped[str] = mapped_column(String(320), default="")

    # Security policy
    require_mfa: Mapped[bool] = mapped_column(Boolean, default=False)
    session_idle_minutes: Mapped[int] = mapped_column(Integer, default=120)

    # AI assistant: off until an admin opts in (workspace text is sent to the configured AI provider).
    ai_enabled: Mapped[bool] = mapped_column(Boolean, default=False)

    memberships: Mapped[list["Membership"]] = relationship(back_populates="organization")


ROLES = ("owner", "admin", "member", "auditor")


class Membership(TimestampMixin, Base):
    __tablename__ = "memberships"
    __table_args__ = (UniqueConstraint("user_id", "org_id"),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uid)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(20), default="member")
    # Time-limited access (used for external auditors). Null = no expiry.
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

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
    # For time-limited roles such as external auditors: membership expires at this time.
    access_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


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
    source: Mapped[str] = mapped_column(String(200), default="manual")  # manual | test:<key> | policy:<id> | ...
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
    source: Mapped[str] = mapped_column(String(200), default="manual", index=True)  # manual | test:<key> | ...
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    external_ref: Mapped[str] = mapped_column(String(100), default="", server_default="")  # e.g. Jira issue key
    external_url: Mapped[str] = mapped_column(String(500), default="", server_default="")

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
    # Null for platform checks computed across sources (e.g. leaver access).
    integration_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("integrations.id", ondelete="CASCADE"), nullable=True
    )
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
    user_agent: Mapped[str] = mapped_column(String(300), default="")
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    # Tamper evidence: each entry's hash covers its content and the previous entry's hash (per organisation).
    seq: Mapped[int] = mapped_column(Integer, default=0)
    prev_hash: Mapped[str] = mapped_column(String(64), default="")
    hash: Mapped[str] = mapped_column(String(64), default="")

    user: Mapped[User | None] = relationship()


# --------------------------------------------------------------------------------------
# Notifications (also the delivery outbox)
# --------------------------------------------------------------------------------------


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (UniqueConstraint("org_id", "dedupe_key"),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uid)
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    dedupe_key: Mapped[str] = mapped_column(String(200))
    event: Mapped[str] = mapped_column(String(50))
    title: Mapped[str] = mapped_column(String(300))
    body: Mapped[str] = mapped_column(Text, default="")
    link: Mapped[str] = mapped_column(String(500), default="")
    recipients: Mapped[list] = mapped_column(JSON, default=list)  # email addresses
    broadcast: Mapped[bool] = mapped_column(Boolean, default=False)  # also post to Slack / Teams
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)  # pending | sent | failed
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


# --------------------------------------------------------------------------------------
# People (HR roster) and accounts (identity inventory)
# --------------------------------------------------------------------------------------


class Person(TimestampMixin, Base):
    __tablename__ = "people"
    __table_args__ = (UniqueConstraint("org_id", "email"),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uid)
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    source: Mapped[str] = mapped_column(String(20), default="csv")  # csv | keka
    employee_id: Mapped[str] = mapped_column(String(100), default="")
    email: Mapped[str] = mapped_column(String(320))
    full_name: Mapped[str] = mapped_column(String(200), default="")
    department: Mapped[str] = mapped_column(String(200), default="")
    title: Mapped[str] = mapped_column(String(200), default="")
    manager_email: Mapped[str] = mapped_column(String(320), default="")
    status: Mapped[str] = mapped_column(String(20), default="active")  # active | exited
    join_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    exit_date: Mapped[date | None] = mapped_column(Date, nullable=True)


class Account(Base):
    __tablename__ = "accounts"
    __table_args__ = (UniqueConstraint("org_id", "provider", "external_id"),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uid)
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    integration_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("integrations.id", ondelete="CASCADE"))
    provider: Mapped[str] = mapped_column(String(50))
    external_id: Mapped[str] = mapped_column(String(300))
    email: Mapped[str] = mapped_column(String(320), default="", index=True)
    name: Mapped[str] = mapped_column(String(300), default="")
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    mfa_enabled: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


# --------------------------------------------------------------------------------------
# Access reviews
# --------------------------------------------------------------------------------------


class AccessReview(TimestampMixin, Base):
    __tablename__ = "access_reviews"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uid)
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    providers: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(20), default="open")  # open | completed
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_by: Mapped[User | None] = relationship()
    items: Mapped[list["AccessReviewItem"]] = relationship(back_populates="review", cascade="all, delete-orphan")


class AccessReviewItem(Base):
    __tablename__ = "access_review_items"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uid)
    review_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("access_reviews.id", ondelete="CASCADE"), index=True)
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    account_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("accounts.id", ondelete="SET NULL"))
    provider: Mapped[str] = mapped_column(String(50))
    external_id: Mapped[str] = mapped_column(String(300))
    email: Mapped[str] = mapped_column(String(320), default="")
    name: Mapped[str] = mapped_column(String(300), default="")
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    person_status: Mapped[str] = mapped_column(String(20), default="unknown")  # active | exited | unknown
    reviewer_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    decision: Mapped[str] = mapped_column(String(20), default="pending")  # pending | keep | revoke
    note: Mapped[str] = mapped_column(Text, default="")
    decided_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    removal_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    review: Mapped[AccessReview] = relationship(back_populates="items")
    reviewer: Mapped[User | None] = relationship(foreign_keys=[reviewer_id])
    decided_by: Mapped[User | None] = relationship(foreign_keys=[decided_by_id])


# --------------------------------------------------------------------------------------
# Public portal verification
# --------------------------------------------------------------------------------------


class PortalVerification(Base):
    __tablename__ = "portal_verifications"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uid)
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(128), unique=True)
    email: Mapped[str] = mapped_column(String(320))
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    ip: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


# --------------------------------------------------------------------------------------
# Personal data discovery
# --------------------------------------------------------------------------------------


class DataSource(TimestampMixin, Base):
    __tablename__ = "data_sources"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uid)
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(20))  # postgres | mysql | s3
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    secret_encrypted: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="new")  # new | scanned | error
    last_scan_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str] = mapped_column(Text, default="")
    stats: Mapped[dict] = mapped_column(JSON, default=dict)


class PiiFinding(Base):
    __tablename__ = "pii_findings"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uid)
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("data_sources.id", ondelete="CASCADE"), index=True)
    container: Mapped[str] = mapped_column(String(500))  # schema.table or s3 key
    field: Mapped[str] = mapped_column(String(300), default="")  # column name ("" for files)
    category: Mapped[str] = mapped_column(String(50))
    matches: Mapped[int] = mapped_column(Integer, default=0)
    sampled: Mapped[int] = mapped_column(Integer, default=0)
    by_name_only: Mapped[bool] = mapped_column(Boolean, default=False)
    examples: Mapped[list] = mapped_column(JSON, default=list)  # masked values only, never raw
    scanned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AuditChainHead(Base):
    """Latest sequence number and hash per audit chain (one per organisation, plus "system").

    Holds no sensitive data, so it is outside row-level security and serialises writers with FOR UPDATE.
    """

    __tablename__ = "audit_chain_heads"
    chain_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    seq: Mapped[int] = mapped_column(Integer, default=0)
    hash: Mapped[str] = mapped_column(String(64))


# --------------------------------------------------------------------------------------
# Authentication and account security
# --------------------------------------------------------------------------------------


class UserSession(Base):
    """Server-side session. The cookie holds a random token; only its SHA-256 is stored."""

    __tablename__ = "user_sessions"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uid)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    org_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("organizations.id", ondelete="SET NULL"))
    stage: Mapped[str] = mapped_column(String(20), default="full")  # mfa | full
    auth_method: Mapped[str] = mapped_column(String(20), default="password")  # password | sso
    mfa_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    mfa_attempts: Mapped[int] = mapped_column(Integer, default=0)
    ip: Mapped[str] = mapped_column(String(64), default="")
    user_agent: Mapped[str] = mapped_column(String(300), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped[User] = relationship()


class AuthToken(Base):
    """Single-use tokens: email verification, password reset, SSO state. Only the hash is stored."""

    __tablename__ = "auth_tokens"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uid)
    purpose: Mapped[str] = mapped_column(String(30), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    org_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"),
                                                     nullable=True)
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class RecoveryCode(Base):
    __tablename__ = "mfa_recovery_codes"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uid)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    code_hash: Mapped[str] = mapped_column(String(64))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class OrgDomain(TimestampMixin, Base):
    """Email domain claimed by an organisation; must be proven with a DNS TXT record before SSO can use it."""

    __tablename__ = "org_domains"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uid)
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    domain: Mapped[str] = mapped_column(String(253))
    verification_token: Mapped[str] = mapped_column(String(64))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SsoConfig(TimestampMixin, Base):
    __tablename__ = "sso_configs"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uid)
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), unique=True)
    provider: Mapped[str] = mapped_column(String(20))  # google | microsoft | okta | oidc
    issuer: Mapped[str] = mapped_column(String(500))
    client_id: Mapped[str] = mapped_column(String(300))
    client_secret_encrypted: Mapped[str] = mapped_column(Text, default="")
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    enforced: Mapped[bool] = mapped_column(Boolean, default=False)  # block password sign-in (owners exempt)
    jit_provisioning: Mapped[bool] = mapped_column(Boolean, default=False)
    default_role: Mapped[str] = mapped_column(String(20), default="member")


class ApiKey(Base):
    """Organisation API key for machine access (consent API, self-hosted scanner)."""

    __tablename__ = "api_keys"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uid)
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    prefix: Mapped[str] = mapped_column(String(20))
    key_hash: Mapped[str] = mapped_column(String(64), unique=True)
    scopes: Mapped[list] = mapped_column(JSON, default=list)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


# --------------------------------------------------------------------------------------
# DPDP consent records
# --------------------------------------------------------------------------------------


class ConsentNotice(TimestampMixin, Base):
    """A versioned privacy notice / consent request shown to data principals. Published versions are immutable."""

    __tablename__ = "consent_notices"
    __table_args__ = (UniqueConstraint("org_id", "key", "version"),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uid)
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    key: Mapped[str] = mapped_column(String(60))
    version: Mapped[int] = mapped_column(Integer, default=1)
    title: Mapped[str] = mapped_column(String(200))
    body_md: Mapped[str] = mapped_column(Text, default="")
    # [{"id": "marketing", "label": "...", "description": "...", "required": false}]
    purposes: Mapped[list] = mapped_column(JSON, default=list)
    languages: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(20), default="draft")  # draft | published | retired
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ConsentEvent(Base):
    """Append-only log of consent given, updated or withdrawn by a data principal (DPDP s.6)."""

    __tablename__ = "consent_events"
    __table_args__ = (UniqueConstraint("org_id", "event_id"),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uid)
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    event_id: Mapped[str] = mapped_column(String(100))  # idempotency key from the caller
    principal_id: Mapped[str] = mapped_column(String(200), index=True)  # the customer's own user identifier
    notice_key: Mapped[str] = mapped_column(String(60))
    notice_version: Mapped[int] = mapped_column(Integer)
    action: Mapped[str] = mapped_column(String(20))  # granted | withdrawn
    purposes: Mapped[list] = mapped_column(JSON, default=list)
    source: Mapped[str] = mapped_column(String(30), default="api")  # web | app | api | import | consent_manager
    language: Mapped[str] = mapped_column(String(10), default="en")
    consent_manager_ref: Mapped[str] = mapped_column(String(200), default="")
    metadata_: Mapped[dict] = mapped_column("metadata", JSON, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


# --------------------------------------------------------------------------------------
# Security awareness training
# --------------------------------------------------------------------------------------


class TrainingCourse(Base):
    """Built-in course (global content)."""

    __tablename__ = "training_courses"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uid)
    slug: Mapped[str] = mapped_column(String(80), unique=True)
    title: Mapped[str] = mapped_column(String(200))
    summary: Mapped[str] = mapped_column(Text, default="")
    minutes: Mapped[int] = mapped_column(Integer, default=10)
    body_md: Mapped[str] = mapped_column(Text)
    quiz: Mapped[list] = mapped_column(JSON, default=list)  # [{"q", "options": [...], "answer": index}]
    pass_mark: Mapped[int] = mapped_column(Integer, default=80)
    control_codes: Mapped[list] = mapped_column(JSON, default=list)


class TrainingAssignment(TimestampMixin, Base):
    __tablename__ = "training_assignments"
    __table_args__ = (UniqueConstraint("org_id", "course_slug"),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uid)
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    course_slug: Mapped[str] = mapped_column(String(80))
    required: Mapped[bool] = mapped_column(Boolean, default=True)
    renew_months: Mapped[int] = mapped_column(Integer, default=12)
    due_days: Mapped[int] = mapped_column(Integer, default=30)


class TrainingCompletion(Base):
    __tablename__ = "training_completions"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uid)
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    course_slug: Mapped[str] = mapped_column(String(80))
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    email: Mapped[str] = mapped_column(String(320), index=True)
    score: Mapped[int] = mapped_column(Integer, default=0)
    passed: Mapped[bool] = mapped_column(Boolean, default=False)
    source: Mapped[str] = mapped_column(String(20), default="platform")  # platform | import
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


# --------------------------------------------------------------------------------------
# Vendor due diligence
# --------------------------------------------------------------------------------------


class QuestionnaireTemplate(Base):
    """Built-in vendor questionnaire (global content)."""

    __tablename__ = "questionnaire_templates"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uid)
    slug: Mapped[str] = mapped_column(String(80), unique=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    # [{"id", "section", "text", "type": "yes_no"|"text", "weight", "good": "yes"|"no", "evidence": bool}]
    questions: Mapped[list] = mapped_column(JSON, default=list)


class VendorAssessment(TimestampMixin, Base):
    __tablename__ = "vendor_assessments"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uid)
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    vendor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("vendors.id", ondelete="CASCADE"), index=True)
    template_slug: Mapped[str] = mapped_column(String(80))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    sent_to_email: Mapped[str] = mapped_column(String(320))
    status: Mapped[str] = mapped_column(String(20), default="sent")  # sent | in_progress | submitted | reviewed
    answers: Mapped[dict] = mapped_column(JSON, default=dict)
    respondent_name: Mapped[str] = mapped_column(String(200), default="")
    score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rating: Mapped[str] = mapped_column(String(10), default="")  # low | medium | high (risk)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewed_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewer_notes: Mapped[str] = mapped_column(Text, default="")
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


class VendorDocument(Base):
    __tablename__ = "vendor_documents"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uid)
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    vendor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("vendors.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(30))  # iso27001 | soc2 | dpa | pentest | insurance | other
    title: Mapped[str] = mapped_column(String(300))
    file_key: Mapped[str] = mapped_column(String(500))
    file_name: Mapped[str] = mapped_column(String(300))
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    valid_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    uploaded_via: Mapped[str] = mapped_column(String(20), default="staff")  # staff | vendor_portal
    uploaded_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


# --------------------------------------------------------------------------------------
# Auditor workspace
# --------------------------------------------------------------------------------------


class EvidenceRequest(TimestampMixin, Base):
    __tablename__ = "evidence_requests"
    __table_args__ = (UniqueConstraint("org_id", "number"),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uid)
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    number: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text, default="")
    framework_code: Mapped[str] = mapped_column(String(50), default="")
    requirement_ref: Mapped[str] = mapped_column(String(50), default="")
    control_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("controls.id", ondelete="SET NULL"))
    requested_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    assignee_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="open")  # open | submitted | accepted | rejected
    evidence_ids: Mapped[list] = mapped_column(JSON, default=list)

    control: Mapped[Control | None] = relationship()
    requested_by: Mapped[User | None] = relationship(foreign_keys=[requested_by_id])
    assignee: Mapped[User | None] = relationship(foreign_keys=[assignee_id])


class RequestComment(Base):
    __tablename__ = "request_comments"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uid)
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    request_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("evidence_requests.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    user: Mapped[User | None] = relationship()


# --------------------------------------------------------------------------------------
# AI assistant
# --------------------------------------------------------------------------------------


class AiJob(TimestampMixin, Base):
    __tablename__ = "ai_jobs"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uid)
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(30))  # policy_draft | gap_analysis | questionnaire
    title: Mapped[str] = mapped_column(String(300), default="")
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)  # pending|running|done|failed
    input: Mapped[dict] = mapped_column(JSON, default=dict)
    output: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str] = mapped_column(Text, default="")
    tokens_in: Mapped[int] = mapped_column(Integer, default=0)
    tokens_out: Mapped[int] = mapped_column(Integer, default=0)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_by: Mapped[User | None] = relationship()
