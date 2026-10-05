import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


Role = Literal["owner", "admin", "member", "auditor"]


# ---------------------------------------------------------------- auth / users


class SignupIn(BaseModel):
    full_name: str = Field(min_length=1, max_length=200)
    email: EmailStr
    password: str = Field(min_length=10, max_length=200)
    org_name: str = Field(min_length=1, max_length=200)


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class UserBrief(ORM):
    id: uuid.UUID
    full_name: str
    email: str


class MembershipOut(BaseModel):
    org_id: uuid.UUID
    org_name: str
    role: Role


class MeOut(BaseModel):
    user: UserBrief
    org_id: uuid.UUID | None
    role: Role | None
    memberships: list[MembershipOut]
    onboarded: bool


class SwitchOrgIn(BaseModel):
    org_id: uuid.UUID


class InviteIn(BaseModel):
    email: EmailStr
    role: Role = "member"


class AcceptInviteIn(BaseModel):
    token: str
    full_name: str | None = None
    password: str | None = Field(default=None, min_length=10, max_length=200)


class MemberOut(BaseModel):
    user: UserBrief
    role: Role
    joined_at: datetime


class RoleIn(BaseModel):
    role: Role


# ---------------------------------------------------------------- organisation


class OrgOut(ORM):
    id: uuid.UUID
    name: str
    sector: str
    employee_count: str
    country: str
    profile: dict
    onboarded_at: datetime | None
    rights_request_sla_days: int


class OrgUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    sector: str | None = None
    employee_count: str | None = None
    profile: dict[str, bool] | None = None
    rights_request_sla_days: int | None = Field(default=None, ge=1, le=90)


class OnboardingIn(BaseModel):
    sector: str
    employee_count: str
    profile: dict[str, bool] = {}
    framework_codes: list[str] = Field(min_length=1)
    create_policies: bool = True


# ---------------------------------------------------------------- frameworks / controls


class ControlOut(BaseModel):
    id: uuid.UUID
    code: str
    title: str
    description: str
    category: str
    frequency: str
    status: str
    health: str
    owner: UserBrief | None
    next_review_date: date | None
    valid_evidence: int
    total_evidence: int
    frameworks: list[str]
    automatable: bool
    failing_tests: list[str]


class ControlUpdate(BaseModel):
    status: Literal["not_started", "in_progress", "implemented", "not_applicable"] | None = None
    owner_id: uuid.UUID | None = None
    implementation_notes: str | None = None
    na_justification: str | None = None
    next_review_date: date | None = None
    clear_owner: bool = False


class ControlCreate(BaseModel):
    code: str = Field(min_length=2, max_length=20, pattern=r"^[A-Z0-9-]+$")
    title: str = Field(min_length=1, max_length=200)
    description: str = ""
    category: str = "Custom"
    frequency: Literal["once", "continuous", "monthly", "quarterly", "semiannual", "annual"] = "annual"


class EvidenceOut(ORM):
    id: uuid.UUID
    control_id: uuid.UUID
    title: str
    description: str
    kind: str
    source: str
    url: str
    file_name: str
    size_bytes: int
    collected_at: datetime
    valid_until: date | None
    uploaded_by: UserBrief | None
    data: dict


# ---------------------------------------------------------------- tasks


class TaskIn(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    description: str = ""
    control_id: uuid.UUID | None = None
    assignee_id: uuid.UUID | None = None
    due_date: date | None = None
    priority: Literal["low", "medium", "high"] = "medium"


class TaskUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=300)
    description: str | None = None
    assignee_id: uuid.UUID | None = None
    due_date: date | None = None
    priority: Literal["low", "medium", "high"] | None = None
    status: Literal["open", "in_progress", "done"] | None = None


class TaskOut(ORM):
    id: uuid.UUID
    title: str
    description: str
    control_id: uuid.UUID | None
    control_code: str | None = None
    assignee: UserBrief | None
    due_date: date | None
    status: str
    priority: str
    source: str
    created_at: datetime
    completed_at: datetime | None


# ---------------------------------------------------------------- policies


class PolicyOut(ORM):
    id: uuid.UUID
    slug: str
    title: str
    body_md: str
    version: int
    status: str
    control_codes: list[str]
    owner: UserBrief | None
    approved_by: UserBrief | None
    approved_at: datetime | None
    review_due: date | None
    updated_at: datetime
    acknowledged_count: int = 0
    member_count: int = 0
    acknowledged_by_me: bool = False


class PolicyIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    body_md: str = ""
    control_codes: list[str] = []


class PolicyUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    body_md: str | None = None
    owner_id: uuid.UUID | None = None
    control_codes: list[str] | None = None


class FromTemplateIn(BaseModel):
    slug: str


# ---------------------------------------------------------------- risks / vendors


