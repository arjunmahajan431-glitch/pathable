#!/usr/bin/env python3
"""Download and cache the walking network for one or all mapping areas.

This is the online step. It uses the free Overpass API through OSMnx and writes
the graph plus a metadata file under ``data/cache``. If Overpass is unavailable,
the API will fall back to the committed sample extract with a visible DEMO
banner; this script exits non-zero so the failure is not silent.

Usage::

    python scripts/fetch_data.py
    python scripts/fetch_data.py --area saint-paul-mn
    python scripts/fetch_data.py --all
    PATHABLE_DEMO=1 python scripts/fetch_data.py   # load the sample, no download
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from pathable.config import load_config  # noqa: E402
from pathable.graph.loader import download_graph, load_area_graph  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--area", help="area id to fetch (default: active area)")
    parser.add_argument("--all", action="store_true", help="fetch every configured area")
    args = parser.parse_args()

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

    failed = False
    for area in areas:
        print(f"Area: {area.name} ({area.id})")
        print(
            f"Center: {area.center.lat:.6f}, {area.center.lon:.6f}  "
            f"radius: {area.radius_m:.0f} m  boundary: {area.boundary or 'none'}"
        )
        if config.demo_forced:
            bundle = load_area_graph(config, area=area, demo_mode=True)
            print(f"Demo mode: loaded {bundle.path}")
            print(
                f"{bundle.meta.area_name}: {bundle.graph.number_of_nodes()} nodes, "
                f"{bundle.graph.number_of_edges()} edges"
            )
            print("No download was performed.")
            continue

        print("Downloading the OpenStreetMap walk network via Overpass...")
        try:
            path = download_graph(config, area)
        except Exception as exc:
            print(
                f"ERROR: download failed for {area.id}: {type(exc).__name__}: {exc}",
                file=sys.stderr,
            )
            failed = True
            continue
        print(f"Saved: {path}")
        bundle = load_area_graph(config, area=area, demo_mode=False)
        print(
            f"Loaded: {bundle.graph.number_of_nodes()} nodes, "
            f"{bundle.graph.number_of_edges()} directed edges"
        )
        if bundle.meta.demo_mode:
            print(
                "ERROR: the loader fell back to the sample extract. Check the download log.",
                file=sys.stderr,
            )
            failed = True
    if not config.demo_forced and not failed:
        print("Next: `make elevation` (optional) and `make coverage`.")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
