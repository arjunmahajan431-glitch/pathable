#!/usr/bin/env python3
"""Import a field-audit CSV or GeoJSON file (see docs/FIELD_AUDIT.md).

Examples::

    python scripts/import_audit.py data/fixtures/sample_field_audit.csv --dry-run
    python scripts/import_audit.py data/fixtures/sample_field_audit.csv --allow-demo
    python scripts/import_audit.py my_audit.geojson

The script refuses to snap real field data onto the committed demo extract
unless ``--allow-demo`` is explicit, because a field measurement belongs to a
real block in the selected mapping area. Re-importing the same filename replaces the
rows previously imported from it, so fixing a row is just re-running the file.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from pathable.audit_import import (  # noqa: E402
    AuditImportError,
    import_records,
    read_audit_file,
)
from pathable.config import load_config  # noqa: E402
from pathable.graph.loader import haversine_m, load_area_graph  # noqa: E402
from pathable.reports.store import ReportStore  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", type=Path, help="CSV or GeoJSON audit file")
    parser.add_argument(
        "--database",
        type=Path,
        default=None,
        help="SQLite path (default: config reports.database, or PATHABLE_DATABASE)",
    )
    parser.add_argument("--dry-run", action="store_true", help="validate and snap, do not store")
    parser.add_argument(
        "--allow-demo",
        action="store_true",
        help="allow snapping onto the committed demo extract (clearly labeled data only)",
    )
    args = parser.parse_args(argv)

    config = load_config()
    store = ReportStore(args.database or config.database_path)
    store.initialize()
    graph_bundle = load_area_graph(config, demo_mode=None)
    if graph_bundle.meta.demo_mode and not args.allow_demo:
        print(
            "Refusing to import field data onto the DEMO extract. Download the real "
            "area first (`make data`) or pass --allow-demo for the labeled sample file.",
            file=sys.stderr,
        )
        return 2

    try:
        records = read_audit_file(args.file)
    except (AuditImportError, FileNotFoundError, json.JSONDecodeError) as exc:
        print(f"Could not read {args.file}: {exc}", file=sys.stderr)
        return 2
    if not records:
        print("No audit rows found.", file=sys.stderr)
        return 2

    area = config.area
    outside = [
        f"row {record.row_number}: outside the selected mapping area"
        for record in records
        if haversine_m(area.center.lat, area.center.lon, record.lat, record.lon) > area.radius_m
    ]
    if outside:
        print("\n".join(outside), file=sys.stderr)
        print("Nothing was imported. Move the point or change the mapping area.", file=sys.stderr)
        return 2

    summary = import_records(
        graph_bundle.graph,
        store,
        records,
        source_file=args.file.name,
        max_snap_m=config.routing.max_snap_m,
        dry_run=args.dry_run,
    )
    print(f"Source: {summary['source_file']}")
    print(f"Rows read: {summary['records']}")
    print(f"Snapped and {'validated' if args.dry_run else 'stored'}: {summary['imported']}")
    print(f"Farthest snap: {summary['max_snap_m']:.1f} m")
    if graph_bundle.meta.demo_mode:
        print("DEMO EXTRACT: these rows are sample/demo data, not a finding about a real place.")
    if summary["errors"]:
        print("\nRejected rows:", file=sys.stderr)
        for error in summary["errors"]:
            print(f"  {error}", file=sys.stderr)
        return 1
    if args.dry_run:
        print("Dry run: database unchanged.")
    else:
        print("Restart the API to apply the new audit values to the in-memory graph.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