class RiskIn(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    description: str = ""
    category: str = ""
    likelihood: int = Field(3, ge=1, le=5)
    impact: int = Field(3, ge=1, le=5)
    treatment: Literal["mitigate", "accept", "transfer", "avoid"] = "mitigate"
    treatment_plan: str = ""
    residual_likelihood: int | None = Field(default=None, ge=1, le=5)
    residual_impact: int | None = Field(default=None, ge=1, le=5)
    status: Literal["open", "treated", "closed"] = "open"
    owner_id: uuid.UUID | None = None
    control_codes: list[str] = []
    review_date: date | None = None


class RiskOut(ORM):
    id: uuid.UUID
    title: str
    description: str
    category: str
    likelihood: int
    impact: int
    score: int = 0
    treatment: str
    treatment_plan: str
    residual_likelihood: int | None
    residual_impact: int | None
    status: str
    owner: UserBrief | None
    control_codes: list[str]
    review_date: date | None
    created_at: datetime


class VendorIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    website: str = ""
    services: str = ""
    tier: Literal["critical", "high", "medium", "low"] = "medium"
    data_shared: list[str] = []
    is_processor: bool = False
    dpa_signed: bool = False
    data_location: str = ""
    certifications: list[str] = []
    status: Literal["onboarding", "active", "offboarded"] = "active"
    owner_id: uuid.UUID | None = None
    last_assessed_at: date | None = None
    next_review_date: date | None = None
    notes: str = ""


class VendorOut(VendorIn, ORM):
    id: uuid.UUID
    owner: UserBrief | None
    created_at: datetime
    owner_id: uuid.UUID | None = None


# ---------------------------------------------------------------- DPDP


class DataAssetIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = ""
    systems: list[str] = []
    data_principals: list[str] = []
    data_categories: list[str] = []
    purposes: str = ""
    lawful_ground: Literal["consent", "legitimate_use"] = "consent"
    legitimate_use: str = ""
    retention_period: str = ""
    processors: list[str] = []
    cross_border: bool = False
    transfer_countries: list[str] = []
    includes_children_data: bool = False
    owner_id: uuid.UUID | None = None
    last_reviewed_at: date | None = None


class DataAssetOut(DataAssetIn, ORM):
    id: uuid.UUID
    owner: UserBrief | None
    created_at: datetime
    updated_at: datetime


RequestType = Literal["access", "correction", "erasure", "grievance", "nomination", "consent_withdrawal"]


class RightsRequestIn(BaseModel):
    request_type: RequestType
    requester_name: str = Field(min_length=1, max_length=200)
    requester_email: EmailStr
    details: str = ""
    channel: str = "email"
    received_at: datetime | None = None
    assignee_id: uuid.UUID | None = None


class RightsRequestUpdate(BaseModel):
    status: Literal["new", "verifying", "in_progress", "completed", "rejected"] | None = None
    identity_verified: bool | None = None
    assignee_id: uuid.UUID | None = None
    resolution: str | None = None
    details: str | None = None


class RightsRequestOut(ORM):
    id: uuid.UUID
    number: int
    request_type: str
    requester_name: str
    requester_email: str
    details: str
    channel: str
    received_at: datetime
    due_at: datetime
    legal_due_at: datetime
    identity_verified: bool
    status: str
    assignee: UserBrief | None
    resolution: str
    closed_at: datetime | None


class IncidentIn(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    description: str = ""
    severity: Literal["sev1", "sev2", "sev3"] = "sev3"
    category: str = ""
    detected_at: datetime
    certin_reportable: bool = False
    personal_data_breach: bool = False
    affected_principals_estimate: int | None = None
    lead_id: uuid.UUID | None = None

    @field_validator("detected_at")
    @classmethod
    def tz_required(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("detected_at must include a timezone offset")
        return v


class IncidentUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=300)
    description: str | None = None
    severity: Literal["sev1", "sev2", "sev3"] | None = None
    category: str | None = None
    status: Literal["open", "contained", "resolved", "closed"] | None = None
    certin_reportable: bool | None = None
    personal_data_breach: bool | None = None
    affected_principals_estimate: int | None = None
    lead_id: uuid.UUID | None = None
    certin_reported_at: datetime | None = None
    dpb_initial_reported_at: datetime | None = None
    dpb_detailed_reported_at: datetime | None = None
    principals_notified_at: datetime | None = None
    root_cause: str | None = None
    actions_taken: str | None = None
    lessons_learned: str | None = None


class IncidentOut(ORM):
    id: uuid.UUID
    number: int
    title: str
    description: str
    severity: str
    category: str
    detected_at: datetime
    status: str
    lead: UserBrief | None
    certin_reportable: bool
    certin_due_at: datetime | None
    certin_reported_at: datetime | None
    personal_data_breach: bool
    affected_principals_estimate: int | None
    dpb_initial_reported_at: datetime | None
    dpb_due_at: datetime | None
    dpb_detailed_reported_at: datetime | None
    principals_notified_at: datetime | None
    root_cause: str
    actions_taken: str
    lessons_learned: str
    closed_at: datetime | None
    created_at: datetime


# ---------------------------------------------------------------- integrations


class IntegrationConnectIn(BaseModel):
    config: dict[str, str] = {}
    secrets: dict[str, str] = {}
