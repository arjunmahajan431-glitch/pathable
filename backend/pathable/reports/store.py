"""SQLite persistence for community reports and field audits.

Privacy: we never store names, emails, IP addresses, or route endpoints. Rate
limiting uses a rotating salted hash (see ``client_hash`` below). WAL mode is
enabled so concurrent reads and a single writer do not block each other.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lat REAL NOT NULL CHECK (lat BETWEEN -90 AND 90),
    lon REAL NOT NULL CHECK (lon BETWEEN -180 AND 180),
    category TEXT NOT NULL CHECK (category IN (
        'blocked_sidewalk',
        'missing_or_damaged_curb_ramp',
        'stairs_or_inaccessible_entrance',
        'rough_or_damaged_pavement',
        'construction',
        'other'
    )),
    description TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'unverified'
        CHECK (status IN ('unverified', 'reviewed', 'resolved', 'rejected')),
    reviewed_at TEXT,
    last_confirmed_at TEXT NOT NULL,
    client_hash TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_reports_pos ON reports(lat, lon);
CREATE INDEX IF NOT EXISTS idx_reports_hash ON reports(client_hash, created_at);

CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    edge_uid TEXT NOT NULL,
    lat REAL NOT NULL,
    lon REAL NOT NULL,
    curb_ramp TEXT,
    measured_slope_pct REAL,
    clear_width_m REAL,
    obstacle TEXT,
    audit_date TEXT,
    photo_ref TEXT,
    notes TEXT,
    snap_distance_m REAL,
    imported_at TEXT NOT NULL,
    source_file TEXT
);
CREATE INDEX IF NOT EXISTS idx_audits_edge ON audits(edge_uid);
"""


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class ReportStore:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.executescript(SCHEMA)
            conn.commit()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    # --- rotating client hash ------------------------------------------------
    def _secret(self) -> str:
        with self._connect() as conn:
            row = conn.execute("SELECT value FROM meta WHERE key='client_hash_secret'").fetchone()
            if row:
                return str(row["value"])
            secret = secrets.token_hex(32)
            conn.execute(
                "INSERT INTO meta(key, value) VALUES('client_hash_secret', ?)",
                (secret,),
            )
            conn.commit()
            return secret

    def client_hash(self, client_id: str, *, when: datetime | None = None) -> str:
        """Daily-rotating hash. The raw client id is never stored."""
        day = (when or datetime.now(UTC)).strftime("%Y-%m-%d")
        digest = hmac.new(
            self._secret().encode("utf-8"),
            f"{day}|{client_id}".encode(),
            hashlib.sha256,
        ).hexdigest()
        return digest[:24]

    # --- reports -------------------------------------------------------------
    def create_report(
        self,
        *,
        lat: float,
        lon: float,
        category: str,
        description: str,
        client_hash: str,
    ) -> dict[str, Any]:
        stamp = now_iso()
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO reports
                    (lat, lon, category, description, created_at, status,
                     last_confirmed_at, client_hash)
                VALUES (?, ?, ?, ?, ?, 'unverified', ?, ?)
                """,
                (lat, lon, category, description, stamp, stamp, client_hash),
            )
            conn.commit()
            report_id = int(cursor.lastrowid or 0)
        report = self.get_report(report_id)
        if report is None:
            raise RuntimeError("report was inserted but could not be read back")
        return report

    def recent_report_count(self, client_hash: str, *, hours: int = 1) -> int:
        cutoff = (datetime.now(UTC) - timedelta(hours=hours)).isoformat(timespec="seconds")
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM reports WHERE client_hash=? AND created_at>=?",
                (client_hash, cutoff),
            ).fetchone()
        return int(row["n"]) if row else 0

    def get_report(self, report_id: int) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM reports WHERE id=?", (report_id,)).fetchone()
        return dict(row) if row else None

    def list_reports(
        self, *, min_lat: float, min_lon: float, max_lat: float, max_lon: float, limit: int = 500
    ) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM reports
                WHERE lat BETWEEN ? AND ? AND lon BETWEEN ? AND ?
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """,
                (min_lat, max_lat, min_lon, max_lon, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def routing_reports(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM reports
                WHERE status IN ('unverified', 'reviewed')
                ORDER BY id ASC
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def update_status(
        self, report_id: int, status: str, *, reconfirm: bool = False
    ) -> dict[str, Any] | None:
        stamp = now_iso()
        with self._connect() as conn:
            existing = conn.execute("SELECT * FROM reports WHERE id=?", (report_id,)).fetchone()
            if not existing:
                return None
            reviewed_at = existing["reviewed_at"]
            if status != "unverified" and reviewed_at is None:
                reviewed_at = stamp
            confirmed = (
                stamp if (reconfirm or status == "reviewed") else existing["last_confirmed_at"]
            )
            conn.execute(
                """
                UPDATE reports
                SET status=?, reviewed_at=?, last_confirmed_at=?
                WHERE id=?
                """,
                (status, reviewed_at, confirmed, report_id),
            )
            conn.commit()
        return self.get_report(report_id)

    # --- field audits --------------------------------------------------------
    def add_audit(self, record: dict[str, Any]) -> int:
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO audits
                    (edge_uid, lat, lon, curb_ramp, measured_slope_pct, clear_width_m,
                     obstacle, audit_date, photo_ref, notes, snap_distance_m,
                     imported_at, source_file)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record["edge_uid"],
                    record["lat"],
                    record["lon"],
                    record.get("curb_ramp"),
                    record.get("measured_slope_pct"),
                    record.get("clear_width_m"),
                    record.get("obstacle"),
                    record.get("audit_date"),
                    record.get("photo_ref"),
                    record.get("notes"),
                    record.get("snap_distance_m"),
                    now_iso(),
                    record.get("source_file"),
                ),
            )
            conn.commit()
            return int(cursor.lastrowid or 0)

    def audits(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM audits ORDER BY id ASC").fetchall()
        return [dict(row) for row in rows]

    def delete_audits_from_source(self, source_file: str) -> int:
        with self._connect() as conn:
            cursor = conn.execute("DELETE FROM audits WHERE source_file=?", (source_file,))
            conn.commit()
            return int(cursor.rowcount)

    def audit_count(self) -> int:
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS n FROM audits").fetchone()
        return int(row["n"]) if row else 0
