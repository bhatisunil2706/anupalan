export type Role = "owner" | "admin" | "member" | "auditor";

export interface UserBrief {
  id: string;
  full_name: string;
  email: string;
}

export interface Me {
  user: UserBrief;
  org_id: string | null;
  role: Role | null;
  memberships: { org_id: string; org_name: string; role: Role }[];
  onboarded: boolean;
}

export interface Org {
  id: string;
  name: string;
  sector: string;
  employee_count: string;
  country: string;
  profile: Record<string, boolean>;
  onboarded_at: string | null;
  rights_request_sla_days: number;
}

export interface Member {
  user: UserBrief;
  role: Role;
  joined_at: string;
}

export type Health = "passing" | "failing" | "needs_evidence" | "in_progress" | "not_started" | "not_applicable";

export interface Control {
  id: string;
  code: string;
  title: string;
  description: string;
  category: string;
  frequency: string;
  status: "not_started" | "in_progress" | "implemented" | "not_applicable";
  health: Health;
  owner: UserBrief | null;
  next_review_date: string | null;
  valid_evidence: number;
  total_evidence: number;
  frameworks: string[];
  automatable: boolean;
  failing_tests: string[];
}

export interface Evidence {
  id: string;
  control_id: string;
  title: string;
  description: string;
  kind: "file" | "link" | "note" | "automated" | "policy";
  source: string;
  url: string;
  file_name: string;
  size_bytes: number;
  collected_at: string;
  valid_until: string | null;
  uploaded_by: UserBrief | null;
  data: Record<string, unknown>;
}

export interface Task {
  id: string;
  title: string;
  description: string;
  control_id: string | null;
  control_code: string | null;
  assignee: UserBrief | null;
  due_date: string | null;
  status: "open" | "in_progress" | "done";
  priority: "low" | "medium" | "high";
  source: string;
  created_at: string;
  completed_at: string | null;
}

export interface Readiness {
  framework_id: string;
  code: string;
  name: string;
  short_name: string;
  region: string;
  total: number;
  met: number;
  partial: number;
  not_applicable_requirements: number;
  percent: number;
}

export interface FrameworkCatalogItem {
  id: string;
  code: string;
  name: string;
  short_name: string;
  version: string;
  region: string;
  publisher: string;
  description: string;
  source_url: string;
  review_status: string;
  requirement_count: number;
  enabled: boolean;
}

export interface RequirementRow {
  id: string;
  ref: string;
  section: string;
  title: string;
  guidance: string;
  condition: string | null;
  status: "met" | "partial" | "not_met" | "not_applicable";
  controls: { id: string; code: string; title: string; health: Health }[];
}

export interface Policy {
  id: string;
  slug: string;
  title: string;
  body_md: string;
  version: number;
  status: "draft" | "approved";
  control_codes: string[];
  owner: UserBrief | null;
  approved_by: UserBrief | null;
  approved_at: string | null;
  review_due: string | null;
  updated_at: string;
  acknowledged_count: number;
  member_count: number;
  acknowledged_by_me: boolean;
}

export interface Risk {
  id: string;
  title: string;
  description: string;
  category: string;
  likelihood: number;
  impact: number;
  score: number;
  treatment: "mitigate" | "accept" | "transfer" | "avoid";
  treatment_plan: string;
  residual_likelihood: number | null;
  residual_impact: number | null;
  status: "open" | "treated" | "closed";
  owner: UserBrief | null;
  control_codes: string[];
  review_date: string | null;
  created_at: string;
}

export interface Vendor {
  id: string;
  name: string;
  website: string;
  services: string;
  tier: "critical" | "high" | "medium" | "low";
  data_shared: string[];
  is_processor: boolean;
  dpa_signed: boolean;
  data_location: string;
  certifications: string[];
  status: "onboarding" | "active" | "offboarded";
  owner: UserBrief | null;
  owner_id: string | null;
  last_assessed_at: string | null;
  next_review_date: string | null;
  notes: string;
}

export interface DataAsset {
  id: string;
  name: string;
  description: string;
  systems: string[];
  data_principals: string[];
  data_categories: string[];
  purposes: string;
  lawful_ground: "consent" | "legitimate_use";
  legitimate_use: string;
  retention_period: string;
  processors: string[];
  cross_border: boolean;
  transfer_countries: string[];
  includes_children_data: boolean;
  owner: UserBrief | null;
  owner_id: string | null;
  last_reviewed_at: string | null;
  updated_at: string;
}

export interface RightsRequest {
  id: string;
  number: number;
  request_type: string;
  requester_name: string;
  requester_email: string;
  details: string;
  channel: string;
  received_at: string;
  due_at: string;
  legal_due_at: string;
  identity_verified: boolean;
  status: "new" | "verifying" | "in_progress" | "completed" | "rejected";
  assignee: UserBrief | null;
  resolution: string;
  closed_at: string | null;
}

export interface Incident {
  id: string;
  number: number;
  title: string;
  description: string;
  severity: "sev1" | "sev2" | "sev3";
  category: string;
  detected_at: string;
  status: "open" | "contained" | "resolved" | "closed";
  lead: UserBrief | null;
  certin_reportable: boolean;
  certin_due_at: string | null;
  certin_reported_at: string | null;
  personal_data_breach: boolean;
  affected_principals_estimate: number | null;
  dpb_initial_reported_at: string | null;
  dpb_due_at: string | null;
  dpb_detailed_reported_at: string | null;
  principals_notified_at: string | null;
  root_cause: string;
  actions_taken: string;
  lessons_learned: string;
  closed_at: string | null;
  created_at: string;
}

export interface IntegrationField {
  name: string;
  label: string;
  secret: boolean;
  required: boolean;
  help: string;
  default: string;
  multiline: boolean;
}

export interface IntegrationItem {
  provider: string;
  name: string;
  description: string;
  category: string;
  setup_help: string;
  beta: boolean;
  provides_accounts: boolean;
  provides_people: boolean;
  fields: IntegrationField[];
  tests: { key: string; title: string; control_codes: string[] }[];
  connection: {
    id: string;
    status: string;
    config: Record<string, string>;
    last_synced_at: string | null;
    last_error: string;
  } | null;
}

export interface ReviewSummary {
  id: string;
  title: string;
  status: "open" | "completed";
  due_date: string | null;
  providers: { provider: string; name: string }[];
  created_by: string | null;
  created_at: string;
  completed_at: string | null;
  total: number;
  pending: number;
  revoked: number;
  kept: number;
  my_pending: number;
  removals_unverified: number;
}
