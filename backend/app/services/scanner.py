"""Scan customer data stores for personal data. Read-only, sampled, and only masked examples are stored."""
import ipaddress
import json
import socket
from datetime import datetime, timezone

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import DataSource, PiiFinding
from app.security import decrypt_json
from app.services.pii import FieldStats, findings_for_field

MAX_TABLES = 300
ROWS_PER_TABLE = 200
MAX_OBJECTS = 200
BYTES_PER_OBJECT = 256 * 1024
TEXT_TYPES_PG = ("character varying", "text", "character", "json", "jsonb", "USER-DEFINED", "date",
                 "bigint", "numeric", "integer")
S3_EXTENSIONS = (".csv", ".json", ".jsonl", ".ndjson", ".txt", ".log", ".tsv")


class ScanError(Exception):
    pass


def check_host_allowed(host: str) -> None:
    s = get_settings()
    allowed = s.allow_private_scan_targets if s.allow_private_scan_targets is not None else not s.is_production
    if allowed:
        return
    try:
        addrs = {ai[4][0] for ai in socket.getaddrinfo(host, None)}
    except socket.gaierror as e:
        raise ScanError(f"Can't resolve host {host}") from e
    for a in addrs:
        ip = ipaddress.ip_address(a)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            raise ScanError("This host is on a private network. Run the scanner inside your network instead.")


# ---------------------------------------------------------------- SQL databases


def _scan_postgres(cfg: dict, secret: dict) -> tuple[list[dict], dict]:
    import psycopg
    from psycopg import sql

    check_host_allowed(cfg["host"])
    conn = psycopg.connect(host=cfg["host"], port=int(cfg.get("port") or 5432), dbname=cfg["database"],
                           user=cfg["username"], password=secret.get("password", ""), connect_timeout=10,
                           sslmode=cfg.get("sslmode") or "prefer", autocommit=True)
    out, tables = [], 0
    with conn:
        conn.execute("SET default_transaction_read_only = on")
        conn.execute("SET statement_timeout = '15s'")
        cols = conn.execute(
            "SELECT table_schema, table_name, column_name, data_type FROM information_schema.columns "
            "WHERE table_schema NOT IN ('pg_catalog', 'information_schema') AND table_schema NOT LIKE 'pg_toast%%' "
            "ORDER BY table_schema, table_name, ordinal_position").fetchall()
        by_table: dict[tuple[str, str], list[tuple[str, str]]] = {}
        for schema, table, col, dtype in cols:
            by_table.setdefault((schema, table), []).append((col, dtype))
        for (schema, table), columns in list(by_table.items())[:MAX_TABLES]:
            tables += 1
            scan_cols = [c for c, t in columns if t in TEXT_TYPES_PG]
            stats = {c: FieldStats() for c, _ in columns}
            if scan_cols:
                q = sql.SQL("SELECT {} FROM {}.{} LIMIT {}").format(
                    sql.SQL(", ").join(sql.Identifier(c) for c in scan_cols), sql.Identifier(schema),
                    sql.Identifier(table), sql.Literal(ROWS_PER_TABLE))
                try:
                    for row in conn.execute(q):
                        for c, v in zip(scan_cols, row, strict=True):
                            stats[c].add(json.dumps(v) if isinstance(v, (dict, list)) else v)
                except psycopg.Error:
                    pass  # no permission on this table; column names are still checked
            for c, st in stats.items():
                for f in findings_for_field(c, st):
                    out.append({"container": f"{schema}.{table}", "field": c, **f})
    return out, {"tables": tables}


def _scan_mysql(cfg: dict, secret: dict) -> tuple[list[dict], dict]:
    import pymysql

    check_host_allowed(cfg["host"])
    conn = pymysql.connect(host=cfg["host"], port=int(cfg.get("port") or 3306), user=cfg["username"],
                           password=secret.get("password", ""), database=cfg["database"], connect_timeout=10,
                           read_timeout=20)
    out, tables = [], 0
    try:
        with conn.cursor() as cur:
            cur.execute("SET SESSION TRANSACTION READ ONLY")
            cur.execute("SELECT table_name, column_name, data_type FROM information_schema.columns "
                        "WHERE table_schema = %s ORDER BY table_name, ordinal_position", (cfg["database"],))
            by_table: dict[str, list[tuple[str, str]]] = {}
            for table, col, dtype in cur.fetchall():
                by_table.setdefault(table, []).append((col, dtype))
            for table, columns in list(by_table.items())[:MAX_TABLES]:
                tables += 1
                text_cols = [c for c, t in columns if t in ("varchar", "text", "char", "json", "mediumtext",
                                                            "longtext", "tinytext", "date", "bigint", "decimal")]
                stats = {c: FieldStats() for c, _ in columns}
                if text_cols:
                    cols_sql = ", ".join(f"`{c.replace('`', '``')}`" for c in text_cols)
                    try:
                        cur.execute(f"SELECT {cols_sql} FROM `{table.replace('`', '``')}` LIMIT {ROWS_PER_TABLE}")  # nosec B608 - identifiers escaped
                        for row in cur.fetchall():
                            for c, v in zip(text_cols, row, strict=True):
                                stats[c].add(v)
                    except pymysql.MySQLError:
                        pass
                for c, st in stats.items():
                    for f in findings_for_field(c, st):
                        out.append({"container": f"{cfg['database']}.{table}", "field": c, **f})
    finally:
        conn.close()
    return out, {"tables": tables}


