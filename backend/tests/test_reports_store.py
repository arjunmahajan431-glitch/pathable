from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

from pathable.reports.status import is_active
from pathable.reports.store import ReportStore


def _store(tmp_path: Path) -> ReportStore:
    store = ReportStore(tmp_path / "test.db")
    store.initialize()
    return store


def test_wal_mode_and_schema(tmp_path: Path) -> None:
    store = _store(tmp_path)
    conn = sqlite3.connect(store.path)
    mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    tables = {
        row[0]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }
    conn.close()
    assert mode.lower() == "wal"
    assert {"reports", "audits", "meta"} <= tables


def test_report_roundtrip_and_client_hash_privacy(tmp_path: Path) -> None:
    store = _store(tmp_path)
    client_hash = store.client_hash("192.0.2.44")
    assert len(client_hash) == 24
    report = store.create_report(
        lat=40.0,
        lon=-75.0,
        category="construction",
        description="temporary closure",
        client_hash=client_hash,
    )
    assert report["status"] == "unverified"
    assert report["client_hash"] == client_hash

    conn = sqlite3.connect(store.path)
    values = conn.execute("SELECT lat, lon, description, client_hash FROM reports").fetchall()
    conn.close()
    flat = " ".join(str(part) for row in values for part in row)
    assert "192.0.2.44" not in flat
    # Different days produce different hashes, so the stored identifier rotates.
    today = datetime(2026, 1, 1, tzinfo=UTC)
    tomorrow = datetime(2026, 1, 2, tzinfo=UTC)
    assert store.client_hash("192.0.2.44", when=today) != store.client_hash(
        "192.0.2.44", when=tomorrow
    )


def test_expiry_and_reconfirmation(tmp_path: Path) -> None:
    store = _store(tmp_path)
    report = store.create_report(
        lat=40.0,
        lon=-75.0,
        category="other",
        description="",
        client_hash=store.client_hash("client"),
    )
    old = (datetime.now(UTC) - timedelta(days=200)).isoformat(timespec="seconds")
    with sqlite3.connect(store.path) as conn:
        conn.execute(
            "UPDATE reports SET created_at=?, last_confirmed_at=? WHERE id=?",
            (old, old, report["id"]),
        )
        conn.commit()
    stale = store.get_report(report["id"])
    assert stale is not None
    assert is_active(stale, expiry_days=180) is False
    update = store.update_status(report["id"], "reviewed", reconfirm=True)
    assert update is not None
    assert update["status"] == "reviewed"
    assert is_active(update, expiry_days=180) is True


def test_resolved_reports_do_not_influence(tmp_path: Path) -> None:
    store = _store(tmp_path)
    report = store.create_report(
        lat=40.0,
        lon=-75.0,
        category="other",
        description="",
        client_hash=store.client_hash("client"),
    )
    resolved = store.update_status(report["id"], "resolved")
    assert resolved is not None
    assert is_active(resolved, expiry_days=180) is False
    assert store.routing_reports() == []


def test_rate_limit_counting(tmp_path: Path) -> None:
    store = _store(tmp_path)
    client_hash = store.client_hash("client")
    for index in range(2):
        store.create_report(
            lat=40.0,
            lon=-75.0,
            category="other",
            description=f"report {index}",
            client_hash=client_hash,
        )
    assert store.recent_report_count(client_hash) == 2
    assert store.recent_report_count(store.client_hash("other")) == 0


def test_audit_storage(tmp_path: Path) -> None:
    store = _store(tmp_path)
    audit_id = store.add_audit(
        {
            "edge_uid": "1:2:0",
            "lat": 40.0,
            "lon": -75.0,
            "curb_ramp": "yes",
            "measured_slope_pct": 4.5,
            "clear_width_m": 1.4,
            "obstacle": "",
            "snap_distance_m": 2.1,
            "source_file": "sample.csv",
        }
    )
    assert audit_id > 0
    audits = store.audits()
    assert len(audits) == 1
    assert audits[0]["curb_ramp"] == "yes"
    assert store.audit_count() == 1
    assert store.delete_audits_from_source("sample.csv") == 1
    assert store.audits() == []
