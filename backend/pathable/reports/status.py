"""Report influence rules shared by the router and the API.

A report influences routing only while its status is ``unverified`` or
``reviewed`` and it has been confirmed recently enough. Unverified reports get
half weight in the cost function; resolved and rejected reports get none.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

STATUS_WEIGHT = {"reviewed": 1.0, "unverified": 0.5, "resolved": 0.0, "rejected": 0.0}


def _parse(stamp: Any) -> datetime | None:
    if not stamp:
        return None
    try:
        value = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
    except ValueError:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value


def confirmed_at(report: dict[str, Any]) -> datetime | None:
    return _parse(report.get("last_confirmed_at")) or _parse(report.get("created_at"))


def is_active(report: dict[str, Any], expiry_days: int, *, now: datetime | None = None) -> bool:
    if report.get("status") not in {"unverified", "reviewed"}:
        return False
    stamp = confirmed_at(report)
    if stamp is None:
        return False
    current = now or datetime.now(UTC)
    return stamp >= current - timedelta(days=expiry_days)
