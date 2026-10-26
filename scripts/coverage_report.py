#!/usr/bin/env python3
"""Print tag-coverage statistics for the active pedestrian graph.

This is the Phase 1 checkpoint: how much of the network has each attribute the
router uses? It is a mapping statistic. It is not a safety or accessibility
score, and a missing value is not a defect in the route.

Usage::

    python scripts/coverage_report.py
    PATHABLE_DEMO=1 python scripts/coverage_report.py --demo
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from pathable.config import AppConfig, AreaConfig, load_config  # noqa: E402
from pathable.graph.loader import load_area_graph  # noqa: E402
from pathable.graph.model import EdgeFeatures  # noqa: E402
from pathable.models import Provenance  # noqa: E402


def _provenance(features: EdgeFeatures, attribute: str) -> Provenance:
    return {
        "surface": features.surface_prov,
        "smoothness": features.smoothness_prov,
        "width": features.width_prov,
        "grade": features.grade_prov,
        "steps": features.steps_prov,
        "kerb": features.kerb_prov,
        "lit": features.lit_prov,
        "wheelchair": features.wheelchair_prov,
        "crossing": features.crossing_prov,
        "tactile_paving": features.tactile_prov,
    }[attribute]


def _known(features: EdgeFeatures, attribute: str) -> bool:
    return _provenance(features, attribute) is not Provenance.UNKNOWN


def _print_area(config: AppConfig, area: AreaConfig, *, demo: bool) -> None:
    bundle = load_area_graph(config, area=area, demo_mode=demo)
    graph, meta = bundle.graph, bundle.meta
    edges = list(graph.edges(keys=True, data=True))
    total_length = sum(float(data["features"].length_m) for _, _, _, data in edges)
    crossing_length = sum(
        float(data["features"].length_m) for _, _, _, data in edges if data["features"].is_crossing
    )

    print(f"Area: {meta.area_name} ({meta.area_id})")
    print(f"Source: {meta.source}")
    print(f"Fetched: {meta.fetched_at}")
    print(
        f"Graph: {graph.number_of_nodes()} nodes, {len(edges)} directed edges, "
        f"{total_length / 1000:.1f} km of edge length"
    )
    if meta.demo_mode:
        print(
            "*** DEMO EXTRACT: committed sample data, not a live download. ***\n"
            "*** Numbers describe this extract, not current conditions.        ***"
        )
    print()

    header = (
        f"{'Attribute':<18} {'Known edges':>11} {'Edge %':>8} "
        f"{'Known length':>13} {'Length %':>9}  Provenance"
    )
    print(header)
    print("-" * len(header))
    attributes = [
        "steps",
        "surface",
        "smoothness",
        "width",
        "grade",
        "kerb",
        "crossing",
        "lit",
        "tactile_paving",
        "wheelchair",
    ]
    for attribute in attributes:
        considered = [
            data["features"]
            for _, _, _, data in edges
            if attribute != "kerb" or data["features"].is_crossing
        ]
        denominator = crossing_length if attribute == "kerb" else total_length
        known = [features for features in considered if _known(features, attribute)]
        known_length = sum(features.length_m for features in known)
        provenance = Counter(
            {
                "OSM_MAPPED": sum(
                    1 for f in known if _provenance(f, attribute) is Provenance.OSM_MAPPED
                ),
                "DEM_ESTIMATED": sum(
                    1 for f in known if _provenance(f, attribute) is Provenance.DEM_ESTIMATED
                ),
                "FIELD_AUDIT": sum(
                    1 for f in known if _provenance(f, attribute) is Provenance.FIELD_AUDIT
                ),
            }
        )
        if attribute == "grade":
            detail = (
                f"OSM {provenance['OSM_MAPPED']}, DEM {provenance['DEM_ESTIMATED']}, "
                f"field {provenance['FIELD_AUDIT']}"
            )
        else:
            detail = "known" if known else "unknown"
        print(
            f"{attribute:<18} {len(known):>11} {100 * len(known) / max(len(considered), 1):>7.1f}% "
            f"{known_length:>10.0f} m {100 * known_length / max(denominator, 1):>8.1f}%  {detail}"
        )

    print("\nNotes:")
    print("- `kerb` is counted only on crossing edges; its length denominator is crossing length.")
    print("- `grade` counts OSM incline and DEM estimates as known; see the provenance column.")
    print("- Coverage measures mapping completeness, not accessibility or safety.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--demo", action="store_true", help="force the committed sample graph")
    parser.add_argument("--area", help="area id to report (default: active area)")
    parser.add_argument("--all", action="store_true", help="report every configured area")
    args = parser.parse_args(argv)

    config = load_config()
    if args.all:
        areas = config.areas
    elif args.area:
        match = next((area for area in config.areas if area.id == args.area), None)
        if match is None:
            print(f"Unknown area: {args.area}", file=sys.stderr)
            return 2
        areas = [match]
    else:
        areas = [config.area]

    demo = args.demo or config.demo_forced
    for index, area in enumerate(areas):
        if index:
            print()
        _print_area(config, area, demo=demo)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
