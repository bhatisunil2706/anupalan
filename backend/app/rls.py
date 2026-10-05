"""PostgreSQL row-level security policies and runtime-role grants.

Applied by migrations (and by the test suite) with an owner role. The application connects with a restricted
runtime role that has no BYPASSRLS, so these policies are enforced on every query it runs.
"""
from sqlalchemy import Connection, text

# Tables with an org_id column that are NOT tenant data (looked up by secret token hash before any tenant is known).
NOT_TENANT_SCOPED = {"auth_tokens", "user_sessions"}
# Global, read-only reference content. The runtime role may only read these.
CONTENT_TABLES = {"frameworks", "requirements", "control_templates", "mappings", "policy_templates",
                  "training_courses", "questionnaire_templates"}
# Append-only tables: the runtime role may insert and read, never update or delete. Consent events are the
# legal record of consent (DPDP s.6(10)), so they get the same protection as the audit log.
APPEND_ONLY = {"audit_logs", "consent_events"}

BYPASS = "current_setting('app.rls_bypass', true) = 'on'"
CUR_ORG = "nullif(current_setting('app.org_id', true), '')::uuid"
CUR_USER = "nullif(current_setting('app.user_id', true), '')::uuid"
DEFAULT = f"({BYPASS} OR org_id = {CUR_ORG})"

SPECIAL: dict[str, tuple[str, str]] = {
    # (USING, WITH CHECK)
    "organizations": (
        f"({BYPASS} OR id = {CUR_ORG} OR EXISTS (SELECT 1 FROM memberships m "  # nosec B608 - constant policy SQL
        f"WHERE m.org_id = organizations.id AND m.user_id = {CUR_USER}))",
        f"({BYPASS} OR id = {CUR_ORG})",
    ),
    "memberships": (f"({BYPASS} OR org_id = {CUR_ORG} OR user_id = {CUR_USER})", DEFAULT),
    # Security events without an organisation (e.g. failed sign-in to an unknown account) may be written
    # without a tenant, but only read with bypass.
    "audit_logs": (DEFAULT, f"({DEFAULT} OR org_id IS NULL)"),
}


def tenant_tables(conn: Connection) -> list[str]:
    rows = conn.execute(text(
        "SELECT table_name FROM information_schema.columns WHERE table_schema = 'public' AND column_name = 'org_id' "
        "UNION SELECT 'organizations' ORDER BY 1")).scalars().all()
    return [t for t in rows if t not in NOT_TENANT_SCOPED]


def apply_policies(conn: Connection) -> list[str]:
    tables = tenant_tables(conn)
    for t in tables:
        using, check = SPECIAL.get(t, (DEFAULT, DEFAULT))
        conn.execute(text(f'ALTER TABLE "{t}" ENABLE ROW LEVEL SECURITY'))
        conn.execute(text(f'ALTER TABLE "{t}" FORCE ROW LEVEL SECURITY'))
        conn.execute(text(f'DROP POLICY IF EXISTS tenant_isolation ON "{t}"'))
        conn.execute(text(f'CREATE POLICY tenant_isolation ON "{t}" USING {using} WITH CHECK {check}'))
    return tables


def ensure_runtime_role(conn: Connection, role: str, password: str) -> bool:
    """Create the runtime login role if this connection may. Returns True if the role exists afterwards."""
    if not role.replace("_", "").isalnum():
        raise ValueError("runtime role name must be alphanumeric/underscore")
    exists = conn.execute(text("SELECT 1 FROM pg_roles WHERE rolname = :r"), {"r": role}).first()
    if exists:
        return True
    can_create = conn.execute(text(
        "SELECT rolsuper OR rolcreaterole FROM pg_roles WHERE rolname = current_user")).scalar()
    if not (can_create and password):
        return False
    # Password is a bind-free literal here because CREATE ROLE doesn't accept parameters; quote it safely.
    quoted = conn.execute(text("SELECT quote_literal(:p)"), {"p": password}).scalar()
    conn.execute(text(f'CREATE ROLE "{role}" LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE '
                      f"PASSWORD {quoted}"))
    return True


def grant_runtime(conn: Connection, role: str) -> None:
    if not conn.execute(text("SELECT 1 FROM pg_roles WHERE rolname = :r"), {"r": role}).first():
        return
    r = f'"{role}"'
    conn.execute(text(f"GRANT USAGE ON SCHEMA public TO {r}"))
    conn.execute(text(f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {r}"))
    conn.execute(text(f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {r}"))
    for t in CONTENT_TABLES:
        conn.execute(text(f'REVOKE INSERT, UPDATE, DELETE ON "{t}" FROM {r}'))
    for t in APPEND_ONLY:
        conn.execute(text(f'REVOKE UPDATE, DELETE, TRUNCATE ON "{t}" FROM {r}'))
    if conn.execute(text("SELECT to_regclass('public.alembic_version')")).scalar():
        conn.execute(text(f"REVOKE ALL ON alembic_version FROM {r}"))


def runtime_role_report(conn: Connection) -> dict:
    """Used at startup to refuse running with a role that would silently bypass RLS."""
    row = conn.execute(text("SELECT current_user, rolsuper, rolbypassrls FROM pg_roles "
                            "WHERE rolname = current_user")).one()
    forced = conn.execute(text("SELECT relforcerowsecurity FROM pg_class WHERE relname = 'controls'")).scalar()
    return {"role": row[0], "superuser": row[1], "bypassrls": row[2], "rls_forced": bool(forced)}