# ---------------------------------------------------------------- S3


def _values_from_text(name: str, text: str):
    """Yield (field, value) pairs. CSV/JSON keys become fields so column names count as hints."""
    lower = name.lower()
    if lower.endswith((".csv", ".tsv")):
        import csv
        import io

        reader = csv.DictReader(io.StringIO(text), delimiter="\t" if lower.endswith(".tsv") else ",")
        for i, row in enumerate(reader):
            if i >= ROWS_PER_TABLE:
                break
            for k, v in row.items():
                yield (k or "", v)
        return
    if lower.endswith((".json", ".jsonl", ".ndjson")):
        lines = text.splitlines() if not lower.endswith(".json") else [text]
        for line in lines[:ROWS_PER_TABLE]:
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            stack = [obj]
            while stack:
                o = stack.pop()
                if isinstance(o, dict):
                    for k, v in o.items():
                        if isinstance(v, (dict, list)):
                            stack.append(v)
                        else:
                            yield (str(k), v)
                elif isinstance(o, list):
                    stack.extend(o[:ROWS_PER_TABLE])
        return
    for line in text.splitlines()[:2000]:
        yield ("", line)


def _scan_s3(cfg: dict, secret: dict, session=None) -> tuple[list[dict], dict]:
    import boto3

    session = session or boto3.Session(aws_access_key_id=secret.get("access_key_id"),
                                       aws_secret_access_key=secret.get("secret_access_key"),
                                       region_name=cfg.get("region") or "ap-south-1")
    s3 = session.client("s3")
    bucket, prefix = cfg["bucket"], cfg.get("prefix") or ""
    out, objects = [], 0
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            if objects >= MAX_OBJECTS:
                break
            key = obj["Key"]
            if not key.lower().endswith(S3_EXTENSIONS) or obj.get("Size", 0) == 0:
                continue
            objects += 1
            body = s3.get_object(Bucket=bucket, Key=key, Range=f"bytes=0-{BYTES_PER_OBJECT - 1}")["Body"].read()
            stats: dict[str, FieldStats] = {}
            for field, value in _values_from_text(key, body.decode("utf-8", errors="replace")):
                stats.setdefault(field, FieldStats()).add(value)
            for field, st in stats.items():
                for f in findings_for_field(field, st):
                    out.append({"container": f"s3://{bucket}/{key}", "field": field, **f})
    return out, {"objects": objects}


SCANNERS = {"postgres": _scan_postgres, "mysql": _scan_mysql, "s3": _scan_s3}

REQUIRED = {
    "postgres": ["host", "database", "username"],
    "mysql": ["host", "database", "username"],
    "s3": ["bucket"],
}


def scan_source(db: Session, source: DataSource, **kwargs) -> int:
    secret = decrypt_json(source.secret_encrypted)
    try:
        findings, stats = SCANNERS[source.kind](source.config, secret, **kwargs)
    except ScanError as e:
        source.status, source.last_error = "error", str(e)
        db.commit()
        raise
    except Exception as e:  # driver / network errors
        source.status, source.last_error = "error", f"{type(e).__name__}: {e}"[:1000]
        db.commit()
        raise ScanError(source.last_error) from e
    now = datetime.now(timezone.utc)
    db.execute(delete(PiiFinding).where(PiiFinding.source_id == source.id))
    for f in findings:
        db.add(PiiFinding(org_id=source.org_id, source_id=source.id, container=f["container"][:500],
                          field=f["field"][:300], category=f["category"], matches=f["matches"],
                          sampled=f["sampled"], by_name_only=f["by_name_only"], examples=f["examples"],
                          scanned_at=now))
    source.status, source.last_error, source.last_scan_at = "scanned", "", now
    source.stats = {**stats, "findings": len(findings)}
    db.commit()
    return len(findings)
