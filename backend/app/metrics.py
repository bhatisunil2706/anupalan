"""Minimal Prometheus metrics (text exposition format) without extra dependencies.

Served at /metrics on the backend port, which is not routed through the web proxy. Set METRICS_TOKEN to require
`Authorization: Bearer <token>`.
"""
import threading
from collections import defaultdict

from sqlalchemy import func, select

BUCKETS = (0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10)
_lock = threading.Lock()
_requests: dict[tuple[str, str, str], int] = defaultdict(int)
_latency: dict[str, list[float]] = defaultdict(lambda: [0] * (len(BUCKETS) + 2))  # buckets.., +Inf, sum
_events: dict[str, int] = defaultdict(int)


def observe(method: str, route: str, status: int, seconds: float) -> None:
    with _lock:
        _requests[(method, route, f"{status // 100}xx")] += 1
        h = _latency[route]
        for i, b in enumerate(BUCKETS):
            if seconds <= b:
                h[i] += 1
        h[len(BUCKETS)] += 1
        h[len(BUCKETS) + 1] += seconds


def event(name: str) -> None:
    """Count security-relevant events, e.g. login_failed, csrf_blocked, rate_limited."""
    with _lock:
        _events[name] += 1


def _esc(v: str) -> str:
    return v.replace("\\", "\\\\").replace('"', '\\"')


def render(db) -> str:
    from app.models import AiJob, Notification, Organization

    lines = ["# TYPE http_requests_total counter"]
    with _lock:
        for (m, r, s), n in sorted(_requests.items()):
            lines.append(f'http_requests_total{{method="{m}",route="{_esc(r)}",status="{s}"}} {n}')
        lines.append("# TYPE http_request_duration_seconds histogram")
        for r, h in sorted(_latency.items()):
            for i, b in enumerate(BUCKETS):
                lines.append(f'http_request_duration_seconds_bucket{{route="{_esc(r)}",le="{b}"}} {h[i]}')
            lines.append(f'http_request_duration_seconds_bucket{{route="{_esc(r)}",le="+Inf"}} {h[len(BUCKETS)]}')
            lines.append(f'http_request_duration_seconds_count{{route="{_esc(r)}"}} {h[len(BUCKETS)]}')
            lines.append(f'http_request_duration_seconds_sum{{route="{_esc(r)}"}} {h[len(BUCKETS) + 1]:.4f}')
        lines.append("# TYPE security_events_total counter")
        for name, n in sorted(_events.items()):
            lines.append(f'security_events_total{{event="{_esc(name)}"}} {n}')
    pending = db.scalar(select(func.count(Notification.id)).where(Notification.status == "pending")) or 0
    failed = db.scalar(select(func.count(Notification.id)).where(Notification.status == "failed")) or 0
    ai = db.scalar(select(func.count(AiJob.id)).where(AiJob.status.in_(("pending", "running")))) or 0
    orgs = db.scalar(select(func.count(Organization.id))) or 0
    lines += ["# TYPE notifications_pending gauge", f"notifications_pending {pending}",
              "# TYPE notifications_failed gauge", f"notifications_failed {failed}",
              "# TYPE ai_jobs_queued gauge", f"ai_jobs_queued {ai}",
              "# TYPE organizations gauge", f"organizations {orgs}"]
    return "\n".join(lines) + "\n"
