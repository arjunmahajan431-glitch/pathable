#!/usr/bin/env python3
"""Reproducible evaluation harness for PathAble.

Writes ``docs/EVALUATION.md``. Everything here is deterministic given a seed and
the committed sample graph, except wall-clock runtime (which is a measurement,
not a claim).

What it measures
----------------
1. Detour of the preferred route vs. the length-only shortest route over seeded
   random start/end pairs inside the selected city.
2. Whether the two routes differ, and how many mapped barriers (hard blocks)
   the preferred route avoids.
3. Route-length data coverage per attribute, averaged over routes. Coverage
   measures mapping completeness, never safety.
4. How often the preferred route changes when the risk setting moves
   direct -> balanced -> cautious.
5. Routing pipeline runtime (p50 / p95), measured in-process.
6. OSM vs. field audit: where OSM lacked an attribute or disagreed with the
   measured value. When the committed sample audit is used, the result is
   labeled SAMPLE DATA, NOT A FINDING.

Wall-clock runtime makes the file slightly different each run; all routing
results are deterministic for the same graph and seed.

Usage::

    python scripts/evaluate.py --demo          # 40 pairs, committed city sample
    python scripts/evaluate.py --demo --area saint-paul-mn
    python scripts/evaluate.py --pairs 80
    python scripts/evaluate.py --use-database  # compare against audits in the real DB
"""

from __future__ import annotations

import argparse
import math
import random
import statistics
import sys
import tempfile
import time
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from pathable.audit_import import import_records, read_audit_file  # noqa: E402
from pathable.config import load_config  # noqa: E402
from pathable.engine.pipeline import plan_route  # noqa: E402
from pathable.engine.search import routable_nodes  # noqa: E402
from pathable.graph.area import area_contains  # noqa: E402
from pathable.graph.loader import haversine_m, load_area_graph  # noqa: E402
from pathable.models import Point, Risk  # noqa: E402
from pathable.reports.store import ReportStore  # noqa: E402
from pathable.schemas import RouteRequest, RouteResponse  # noqa: E402

SAMPLE_AUDIT = ROOT / "data" / "fixtures" / "sample_field_audit.csv"
DEFAULT_OUTPUT = ROOT / "docs" / "EVALUATION.md"


def pct(part: int, total: int) -> str:
    return "n/a" if total == 0 else f"{100 * part / total:.0f}%"


def percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, math.ceil(fraction * len(ordered)) - 1))
    return ordered[index]


def route(
    config: Any,
    area: Any,
    graph: Any,
    meta: Any,
    reports: list[dict[str, Any]],
    start: Point,
    end: Point,
    risk: Risk,
) -> tuple[RouteResponse | None, float, str | None]:
    started = time.perf_counter()
    try:
        response = plan_route(
            config,
            graph,
            meta,
            RouteRequest(start=start, end=end, profile="wheelchair", risk=risk),
            area=area,
            reports=reports,
        )
        elapsed = time.perf_counter() - started
        return response, elapsed, None
    except Exception as exc:  # report the concrete API/engine error
        return None, time.perf_counter() - started, f"{type(exc).__name__}: {exc}"


def route_signature(response: RouteResponse | None) -> tuple[str, ...] | None:
    if response is None or response.preferred is None:
        return None
    return tuple(segment.id for segment in response.preferred.segments)


