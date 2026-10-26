"""Import field-audit records and snap them to the routing graph.

Field data is the highest provenance tier: it is what a person actually
measured. This module only *stores* and *snaps* records. Applying them to the
cost model happens in ``graph.features.apply_audit`` and the original OSM
values are kept for comparison (see ``scripts/evaluate.py``).

Two input formats are supported:

* CSV with a header row (see ``docs/FIELD_AUDIT.md``).
* GeoJSON FeatureCollection of Point features; properties use the same names.

The import is idempotent per source file: re-importing ``my_audit.csv``
replaces rows previously imported from that file. Rows are never invented or
interpolated. A row whose point is too far from the network is rejected with a
readable error instead of being snapped to an unrelated block.
"""

from __future__ import annotations

import csv
import json
import math
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import networkx as nx

from pathable.graph.loader import haversine_m
from pathable.graph.model import EdgeFeatures, edge_uid
from pathable.reports.store import ReportStore

CURB_VALUES = {"yes", "no", "damaged", "lowered", "flush", "raised", "missing", "broken", ""}
REQUIRED_COLUMNS = {"lat", "lon"}
MAX_TEXT = 500


@dataclass
class AuditRecord:
    """One validated input row, before snapping."""

    lat: float
    lon: float
    curb_ramp: str | None = None
    measured_slope_pct: float | None = None
    clear_width_m: float | None = None
    obstacle: str | None = None
    audit_date: str | None = None
    photo_ref: str | None = None
    notes: str | None = None
    row_number: int = 0
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class AuditRow:
    """A record that snapped to a graph edge."""

    record: AuditRecord
    edge_uid: str
    snap_distance_m: float


class AuditImportError(ValueError):
    """A row cannot be imported as written."""


def _text(value: Any, *, field_name: str, limit: int = MAX_TEXT) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if len(text) > limit:
        raise AuditImportError(f"{field_name} is longer than {limit} characters")
    return text


def _number(value: Any, *, field_name: str, low: float, high: float) -> float | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise AuditImportError(f"{field_name} must be a number, got {value!r}") from exc
    if not math.isfinite(number) or number < low or number > high:
        raise AuditImportError(f"{field_name} must be between {low} and {high}, got {number}")
    return number


def _date_text(value: Any) -> str | None:
    text = _text(value, field_name="date", limit=40)
    if not text:
        return None
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError:
        return None


def record_from_dict(raw: dict[str, Any], row_number: int = 0) -> AuditRecord:
    """Validate a flat property mapping. Raises :class:`AuditImportError`."""
    normalized = {str(key).strip().lower(): value for key, value in raw.items()}
    missing = {column for column in REQUIRED_COLUMNS if normalized.get(column) in (None, "")}
    if missing:
        raise AuditImportError(f"missing required column(s): {', '.join(sorted(missing))}")
    lat = _number(normalized.get("lat"), field_name="lat", low=-90, high=90)
    lon = _number(normalized.get("lon"), field_name="lon", low=-180, high=180)
    assert lat is not None and lon is not None  # checked above

    curb = (_text(normalized.get("curb_ramp"), field_name="curb_ramp", limit=20) or "").lower()
    if curb not in CURB_VALUES:
        raise AuditImportError(
            "curb_ramp must be yes, no, damaged, lowered, flush, raised, missing or blank"
        )
    slope = _number(
        normalized.get("measured_slope_pct"),
        field_name="measured_slope_pct",
        low=-100,
        high=100,
    )
    width = _number(
        normalized.get("clear_width_m"),
        field_name="clear_width_m",
        low=0,
        high=50,
    )
    known = {key for key in ("lat", "lon", "curb_ramp", "measured_slope_pct", "clear_width_m")}
    extra = {
        key: value
        for key, value in normalized.items()
        if key not in known and value not in (None, "")
    }
    return AuditRecord(
        lat=lat,
        lon=lon,
        curb_ramp=curb or None,
        measured_slope_pct=slope,
        clear_width_m=width,
        obstacle=_text(normalized.get("obstacle"), field_name="obstacle", limit=120),
        audit_date=_date_text(normalized.get("date") or normalized.get("audit_date")),
        photo_ref=_text(normalized.get("photo_ref"), field_name="photo_ref", limit=300),
        notes=_text(normalized.get("notes"), field_name="notes"),
        row_number=row_number,
        extra=extra,
    )


