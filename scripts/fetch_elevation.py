#!/usr/bin/env python3
"""Fetch free DEM elevations for graph nodes and cache them locally.

Default provider: OpenTopoData public API, SRTM 30 m (NASA/USGS).
Provider limits (checked 2026-10-25): 100 locations/request, 1 request/second,
1000 requests/day. This script sleeps between requests and caches every batch,
so it can be resumed. SRTM resolution is ~30 m: the result is an ESTIMATE of
street-level grade, not a sidewalk measurement. Bridges and underpasses are
misrepresented.

Usage:
    python scripts/fetch_elevation.py --demo --all
    python scripts/fetch_elevation.py --area saint-paul-mn
    python scripts/fetch_elevation.py --all
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND = PROJECT_ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from pathable.config import load_config  # noqa: E402
from pathable.graph.loader import (  # noqa: E402
    _elevation_cache_path,
    _log_fetch,
    load_area_graph,
)


def fetch_batch(
    client: httpx.Client, endpoint: str, points: list[tuple[str, float, float]], user_agent: str
) -> dict[str, float]:
    locations = "|".join(f"{lat:.6f},{lon:.6f}" for _, lat, lon in points)
    response = client.get(
        endpoint,
        params={"locations": locations},
        headers={"User-Agent": user_agent},
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("status") != "OK":
        raise RuntimeError(f"OpenTopoData error: {payload.get('status')} {payload.get('error')}")
    results = payload.get("results", [])
    if len(results) != len(points):
        raise RuntimeError(f"expected {len(points)} elevation results, received {len(results)}")
    out: dict[str, float] = {}
    for (node, _, _), item in zip(points, results, strict=True):
        elevation = item.get("elevation")
        if elevation is not None:
            out[str(node)] = float(elevation)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--demo", action="store_true", help="use the committed sample graph")
    parser.add_argument("--area", help="area id to update (default: active area)")
    parser.add_argument("--all", action="store_true", help="update every configured area")
    parser.add_argument("--output", type=Path, help="override the output JSON path")
    parser.add_argument("--force", action="store_true", help="ignore existing cache")
    parser.add_argument("--limit", type=int, default=0, help="only fetch the first N nodes (debug)")
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
    if args.output and len(areas) != 1:
        print("--output only makes sense with a single area", file=sys.stderr)
        return 2

    demo = args.demo or config.demo_forced
    failed = False
    for area in areas:
        print(f"Area: {area.name} ({area.id})")
        bundle = load_area_graph(config, area=area, demo_mode=demo)
        graph = bundle.graph
        if bundle.meta.demo_mode and not demo:
            print(
                f"Refusing to write a live elevation cache for {area.id}: the graph is the "
                "DEMO sample. Run `make data` first, or pass --demo to update the labeled sample.",
                file=sys.stderr,
            )
            failed = True
            continue
        if demo:
            sample = area.sample_elevation or config.data.sample_elevation
            output = args.output or config.path(sample)
        else:
            output = args.output or _elevation_cache_path(config, area)
        existing: dict[str, float] = {}
        if output.exists() and not args.force:
            try:
                payload = json.loads(output.read_text(encoding="utf-8"))
                existing = {str(k): float(v) for k, v in payload.get("elevations", {}).items()}
            except (OSError, ValueError):
                existing = {}
        missing = [
            (str(node), float(data["features"].lat), float(data["features"].lon))
            for node, data in graph.nodes(data=True)
            if str(node) not in existing
        ]
        if args.limit:
            missing = missing[: args.limit]
        print(
            f"Graph nodes: {graph.number_of_nodes()}; already cached: {len(existing)}; "
            f"to fetch: {len(missing)}"
        )
        if not missing:
            print(f"Nothing to fetch. Elevation cache: {output}")
            continue

        try:
            output.parent.mkdir(parents=True, exist_ok=True)
            elevations = dict(existing)
            batch_size = config.elevation.batch_size
            with httpx.Client(timeout=config.elevation.timeout_s) as client:
                for start in range(0, len(missing), batch_size):
                    batch = missing[start : start + batch_size]
                    fetched = fetch_batch(
                        client, config.elevation.endpoint, batch, config.elevation.user_agent
                    )
                    elevations.update(fetched)
                    payload = {
                        "source": (
                            config.data.sample_elevation_source
                            if demo
                            else "OpenTopoData public API, SRTM 30 m (NASA/USGS)"
                        ),
                        "date": datetime.now(UTC).strftime("%Y-%m-%d"),
                        "dataset": "srtm30m",
                        "note": (
                            "Elevation is sampled at graph nodes (~30 m DEM). It is not a "
                            "sidewalk slope measurement and can be wrong on bridges/underpasses."
                        ),
                        "elevations": elevations,
                    }
                    output.write_text(
                        json.dumps(payload, indent=1, sort_keys=True), encoding="utf-8"
                    )
                    done = min(start + batch_size, len(missing))
                    print(
                        f"Fetched {done}/{len(missing)} nodes; saved {len(elevations)} elevations"
                    )
                    _log_fetch(
                        config.cache_dir,
                        f"DEM elevation batch provider={config.elevation.provider} nodes={done}",
                    )
                    if done < len(missing):
                        time.sleep(config.elevation.min_interval_s)
        except Exception as exc:
            print(
                f"ERROR: elevation fetch failed for {area.id}: {type(exc).__name__}: {exc}",
                file=sys.stderr,
            )
            failed = True
            continue

        values = list(elevations.values())
        print(
            f"Wrote {output} ({output.stat().st_size} bytes); "
            f"elevations={len(values)} min={min(values):.1f} m max={max(values):.1f} m"
        )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
