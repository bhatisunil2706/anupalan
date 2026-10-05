"""Per-request values available anywhere (audit log, notifications) without threading them through calls."""
from contextvars import ContextVar

client_ip: ContextVar[str] = ContextVar("client_ip", default="")
user_agent: ContextVar[str] = ContextVar("user_agent", default="")
request_id: ContextVar[str] = ContextVar("request_id", default="")