def compare_audits(graph: Any) -> dict[str, dict[str, int]]:
    """Compare original OSM values with the field-audit overlay.

    Agreement rules (documented in the generated file):
    * curb: OSM kerb maps to the same lowered/raised/damaged family;
    * slope: absolute difference <= 1.0 percentage point;
    * width: absolute difference <= 0.15 m.
    OSM is "missing" when it had no value before the audit overlay.
    """
    lowered = {"lowered", "flush", "no"}
    raised = {"raised", "yes", "damaged"}
    counts: dict[str, dict[str, int]] = {
        "curb_ramp": {"audited": 0, "missing": 0, "agree": 0, "disagree": 0},
        "slope": {"audited": 0, "missing": 0, "agree": 0, "disagree": 0},
        "width": {"audited": 0, "missing": 0, "agree": 0, "disagree": 0},
    }
    for _u, _v, _key, data in graph.edges(keys=True, data=True):
        features = data["features"]
        audit = features.audit or {}
        if not audit:
            continue

        curb = (audit.get("curb_ramp") or "").strip().lower()
        if curb:
            counts["curb_ramp"]["audited"] += 1
            osm_kerb = (features.osm_kerb or "").strip().lower()
            if not osm_kerb:
                counts["curb_ramp"]["missing"] += 1
            else:
                if curb in {"yes", "lowered", "flush", "good"}:
                    expected = "lowered"
                elif curb in {"no", "raised", "missing"}:
                    expected = "raised"
                else:
                    expected = "damaged"
                mapped = (
                    "lowered"
                    if osm_kerb in lowered
                    else "raised"
                    if osm_kerb in raised
                    else "unknown"
                )
                key = "agree" if mapped == expected else "disagree"
                counts["curb_ramp"][key] += 1

        if audit.get("measured_slope_pct") not in (None, ""):
            counts["slope"]["audited"] += 1
            osm = features.osm_grade_pct
            if osm is None:
                counts["slope"]["missing"] += 1
            elif abs(float(osm) - float(audit["measured_slope_pct"])) <= 1.0:
                counts["slope"]["agree"] += 1
            else:
                counts["slope"]["disagree"] += 1

        if audit.get("clear_width_m") not in (None, ""):
            counts["width"]["audited"] += 1
            osm = features.osm_width_m
            if osm is None:
                counts["width"]["missing"] += 1
            elif abs(float(osm) - float(audit["clear_width_m"])) <= 0.15:
                counts["width"]["agree"] += 1
            else:
                counts["width"]["disagree"] += 1
    return counts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pairs", type=int, default=40, help="seeded start/end pairs")
    parser.add_argument("--seed", type=int, default=20261025)
    parser.add_argument("--area", help="area id to evaluate (default: active area)")
    parser.add_argument(
        "--demo",
        action="store_true",
        help="use the committed city sample instead of the local live cache",
    )
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument(
        "--use-database",
        action="store_true",
        help="use audits already imported into the configured database",
    )
    parser.add_argument(
        "--audit-file",
        type=Path,
        default=SAMPLE_AUDIT,
        help="audit file to import into a temporary DB (default: labeled sample)",
    )
    args = parser.parse_args(argv)
    if args.pairs < 2:
        parser.error("--pairs must be at least 2")

    config = load_config()
    demo_mode = True if args.demo else None
    if args.area:
        match = next((item for item in config.areas if item.id == args.area), None)
        if match is None:
            parser.error(f"unknown area: {args.area}")
        area = match
    else:
        area = config.area
    output = args.output or (
        DEFAULT_OUTPUT if area.id == config.area.id else ROOT / "docs" / f"EVALUATION-{area.id}.md"
    )
    sample_mode = False
    temp_dir: tempfile.TemporaryDirectory[str] | None = None
    store: ReportStore
    if args.use_database:
        store = ReportStore(config.database_path)
        store.initialize()
    else:
        audit_file = args.audit_file
        if not audit_file.exists():
            parser.error(f"audit file not found: {audit_file}")
        temp_dir = tempfile.TemporaryDirectory(prefix="pathable-eval-")
        store = ReportStore(Path(temp_dir.name) / "eval.db")
        store.initialize()
        bundle_for_snap = load_area_graph(config, area=area, demo_mode=demo_mode)
        if bundle_for_snap.meta.demo_mode:
            print(
                "Note: snapping sample audits onto the demo extract (labeled sample data).",
                file=sys.stderr,
            )
        records = read_audit_file(audit_file)
        is_sample = "sample" in audit_file.name.lower()
        inside = [record for record in records if area_contains(area, record.lat, record.lon)]
        if is_sample and not inside:
            print(
                f"Sample audit is outside {area.name}; skipping audit import for this city.",
                file=sys.stderr,
            )
        else:
            summary = import_records(
                bundle_for_snap.graph,
                store,
                records,
                source_file=audit_file.name,
                max_snap_m=config.routing.max_snap_m,
                dry_run=False,
            )
            if summary["errors"]:
                print("\n".join(summary["errors"]), file=sys.stderr)
            sample_mode = is_sample

    audits = store.audits()
    bundle = load_area_graph(config, area=area, demo_mode=demo_mode, audits=audits)
    graph, meta = bundle.graph, bundle.meta
    reports = store.routing_reports()
    if graph.number_of_nodes() == 0:
        print("No graph available. Run `make data` or set PATHABLE_DEMO=1.", file=sys.stderr)
        return 2

    rng = random.Random(args.seed)
    connected = routable_nodes(graph)
    candidates = [
        (data["features"].lat, data["features"].lon)
        for node, data in graph.nodes(data=True)
        if node in connected
        and data.get("features") is not None
        and area_contains(area, data["features"].lat, data["features"].lon)
    ]
    if len(candidates) < 2:
        print(f"Not enough mapped nodes inside {area.name}; nothing to evaluate.", file=sys.stderr)
        return 2
    pairs: list[tuple[Point, Point]] = []
    attempts = 0
    while len(pairs) < args.pairs and attempts < args.pairs * 50:
        attempts += 1
        start_lat, start_lon = rng.choice(candidates)
        end_lat, end_lon = rng.choice(candidates)
        start = Point(lat=round(start_lat, 7), lon=round(start_lon, 7))
        end = Point(lat=round(end_lat, 7), lon=round(end_lon, 7))
        if haversine_m(start.lat, start.lon, end.lat, end.lon) < 250:
            continue
        pairs.append((start, end))

    detours_m: list[float] = []
    detours_pct: list[float] = []
    shortest_lengths: list[float] = []
    preferred_lengths: list[float] = []
    runtimes: list[float] = []
    coverage: dict[str, list[float]] = defaultdict(list)
    overall_coverage: list[float] = []
    differ = 0
    preferred_barrier_pairs = 0
    barrier_segments = 0
    barrier_length_m = 0.0
    pairs_with_shortest_barriers = 0
    no_preferred = 0
    skipped = 0
    skip_reasons: dict[str, int] = defaultdict(int)
    risk_changes = 0
    risk_compared = 0
    risk_unavailable = 0
    balanced = 0

    for index, (start, end) in enumerate(pairs, start=1):
        response, elapsed, error = route(
            config, area, graph, meta, reports, start, end, Risk.BALANCED
        )
        if error or response is None:
            skipped += 1
            skip_reasons[error or "unknown"] += 1
            continue
        shortest, preferred = response.shortest, response.preferred
        if preferred is None:
            no_preferred += 1
            continue
        runtimes.append(elapsed)
        preferred_lengths.append(preferred.distance_m)
        if shortest is not None:
            shortest_lengths.append(shortest.distance_m)
            detours_m.append(preferred.distance_m - shortest.distance_m)
            if shortest.distance_m > 0:
                detours_pct.append(
                    100 * (preferred.distance_m - shortest.distance_m) / shortest.distance_m
                )
            if tuple(s.id for s in shortest.segments) != tuple(s.id for s in preferred.segments):
                differ += 1
            if shortest.barriers:
                pairs_with_shortest_barriers += 1
            barrier_segments += len(shortest.barriers)
            barrier_length_m += sum(barrier.distance_m for barrier in shortest.barriers)
        if preferred.barriers:
            preferred_barrier_pairs += 1
        if preferred.coverage.overall is not None:
            overall_coverage.append(preferred.coverage.overall)
        for attribute, item in preferred.coverage.attributes.items():
            if item.coverage is not None:
                coverage[attribute].append(item.coverage)

        # Risk comparison: refuse to compare a route we could not compute.
        direct, _, direct_error = route(config, area, graph, meta, reports, start, end, Risk.DIRECT)
        cautious, _, cautious_error = route(
            config, area, graph, meta, reports, start, end, Risk.CAUTIOUS
        )
        if direct_error or cautious_error or direct is None or cautious is None:
            risk_unavailable += 1
        else:
            risk_compared += 1
            if route_signature(direct) != route_signature(cautious):
                risk_changes += 1
        balanced += 1
        if index % 10 == 0:
            print(f"  {index}/{len(pairs)} pairs", file=sys.stderr)

    if not runtimes:
        print("No routes could be computed; nothing to evaluate.", file=sys.stderr)
        return 2

    generated = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    lines: list[str] = []
    lines.append("# Evaluation results\n\n")
    lines.append(
        "Generated by `python scripts/evaluate.py` (seed "
        f"`{args.seed}`, {len(pairs)} requested pairs) on {generated}.\n\n"
    )
    lines.append(
        f"**Area:** {meta.area_name}. Start and destination points are sampled from mapped "
        "pedestrian nodes inside the city boundary, not from a radius-only circle. This keeps "
        "every pair on the network and inside the real city limit.\n\n"
    )
    if meta.demo_mode:
        lines.append(
            "> **DEMO DATA.** The routing graph is the committed OpenStreetMap extract, not "
            "a live download. Results describe that extract and its mapping coverage.\n\n"
        )
    else:
        lines.append(
            f"> Graph source: {meta.source}, fetched {meta.fetched_at}. Area: {meta.area_name}.\n\n"
        )
    if sample_mode:
        lines.append(
            "> **SAMPLE AUDIT DATA - NOT A FINDING.** The field-audit comparison below uses "
            "`data/fixtures/sample_field_audit.csv`, which is fabricated sample data for "
            "testing the import and comparison code. Replace it with your own audit before "
            "quoting any result as a finding about a real place.\n\n"
        )
    elif audits:
        lines.append(
            "> Field-audit rows were loaded from the configured database. Check "
            "`docs/FIELD_AUDIT.md` for the schema and provenance.\n\n"
        )
    else:
        lines.append(
            "> No field audits are loaded for this area. The audit comparison in section 5 "
            "is empty; see `docs/FIELD_AUDIT.md` to collect and import real measurements.\n\n"
        )

    lines.append("## 1. Preferred route vs. length-only shortest\n\n")
    lines.append("| Measure | Result |\n|---|---:|\n")
    lines.append(f"| Pairs requested | {len(pairs)} |\n")
    lines.append(f"| Pairs evaluated (preferred route available) | {len(preferred_lengths)} |\n")
    lines.append(f"| Pairs with no preferred route under hard limits | {no_preferred} |\n")
    lines.append(f"| Pairs skipped (snap/area/engine error) | {skipped} |\n")
    lines.append(
        f"| Pairs where the routes differ | {differ} ({pct(differ, len(preferred_lengths))}) |\n"
    )
    if detours_m:
        lines.append(f"| Median detour | {statistics.median(detours_m):.0f} m |\n")
        lines.append(f"| Mean detour | {statistics.mean(detours_m):.0f} m |\n")
        lines.append(f"| Median detour (relative) | {statistics.median(detours_pct):.0f}% |\n")
        lines.append(f"| Mean detour (relative) | {statistics.mean(detours_pct):.0f}% |\n")
        lines.append(
            f"| Median shortest / preferred length | "
            f"{statistics.median(shortest_lengths):.0f} m / "
            f"{statistics.median(preferred_lengths):.0f} m |\n"
        )
    lines.append(
        f"| Pairs whose shortest route has a hard barrier | {pairs_with_shortest_barriers} |\n"
    )
    lines.append(f"| Barrier segments on shortest routes (total) | {barrier_segments} |\n")
    lines.append(f"| Barrier length on shortest routes (total) | {barrier_length_m:.0f} m |\n")
    lines.append(
        f"| Pairs whose preferred route still has a barrier | {preferred_barrier_pairs} |\n"
    )

    lines.append(
        "\n**Interpretation.** A detour is the price of respecting the profile and "
        "priced uncertainty. It is not evidence that the preferred route is safe: "
        "read the coverage and unknown-data sections before drawing that conclusion.\n\n"
    )

    lines.append("## 2. Data coverage on preferred routes\n\n")
    lines.append(
        "Length-weighted fraction of each route with a known (non-UNKNOWN) value, averaged "
        "over evaluated routes. DEM-estimated grades count as known here; they are not field "
        "measurements. Coverage counts mapped length, not accessibility or safety.\n\n"
    )
    lines.append("| Attribute | Mean coverage | Median coverage | Routes with data |\n")
    lines.append("|---|---:|---:|---:|\n")
    labels = {
        "steps": "Steps",
        "surface": "Surface",
        "smoothness": "Smoothness",
        "width": "Clear width",
        "grade": "Grade / slope",
        "kerb": "Kerb",
        "crossing": "Crossing type",
        "lit": "Lighting",
    }
    for attribute in sorted(coverage):
        values = coverage[attribute]
        lines.append(
            f"| {labels.get(attribute, attribute)} | {100 * statistics.mean(values):.0f}% | "
            f"{100 * statistics.median(values):.0f}% | {len(values)} |\n"
        )
    if overall_coverage:
        lines.append(
            f"| **Overall (unweighted mean of attributes)** | "
            f"**{100 * statistics.mean(overall_coverage):.0f}%** | "
            f"**{100 * statistics.median(overall_coverage):.0f}%** | "
            f"{len(overall_coverage)} |\n"
        )

    lines.append("\n## 3. Sensitivity to the risk setting\n\n")
    lines.append(
        "For each pair, the preferred route is recomputed at `direct`, `balanced` and "
        "`cautious` with everything else fixed. The table compares `direct` with `cautious`; "
        "the route is considered changed if its ordered segment IDs differ.\n\n"
    )
    lines.append("| Measure | Result |\n|---|---:|\n")
    lines.append(f"| Pairs compared | {risk_compared} |\n")
    lines.append(
        f"| Route changed direct → cautious | {risk_changes} "
        f"({pct(risk_changes, risk_compared)}) |\n"
    )
    lines.append(f"| Pairs where a risk variant failed | {risk_unavailable} |\n")
    lines.append(
        "\nThe risk setting only prices *unknown* attributes. If a neighbourhood is well "
        "mapped, moving the slider should change nothing; that is a feature, not a bug.\n\n"
    )

    lines.append("## 4. Runtime\n\n")
    lines.append(
        "In-process routing pipeline time for the balanced request, including both searches, "
        "explanation, coverage and the sensitivity recomputations. It excludes HTTP and GIS "
        "download time.\n\n"
    )
    lines.append("| Measure | Milliseconds |\n|---|---:|\n")
    lines.append(f"| Median (p50) | {1000 * statistics.median(runtimes):.0f} |\n")
    lines.append(f"| p95 | {1000 * percentile(runtimes, 0.95):.0f} |\n")
    lines.append(f"| Maximum | {1000 * max(runtimes):.0f} |\n")

    audit_counts = compare_audits(graph)
    lines.append("\n## 5. OSM vs. field audit\n\n")
    if not audits:
        lines.append(
            "No field audits are loaded. This section is empty; import a CSV with "
            "`python scripts/import_audit.py` first.\n\n"
        )
    else:
        lines.append(
            f"{len(audits)} audit row(s) loaded. Rules: a curb agrees when OSM maps the same "
            "lowered/raised/damaged family; slope agrees within 1.0 percentage point; width "
            "agrees within 0.15 m. `OSM missing` means OSM had no value before the audit "
            "overlay.\n\n"
        )
        lines.append("| Attribute | Audited | OSM missing | OSM agrees | OSM disagrees |\n")
        lines.append("|---|---:|---:|---:|---:|\n")
        for attribute, label in (
            ("curb_ramp", "Curb ramp"),
            ("slope", "Slope"),
            ("width", "Clear width"),
        ):
            item = audit_counts[attribute]
            lines.append(
                f"| {label} | {item['audited']} | {item['missing']} | {item['agree']} | "
                f"{item['disagree']} |\n"
            )
        if sample_mode:
            lines.append(
                "\n**SAMPLE DATA, NOT A FINDING.** These rows were written to exercise the "
                "comparison code. Do not quote these percentages in a submission. Run the "
                "harness again with your own audit to get a real headline.\n\n"
            )
        else:
            total = sum(item["audited"] for item in audit_counts.values())
            missing = sum(item["missing"] for item in audit_counts.values())
            lines.append(
                f"\nAcross the audited rows, OSM lacked the attribute in {missing} of {total} "
                "comparisons. This is a statement about this sample and this neighbourhood, "
                "not about OSM everywhere.\n"
            )

    lines.append("\n## 6. Limitations\n\n")
    lines.append(
        "- One city per report and a finite random sample: these are descriptive statistics, "
        "not a benchmark of every pedestrian network.\n"
        "- The shortest route is length-only by definition. It is not a recommendation and "
        "may cross steps or restricted access.\n"
        "- DEM-estimated slope is coarse (SRTM 30 m). It is not a sidewalk measurement and "
        "can be wrong at bridges, underpasses and building edges.\n"
        "- Coverage counts mapping completeness, not accessibility, maintenance or safety.\n"
        "- Runtime was measured on this machine in one process; it will differ elsewhere.\n"
    )
    if skipped:
        lines.append("\n### Skipped pairs\n")
        for reason, count in sorted(skip_reasons.items(), key=lambda item: -item[1]):
            lines.append(f"- {count} × {reason}\n")

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("".join(lines), encoding="utf-8")
    try:
        shown = output.relative_to(ROOT)
    except ValueError:
        shown = output
    print(f"Wrote {shown}")
    print(
        f"Evaluated {len(preferred_lengths)} of {len(pairs)} pairs; "
        f"{differ} differed; median detour "
        f"{statistics.median(detours_m) if detours_m else 0:.0f} m."
    )
    if temp_dir is not None:
        temp_dir.cleanup()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