def read_audit_file(path: Path) -> list[AuditRecord]:
    """Read CSV or GeoJSON audit records. Blank rows are skipped."""
    if not path.exists():
        raise FileNotFoundError(f"Audit file not found: {path}")
    suffix = path.suffix.lower()
    records: list[AuditRecord] = []
    if suffix in {".geojson", ".json"}:
        payload = json.loads(path.read_text(encoding="utf-8"))
        features = payload.get("features") if isinstance(payload, dict) else None
        if not isinstance(features, list):
            raise AuditImportError("GeoJSON must be a FeatureCollection with a features array")
        for index, feature in enumerate(features, start=1):
            if not isinstance(feature, dict):
                raise AuditImportError(f"feature {index} is not an object")
            geometry = feature.get("geometry") or {}
            if geometry.get("type") != "Point":
                raise AuditImportError(f"feature {index} is not a Point")
            coords = geometry.get("coordinates") or []
            if not isinstance(coords, list) or len(coords) < 2:
                raise AuditImportError(f"feature {index} has invalid coordinates")
            properties = dict(feature.get("properties") or {})
            properties["lon"], properties["lat"] = coords[0], coords[1]
            records.append(record_from_dict(properties, row_number=index))
        return records

    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise AuditImportError("CSV must have a header row")
        missing = REQUIRED_COLUMNS - {name.strip().lower() for name in reader.fieldnames}
        if missing:
            raise AuditImportError(f"CSV is missing column(s): {', '.join(sorted(missing))}")
        for index, row in enumerate(reader, start=2):
            if not any(str(value or "").strip() for value in row.values()):
                continue
            records.append(record_from_dict(dict(row), row_number=index))
    return records


def _xy(lat: float, lon: float, lat0: float, lon0: float) -> tuple[float, float]:
    """Local equirectangular meters. Good enough at block scale."""
    radius = 6_371_008.8
    x = math.radians(lon - lon0) * math.cos(math.radians(lat0)) * radius
    y = math.radians(lat - lat0) * radius
    return x, y


def _point_segment_distance_m(
    lat: float, lon: float, start: tuple[float, float], end: tuple[float, float]
) -> float:
    """Distance from a point to one edge segment, in meters.

    Coordinates are (lon, lat). The local projection is centered on the query
    point, so errors over a few hundred meters are negligible for snapping.
    """
    ax, ay = _xy(start[1], start[0], lat, lon)
    bx, by = _xy(end[1], end[0], lat, lon)
    dx, dy = bx - ax, by - ay
    length_sq = dx * dx + dy * dy
    if length_sq == 0:
        return math.hypot(ax, ay)
    t = max(0.0, min(1.0, -(ax * dx + ay * dy) / length_sq))
    return math.hypot(ax + t * dx, ay + t * dy)


def edge_distance_m(features: EdgeFeatures, lat: float, lon: float) -> float:
    coords = features.coords
    if not coords:
        return math.inf
    if len(coords) < 2:
        return haversine_m(lat, lon, coords[0][1], coords[0][0])
    return min(
        _point_segment_distance_m(lat, lon, coords[index], coords[index + 1])
        for index in range(len(coords) - 1)
    )


def snap_records(
    graph: nx.MultiDiGraph,
    records: Iterable[AuditRecord],
    *,
    max_snap_m: float,
) -> tuple[list[AuditRow], list[str]]:
    """Snap each record to the closest edge midpoint/segment.

    Returns the rows that snapped and a list of human-readable rejections.
    Deterministic: ties are broken by edge uid.
    """
    edges = sorted(
        (
            (edge_uid(u, v, key), data["features"])
            for u, v, key, data in graph.edges(keys=True, data=True)
        ),
        key=lambda item: item[0],
    )
    rows: list[AuditRow] = []
    errors: list[str] = []
    for record in records:
        best: tuple[float, str] | None = None
        for uid, features in edges:
            distance = edge_distance_m(features, record.lat, record.lon)
            if best is None or distance < best[0]:
                best = (distance, uid)
        if best is None:
            errors.append(f"row {record.row_number}: graph has no edges")
            continue
        distance, uid = best
        if distance > max_snap_m:
            errors.append(
                f"row {record.row_number}: nearest edge is {distance:.0f} m away "
                f"(limit {max_snap_m:.0f} m); not imported"
            )
            continue
        rows.append(AuditRow(record=record, edge_uid=uid, snap_distance_m=round(distance, 2)))
    return rows, errors


def import_records(
    graph: nx.MultiDiGraph,
    store: ReportStore,
    records: Iterable[AuditRecord],
    *,
    source_file: str,
    max_snap_m: float,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Snap and persist records. Re-importing a source file replaces its rows."""
    rows, errors = snap_records(graph, records, max_snap_m=max_snap_m)
    if not dry_run:
        store.delete_audits_from_source(source_file)
        for row in rows:
            record = row.record
            store.add_audit(
                {
                    "edge_uid": row.edge_uid,
                    "lat": record.lat,
                    "lon": record.lon,
                    "curb_ramp": record.curb_ramp,
                    "measured_slope_pct": record.measured_slope_pct,
                    "clear_width_m": record.clear_width_m,
                    "obstacle": record.obstacle,
                    "audit_date": record.audit_date,
                    "photo_ref": record.photo_ref,
                    "notes": record.notes,
                    "snap_distance_m": row.snap_distance_m,
                    "source_file": source_file,
                }
            )
    return {
        "source_file": source_file,
        "records": len(rows) + len(errors),
        "imported": len(rows),
        "errors": errors,
        "max_snap_m": max(row.snap_distance_m for row in rows) if rows else 0.0,
        "dry_run": dry_run,
    }
