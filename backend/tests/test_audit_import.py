from __future__ import annotations

from pathlib import Path

import pytest

from pathable.audit_import import (
    AuditImportError,
    import_records,
    read_audit_file,
    record_from_dict,
    snap_records,
)
from pathable.reports.store import ReportStore
from tests.fixtures.diamond import build_diamond


def test_read_csv_and_validate(tmp_path: Path) -> None:
    path = tmp_path / "audit.csv"
    path.write_text(
        "lat,lon,curb_ramp,measured_slope_pct,clear_width_m,obstacle,date,photo_ref,notes\n"
        "40.0003,-75.00025,yes,4.5,1.2,,2026-10-01,photo.jpg,ramp at the corner\n",
        encoding="utf-8",
    )
    records = read_audit_file(path)
    assert len(records) == 1
    record = records[0]
    assert record.curb_ramp == "yes"
    assert record.measured_slope_pct == 4.5
    assert record.clear_width_m == 1.2
    assert record.audit_date == "2026-10-01"


def test_geojson_and_bad_values(tmp_path: Path) -> None:
    path = tmp_path / "audit.geojson"
    path.write_text(
        """
        {"type":"FeatureCollection","features":[
          {"type":"Feature","geometry":{"type":"Point","coordinates":[-75.00025,40.0003]},
           "properties":{"curb_ramp":"no","clear_width_m":0.8}}
        ]}
        """,
        encoding="utf-8",
    )
    records = read_audit_file(path)
    assert records[0].lat == 40.0003
    assert records[0].lon == -75.00025
    assert records[0].measured_slope_pct is None

    with pytest.raises(AuditImportError, match="curb_ramp"):
        record_from_dict({"lat": 40.0, "lon": -75.0, "curb_ramp": "sort-of"})
    with pytest.raises(AuditImportError, match="between"):
        record_from_dict({"lat": 40.0, "lon": -75.0, "clear_width_m": -1})
    with pytest.raises(AuditImportError, match="missing required"):
        record_from_dict({"lat": 40.0})


def test_snap_to_nearest_edge_and_reject_far_point() -> None:
    graph = build_diamond()
    record = record_from_dict({"lat": 40.0003, "lon": -75.00025, "curb_ramp": "yes"})
    rows, errors = snap_records(graph, [record], max_snap_m=30.0)
    assert errors == []
    assert len(rows) == 1
    assert rows[0].edge_uid == "S:B:0"
    assert rows[0].snap_distance_m < 1.0

    far = record_from_dict({"lat": 40.01, "lon": -75.01})
    rows, errors = snap_records(graph, [far], max_snap_m=30.0)
    assert rows == []
    assert "not imported" in errors[0]


def test_import_is_idempotent_per_source(tmp_path: Path) -> None:
    graph = build_diamond()
    store = ReportStore(tmp_path / "audit.db")
    store.initialize()
    record = record_from_dict({"lat": 40.0003, "lon": -75.00025, "clear_width_m": 1.1})

    first = import_records(graph, store, [record], source_file="my_audit.csv", max_snap_m=30.0)
    second = import_records(graph, store, [record], source_file="my_audit.csv", max_snap_m=30.0)
    assert first["imported"] == second["imported"] == 1
    assert store.audit_count() == 1
    assert store.audits()[0]["source_file"] == "my_audit.csv"
