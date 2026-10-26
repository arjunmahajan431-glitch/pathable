"""Route planning pipeline: search, explanations, coverage, sensitivity.

No FastAPI imports live here, so the whole planner can be tested with synthetic
graphs. Report influence is passed in as plain dictionaries; this module never
touches the database or logs start/end coordinates.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any, Literal

import networkx as nx

from pathable.config import AppConfig, AreaConfig
from pathable.engine import cost as cost_mod
from pathable.engine.coverage import COVERAGE_NOTE, compute_coverage
from pathable.engine.profiles import resolve_profile
from pathable.engine.search import (
    RoutePath,
    a_star,
    haversine_heuristic,
    length_weight,
    routable_nodes,
    snap_to_node,
)
from pathable.graph.area import area_bbox, area_boundary_geojson, area_contains
from pathable.graph.loader import graph_counts, haversine_m
from pathable.graph.model import EdgeFeatures, GraphMeta, edge_uid
from pathable.models import CostBreakdown, Point, Profile, Provenance, Risk
from pathable.reports.status import STATUS_WEIGHT, is_active
from pathable.schemas import (
    AreaOut,
    BarrierOut,
    DataOut,
    ExplanationOut,
    NoFeasibleRouteOut,
    RouteOut,
    RouteRequest,
    RouteResponse,
    SegmentOut,
    SensitivityOut,
    SensitivityVariant,
    SnapOut,
    Warning,
)

RELAXATION_PENALTY_M_EQ = 20_000.0
# Only snap inside the main network when it clearly dominates the graph. A
# fragmented test fixture, or a city extract with many separate paths, should
# still be allowed to snap to whatever is nearest so the engine can report the
# disconnection honestly.
MAIN_NETWORK_SHARE = 0.9
TERM_LABELS = {
    "grade": "Slope",
    "hard_grade": "Slope above your hard limit",
    "surface": "Surface roughness",
    "unknown_surface": "Unmapped surface",
    "unknown_smoothness": "Unmapped smoothness",
    "unknown_width": "Unmapped width",
    "unknown_grade": "Unmapped slope",
    "unknown_steps": "Unmapped steps",
    "unknown_kerb": "Unmapped crossing kerb",
    "unknown_crossing": "Unmapped crossing type",
    "kerb": "Raised or damaged kerb",
    "width": "Narrow width",
    "barrier": "Barrier",
    "steps": "Steps",
    "wheelchair_limited": "wheelchair=limited",
    "crossing_uncontrolled": "Uncontrolled crossing",
    "unlit": "Unlit segment",
    "unknown_lit": "Unmapped lighting",
    "community_report": "Community reports",
}


class OutOfAreaError(ValueError):
    def __init__(
        self,
        which: str,
        distance_m: float,
        radius_m: float,
        *,
        area_name: str | None = None,
        outside_boundary: bool = False,
    ) -> None:
        self.which = which
        self.distance_m = distance_m
        self.radius_m = radius_m
        self.area_name = area_name
        self.outside_boundary = outside_boundary
        if outside_boundary:
            message = (
                f"The {which} point is outside the mapped city boundary"
                f"{f' for {area_name}' if area_name else ''}. "
                "Choose a point inside the selected city."
            )
        else:
            message = (
                f"{which} point is {distance_m:.0f} m from the mapping area center; "
                f"the allowed radius is {radius_m:.0f} m"
            )
        super().__init__(message)


@dataclass
class _Context:
    graph: nx.MultiDiGraph
    profile: Profile
    risk: Risk
    report_penalties: dict[str, tuple[float, list[int]]]
    breakdowns: dict[str, CostBreakdown]
    weights: dict[str, cost_mod.EdgeWeight]

    def breakdown(self, u: Any, v: Any, key: Any, features: EdgeFeatures) -> CostBreakdown:
        uid = edge_uid(u, v, key)
        cached = self.breakdowns.get(uid)
        if cached is not None:
            return cached
        penalty, ids = self.report_penalties.get(uid, (0.0, []))
        breakdown = cost_mod.compute_edge_cost(
            features,
            self.profile,
            self.risk,
            community_penalty_m_eq=penalty,
            community_report_ids=ids,
        )
        self.breakdowns[uid] = breakdown
        return breakdown

    def edge_weight(self, u: Any, v: Any, key: Any, features: EdgeFeatures) -> cost_mod.EdgeWeight:
        uid = edge_uid(u, v, key)
        cached = self.weights.get(uid)
        if cached is not None:
            return cached
        penalty, _ = self.report_penalties.get(uid, (0.0, []))
        weight = cost_mod.compute_edge_weight(
            features,
            self.profile,
            self.risk,
            community_penalty_m_eq=penalty,
        )
        self.weights[uid] = weight
        return weight

    def weight(self, u: Any, v: Any, key: Any, features: EdgeFeatures) -> float | None:
        weight = self.edge_weight(u, v, key, features)
        if weight.hard_block is not None:
            return None
        return weight.total_m_eq

    def relaxed_weight(self, u: Any, v: Any, key: Any, features: EdgeFeatures) -> float | None:
        weight = self.edge_weight(u, v, key, features)
        if weight.hard_block is None:
            return weight.total_m_eq
        # Legal access restrictions are never relaxed. Preference constraints
        # (steps, slope, wheelchair tag, impassable barriers) can be inspected
        # in a clearly labeled alternative.
        if weight.hard_block.attribute == "access":
            return None
        return weight.total_m_eq + RELAXATION_PENALTY_M_EQ


def _check_area(area: AreaConfig, point: Point, which: str) -> None:
    if area_contains(area, point.lat, point.lon):
        return
    distance = haversine_m(area.center.lat, area.center.lon, point.lat, point.lon)
    raise OutOfAreaError(
        which,
        distance,
        area.radius_m,
        area_name=area.name,
        outside_boundary=bool(area.boundary),
    )


def _report_penalties(
    graph: nx.MultiDiGraph,
    reports: Sequence[dict[str, Any]],
    profile: Profile,
    config: AppConfig,
) -> dict[str, tuple[float, list[int]]]:
    """Map edge uid -> (fixed penalty, contributing report ids)."""
    active = [r for r in reports if is_active(r, config.reports.expiry_days)]
    if not active:
        return {}
    radius = config.reports.influence_radius_m
    penalties: dict[str, tuple[float, list[int]]] = {}
    for u, v, key, data in graph.edges(keys=True, data=True):
        features: EdgeFeatures = data["features"]
        if features.coords:
            mid_lon, mid_lat = features.coords[len(features.coords) // 2]
        else:
            mid_lat = (graph.nodes[u]["features"].lat + graph.nodes[v]["features"].lat) / 2
            mid_lon = (graph.nodes[u]["features"].lon + graph.nodes[v]["features"].lon) / 2
        total = 0.0
        ids: list[int] = []
        for report in active:
            if haversine_m(mid_lat, mid_lon, float(report["lat"]), float(report["lon"])) > radius:
                continue
            weight = STATUS_WEIGHT.get(str(report.get("status")), 0.0)
            total += profile.community_report_penalties_m.get(str(report["category"]), 0.0) * weight
            ids.append(int(report["id"]))
        if total > 0:
            penalties[edge_uid(u, v, key)] = (round(total, 3), sorted(ids))
    return penalties


def _unknown_attributes(features: EdgeFeatures, profile: Profile) -> list[str]:
    checks = {
        "steps": features.steps_prov,
        "surface": features.surface_prov,
        "smoothness": features.smoothness_prov,
        "width": features.width_prov,
        "grade": features.grade_prov,
    }
    if features.is_crossing:
        checks["kerb"] = features.kerb_prov
    if profile.avoid_unlit:
        checks["lit"] = features.lit_prov
    return [name for name, prov in checks.items() if prov is Provenance.UNKNOWN]


def _provenance_map(features: EdgeFeatures) -> dict[str, Provenance]:
    return {
        "steps": features.steps_prov,
        "surface": features.surface_prov,
        "smoothness": features.smoothness_prov,
        "width": features.width_prov,
        "grade": features.grade_prov,
        "kerb": features.kerb_prov,
        "lit": features.lit_prov,
        "crossing": features.crossing_prov,
    }


def _route_out(
    ctx: _Context,
    path: RoutePath | None,
    kind: Literal["shortest", "preferred", "relaxed"],
    *,
    is_relaxed: bool = False,
    relaxed_constraints: list[str] | None = None,
) -> RouteOut | None:
    if path is None:
        return None
    graph = ctx.graph
    segments: list[SegmentOut] = []
    barriers: list[BarrierOut] = []
    coords: list[tuple[float, float]] = []
    features_list: list[EdgeFeatures] = []
    if not path.edges:
        features = graph.nodes[path.nodes[0]]["features"]
        point = (features.lon, features.lat)
        coords = [point, point]
    for step in path.edges:
        features = graph.get_edge_data(step.u, step.v, step.key)["features"]
        features_list.append(features)
        breakdown = ctx.breakdown(step.u, step.v, step.key, features)
        uid = edge_uid(step.u, step.v, step.key)
        if breakdown.hard_block is not None:
            barriers.append(
                BarrierOut(
                    segment_id=uid,
                    reason=breakdown.hard_block.reason,
                    attribute=breakdown.hard_block.attribute,
                    provenance=breakdown.hard_block.provenance,
                    street_name=features.street_name,
                    distance_m=features.length_m,
                )
            )
        segments.append(
            SegmentOut(
                id=uid,
                u=str(step.u),
                v=str(step.v),
                key=str(step.key),
                street_name=features.street_name,
                highway=features.highway,
                coords=[(round(x, 7), round(y, 7)) for x, y in features.coords],
                length_m=features.length_m,
                surface=features.surface,
                smoothness=features.smoothness,
                width_m=features.width_m,
                grade_pct=features.grade_pct,
                is_crossing=features.is_crossing,
                kerb=features.kerb,
                provenance=_provenance_map(features),
                unknown_attributes=_unknown_attributes(features, ctx.profile),
                cost=breakdown,
                field_audit=bool(features.audit),
            )
        )
        edge_coords = [(float(x), float(y)) for x, y in features.coords]
        if not edge_coords:
            uf = graph.nodes[step.u]["features"]
            vf = graph.nodes[step.v]["features"]
            edge_coords = [(uf.lon, uf.lat), (vf.lon, vf.lat)]
        if coords and edge_coords and coords[-1] == edge_coords[0]:
            coords.extend(edge_coords[1:])
        else:
            coords.extend(edge_coords)

    coverage = compute_coverage(features_list, ctx.profile)
    cost = round(sum(segment.cost.total_m_eq for segment in segments), 6)
    distance = round(path.length_m, 3)
    minutes = round(distance / ctx.profile.walking_speed_mps / 60.0, 1) if distance else 0.0
    geometry = {
        "type": "LineString",
        "coordinates": [[round(lon, 7), round(lat, 7)] for lon, lat in coords],
    }
    return RouteOut(
        kind=kind,
        distance_m=distance,
        cost_m_eq=cost,
        estimated_minutes=minutes,
        speed_mps=ctx.profile.walking_speed_mps,
        geometry=geometry,
        segments=segments,
        barriers=barriers,
        coverage=coverage,
        is_relaxed=is_relaxed,
        relaxed_constraints=relaxed_constraints or [],
    )


def _top_terms(route: RouteOut) -> list[str]:
    totals: dict[str, float] = {}
    reasons: dict[str, str] = {}
    for segment in route.segments:
        for term in segment.cost.terms:
            totals[term.name] = totals.get(term.name, 0.0) + term.m_eq
            reasons.setdefault(term.name, term.reason)
    ordered = sorted(totals.items(), key=lambda item: (-item[1], item[0]))
    bullets: list[str] = []
    for name, value in ordered[:4]:
        label = TERM_LABELS.get(name, name.replace("_", " "))
        bullets.append(f"{label}: +{value:.0f} m-eq. {reasons.get(name, '')}".strip())
    return bullets


def _barrier_bullets(route: RouteOut | None) -> list[str]:
    if route is None:
        return []
    bullets: list[str] = []
    for barrier in route.barriers:
        street = f" on {barrier.street_name}" if barrier.street_name else ""
        bullets.append(
            f"Avoided {barrier.distance_m:.0f} m{street}: {barrier.reason} "
            f"({barrier.provenance.value})."
        )
    return bullets


def _unknown_bullets(route: RouteOut) -> list[str]:
    bullets: list[str] = []
    for item in route.coverage.attributes.values():
        if item.coverage is None or item.coverage >= 0.9999:
            continue
        unknown_m = item.total_length_m - item.known_length_m
        bullets.append(
            f"{item.label}: unknown on {unknown_m:.0f} m "
            f"({(1 - item.coverage) * 100:.0f}% of the route's relevant length)."
        )
    estimated = sum(
        segment.length_m
        for segment in route.segments
        if segment.provenance.get("grade") is Provenance.DEM_ESTIMATED
    )
    if estimated > 0:
        bullets.append(
            f"{estimated:.0f} m of slope is ESTIMATED from 30 m elevation data, not measured "
            "on the sidewalk. Bridges and underpasses can be misrepresented."
        )
    return bullets


def _report_bullets(
    ctx: _Context, route: RouteOut, reports_by_id: dict[int, dict[str, Any]]
) -> list[str]:
    ids: set[int] = set()
    for segment in route.segments:
        _, seg_ids = ctx.report_penalties.get(segment.id, (0.0, []))
        ids.update(seg_ids)
    bullets: list[str] = []
    for report_id in sorted(ids):
        report = reports_by_id.get(report_id)
        if not report:
            continue
        status = str(report.get("status", "unverified"))
        description = str(report.get("description") or "").strip()
        suffix = f' - "{description[:120]}"' if description else ""
        bullets.append(
            f"Report #{report_id} ({status}): {str(report.get('category')).replace('_', ' ')}"
            f"{suffix}."
        )
    return bullets[:5]


def _assumptions(profile: Profile) -> list[str]:
    return [
        (
            f"Travel time is an estimate at {profile.walking_speed_mps:.2f} m/s, a "
            "user-adjustable assumption; it does not affect the route."
        ),
        ("Costs are in meter-equivalents (m-eq), a relative effort unit, not minutes or calories."),
        (
            "Community reports are unverified unless an admin marks them reviewed; "
            "unverified reports count half."
        ),
        (
            "Unknown data is priced according to the risk setting; it is never assumed "
            "safe or blocked."
        ),
        ("This tool gives routing information, not medical, legal or engineering advice."),
    ]


def _warnings(
    meta: GraphMeta,
    area: AreaOut,
    route: RouteOut | None,
    snap: SnapOut,
    config: AppConfig,
    load_warnings: Iterable[str],
) -> list[Warning]:
    warnings: list[Warning] = []
    for message in load_warnings:
        warnings.append(Warning(code="data", message=message, severity="warning"))
    if meta.demo_mode:
        warnings.append(
            Warning(
                code="demo_mode",
                message=(
                    f"DEMO MODE: {meta.demo_reason}. Data source: {meta.source}, "
                    f"{meta.fetched_at}. Routes may not reflect current conditions."
                ),
                severity="warning",
            )
        )
    if area.is_placeholder:
        warnings.append(
            Warning(
                code="placeholder_area",
                message=(
                    "This build uses a PLACEHOLDER mapping area, not the student's community. "
                    "Replace config/areas.yaml and rerun the data/evaluation steps."
                ),
                severity="warning",
            )
        )
    if not meta.elevation_source:
        warnings.append(
            Warning(
                code="no_elevation",
                message=(
                    "No elevation data is loaded; unmapped grades remain UNKNOWN and are "
                    "priced as risk."
                ),
                severity="warning",
            )
        )
    if snap.start_distance_m > config.routing.snap_warning_m:
        warnings.append(
            Warning(
                code="snap_start",
                message=(
                    f"Start point is {snap.start_distance_m:.0f} m from the nearest mapped path."
                ),
                severity="warning",
            )
        )
    if snap.end_distance_m > config.routing.snap_warning_m:
        warnings.append(
            Warning(
                code="snap_end",
                message=(
                    f"Destination is {snap.end_distance_m:.0f} m from the nearest mapped path."
                ),
                severity="warning",
            )
        )
    if route and route.coverage.overall is not None and route.coverage.overall < 0.5:
        warnings.append(
            Warning(
                code="low_coverage",
                message=(
                    f"Less than half of the relevant attributes are mapped on the preferred "
                    f"route (coverage {route.coverage.overall * 100:.0f}%). Unknown data is "
                    "priced as risk, not assumed safe."
                ),
                severity="warning",
            )
        )
    if route and any(
        segment.provenance.get("grade") is Provenance.DEM_ESTIMATED for segment in route.segments
    ):
        warnings.append(
            Warning(
                code="dem_grade",
                message=(
                    "Some slopes are estimated from 30 m DEM data; this is not a measurement "
                    "of the sidewalk and can be wrong near bridges, underpasses and buildings."
                ),
                severity="info",
            )
        )
    if route and any(
        segment.cost.terms and any(t.name == "community_report" for t in segment.cost.terms)
        for segment in route.segments
    ):
        warnings.append(
            Warning(
                code="community_reports",
                message="Community reports influence this route. Unverified reports count half.",
                severity="info",
            )
        )
    return warnings


def _route_uids(path: RoutePath | None) -> tuple[str, ...]:
    if path is None:
        return ()
    return tuple(edge_uid(step.u, step.v, step.key) for step in path.edges)


def _sensitivity(
    ctx: _Context,
    start: Any,
    end: Any,
    baseline: RoutePath,
    config: AppConfig,
) -> list[SensitivityOut]:
    profile = ctx.profile
    values: list[float] = []
    for delta in (-1.0, 1.0):
        candidate = round(profile.hard_grade_up_pct + delta, 2)
        candidate = max(profile.soft_grade_up_pct + 0.1, min(25.0, candidate))
        if candidate != profile.hard_grade_up_pct and candidate not in values:
            values.append(candidate)
    if not values:
        return []
    baseline_uids = _route_uids(baseline)
    variants: list[SensitivityVariant] = []
    for value in sorted(values):
        variant_profile = Profile.model_validate(
            {**profile.model_dump(), "hard_grade_up_pct": value}
        )
        variant_ctx = _Context(
            graph=ctx.graph,
            profile=variant_profile,
            risk=ctx.risk,
            report_penalties=ctx.report_penalties,
            breakdowns={},
            weights={},
        )
        path = a_star(
            ctx.graph,
            start,
            end,
            variant_ctx.weight,
            haversine_heuristic(ctx.graph, end),
        )
        if path is None:
            variants.append(
                SensitivityVariant(
                    value=value,
                    distance_m=None,
                    cost_m_eq=None,
                    differs_from_baseline=True,
                    route_available=False,
                    description=f"At {value:.1f}% no route satisfies the hard limits.",
                )
            )
            continue
        differs = _route_uids(path) != baseline_uids
        out = _route_out(variant_ctx, path, "preferred")
        variants.append(
            SensitivityVariant(
                value=value,
                distance_m=round(path.length_m, 1),
                cost_m_eq=round(out.cost_m_eq, 1) if out else None,
                differs_from_baseline=differs,
                route_available=True,
                description=(
                    f"At {value:.1f}% the route is {path.length_m:.0f} m"
                    + (" and changes." if differs else " and is unchanged.")
                ),
            )
        )
    return [
        SensitivityOut(
            parameter="hard_grade_up_pct",
            label="Hard uphill slope limit",
            baseline_value=profile.hard_grade_up_pct,
            unit="%",
            variants=variants,
            note=(
                "Recomputed with the same start, destination, profile, risk and reports; "
                "only this setting changed. This is a deterministic check, not a prediction."
            ),
        )
    ]


def _explanation(
    ctx: _Context,
    shortest: RouteOut | None,
    preferred: RouteOut,
    reports_by_id: dict[int, dict[str, Any]],
) -> ExplanationOut:
    detour = preferred.distance_m - (shortest.distance_m if shortest else preferred.distance_m)
    if shortest and shortest.distance_m > 0:
        pct = detour / shortest.distance_m * 100
        comparison = (
            f"The preferred route is {preferred.distance_m:.0f} m, "
            f"{detour:+.0f} m ({pct:+.0f}%) versus the length-only route."
        )
    else:
        comparison = f"The preferred route is {preferred.distance_m:.0f} m."
    barrier_count = len(shortest.barriers) if shortest else 0
    if shortest and _route_uids_from_out(shortest) == _route_uids_from_out(preferred):
        summary = (
            f"{comparison} The length-only route is also the preferred route under this profile."
        )
    elif shortest and barrier_count:
        summary = (
            f"{comparison} It avoids {barrier_count} mapped barrier "
            f"{'segment' if barrier_count == 1 else 'segments'} that the length-only route uses."
        )
    elif shortest:
        summary = (
            f"{comparison} It avoids the steepest or least-mapped segments on the length-only "
            "route."
        )
    else:
        summary = comparison

    why = _top_terms(preferred)
    avoided = _barrier_bullets(shortest)
    if avoided:
        why.append("Barriers on the length-only route that this route avoids:")
        why.extend(f"  • {line.rstrip('.')}." for line in avoided[:4])
    if not why:
        why = ["No segment on this route triggered a cost penalty under this profile."]

    why_not: list[str] = []
    if shortest is None:
        why_not = ["No length-only route exists between these points."]
    elif shortest.segments:
        penalized: list[tuple[float, str]] = []
        for segment in shortest.segments:
            penalty = segment.cost.total_m_eq - segment.length_m
            if segment.cost.hard_block is not None:
                reason = segment.cost.hard_block.reason.rstrip(".")
                penalized.append(
                    (
                        1e12,
                        f"{segment.street_name or 'Unnamed segment'} "
                        f"({segment.length_m:.0f} m): BLOCKED - {reason}.",
                    )
                )
            elif penalty > 0.01:
                top = max(segment.cost.terms, key=lambda t: t.m_eq, default=None)
                reason = (top.reason if top else "penalized").rstrip(".")
                penalized.append(
                    (
                        penalty,
                        f"{segment.street_name or 'Unnamed segment'} "
                        f"({segment.length_m:.0f} m): +{penalty:.0f} m-eq - {reason}.",
                    )
                )
        why_not = [text for _, text in sorted(penalized, key=lambda item: -item[0])[:6]]
        if not why_not:
            why_not = [
                "No segment on the length-only route is penalized under this profile, "
                "so the preferred route is the same or differs only by a tie-break."
            ]
    else:
        why_not = ["The start and destination snapped to the same pedestrian node."]

    unknowns = _unknown_bullets(preferred)
    if not unknowns:
        unknowns = ["Every attribute used by this profile is mapped on this route."]
    unknown_dem_note = (
        "Coverage counts DEM-estimated grades as known, but they are not field measurements."
        if any(
            segment.provenance.get("grade") is Provenance.DEM_ESTIMATED
            for segment in preferred.segments
        )
        else ""
    )
    reports = _report_bullets(ctx, preferred, reports_by_id)
    if not reports:
        reports = ["No community reports are influencing this route."]
    return ExplanationOut(
        summary=summary,
        why_this_route=why,
        why_not_shortest=why_not,
        what_we_dont_know=unknowns + ([unknown_dem_note] if unknown_dem_note else []),
        reports=reports,
        assumptions=_assumptions(ctx.profile),
        coverage_note=COVERAGE_NOTE,
    )


def _route_uids_from_out(route: RouteOut) -> tuple[str, ...]:
    return tuple(segment.id for segment in route.segments)


def _no_feasible(
    ctx: _Context,
    shortest_path: RoutePath | None,
    start: Any,
    end: Any,
) -> tuple[NoFeasibleRouteOut, RoutePath | None, list[str]]:
    if shortest_path is None:
        return (
            NoFeasibleRouteOut(
                code="disconnected",
                message=(
                    "The start and destination are on disconnected parts of the mapped "
                    "pedestrian network. There may be an unmapped connection."
                ),
                blocking_reasons=["no path exists in the graph, even ignoring the profile"],
                shortest_route_available=False,
                relaxed_alternative_available=False,
            ),
            None,
            [],
        )

    reasons: list[str] = []
    attributes: list[str] = []
    for step in shortest_path.edges:
        features = ctx.graph.get_edge_data(step.u, step.v, step.key)["features"]
        breakdown = ctx.breakdown(step.u, step.v, step.key, features)
        if breakdown.hard_block:
            reasons.append(breakdown.hard_block.reason)
            attributes.append(breakdown.hard_block.attribute)
    reasons = list(dict.fromkeys(reasons))
    attributes = list(dict.fromkeys(attributes))

    relaxed_path = a_star(
        ctx.graph,
        start,
        end,
        ctx.relaxed_weight,
        haversine_heuristic(ctx.graph, end),
    )
    relaxed_constraints: list[str] = []
    if relaxed_path is not None:
        for step in relaxed_path.edges:
            features = ctx.graph.get_edge_data(step.u, step.v, step.key)["features"]
            breakdown = ctx.breakdown(step.u, step.v, step.key, features)
            if breakdown.hard_block:
                relaxed_constraints.append(breakdown.hard_block.attribute)
        relaxed_constraints = list(dict.fromkeys(relaxed_constraints))
    reason_text = "; ".join(reasons) if reasons else "a hard profile constraint"
    message = (
        "No route satisfies your hard limits. The length-only connection is blocked by: "
        f"{reason_text}."
    )
    return (
        NoFeasibleRouteOut(
            code="hard_constraints",
            message=message,
            blocking_reasons=reasons or ["hard constraint"],
            shortest_route_available=True,
            relaxed_alternative_available=relaxed_path is not None,
        ),
        relaxed_path,
        relaxed_constraints,
    )


def plan_route(
    config: AppConfig,
    graph: nx.MultiDiGraph,
    meta: GraphMeta,
    request: RouteRequest,
    *,
    area: AreaConfig | None = None,
    reports: Sequence[dict[str, Any]] = (),
    load_warnings: Iterable[str] = (),
) -> RouteResponse:
    """Plan both routes and build every explanation deterministically.

    ``area`` is the area that is currently loaded in memory. It defaults to the
    config's active area, but the API passes the live selection so switching
    cities cannot leave routing checks pointed at the old city.
    """
    active_area = area or config.area
    profile = resolve_profile(request.profile)
    risk = request.risk
    _check_area(active_area, request.start, "Start")
    _check_area(active_area, request.end, "Destination")
    connected = routable_nodes(graph)
    node_count, edge_count = graph_counts(graph)
    eligible = (
        connected if node_count and len(connected) >= MAIN_NETWORK_SHARE * node_count else None
    )
    start, start_distance = snap_to_node(
        graph,
        request.start.lat,
        request.start.lon,
        config.routing.max_snap_m,
        eligible=eligible,
    )
    end, end_distance = snap_to_node(
        graph,
        request.end.lat,
        request.end.lon,
        config.routing.max_snap_m,
        eligible=eligible,
    )
    snap = SnapOut(start_distance_m=round(start_distance, 1), end_distance_m=round(end_distance, 1))

    report_penalties = _report_penalties(graph, reports, profile, config)
    ctx = _Context(
        graph=graph,
        profile=profile,
        risk=risk,
        report_penalties=report_penalties,
        breakdowns={},
        weights={},
    )

    shortest_path = a_star(graph, start, end, length_weight, haversine_heuristic(graph, end))
    preferred_path = a_star(graph, start, end, ctx.weight, haversine_heuristic(graph, end))

    shortest_out = _route_out(ctx, shortest_path, "shortest")
    preferred_out = _route_out(ctx, preferred_path, "preferred")

    no_feasible: NoFeasibleRouteOut | None = None
    relaxed_out: RouteOut | None = None
    if preferred_path is None:
        no_feasible, relaxed_path, relaxed_constraints = _no_feasible(
            ctx, shortest_path, start, end
        )
        if relaxed_path is not None:
            relaxed_out = _route_out(
                ctx,
                relaxed_path,
                "relaxed",
                is_relaxed=True,
                relaxed_constraints=relaxed_constraints,
            )
            no_feasible.relaxed_alternative_available = True

    reports_by_id = {int(report["id"]): report for report in reports}
    explanation = (
        _explanation(ctx, shortest_out, preferred_out, reports_by_id)
        if preferred_out is not None
        else None
    )
    sensitivity = (
        _sensitivity(ctx, start, end, preferred_path, config) if preferred_path is not None else []
    )

    boundary = area_boundary_geojson(active_area)
    area_out = AreaOut(
        id=active_area.id,
        name=active_area.name,
        center=Point(lat=active_area.center.lat, lon=active_area.center.lon),
        radius_m=active_area.radius_m,
        is_placeholder=active_area.is_placeholder,
        note=active_area.note,
        boundary=boundary,
        bbox=list(area_bbox(active_area)) if boundary is not None else None,
    )
    data = DataOut(
        source=meta.source,
        fetched_at=meta.fetched_at,
        demo_mode=meta.demo_mode,
        demo_reason=meta.demo_reason,
        elevation_source=meta.elevation_source,
        elevation_date=meta.elevation_date,
        nodes=node_count,
        edges=edge_count,
    )
    warnings = _warnings(meta, area_out, preferred_out, snap, config, load_warnings)
    return RouteResponse(
        area=area_out,
        data=data,
        profile=profile.model_dump(mode="json"),
        risk=risk,
        shortest=shortest_out,
        preferred=preferred_out,
        relaxed_alternative=relaxed_out,
        no_feasible_route=no_feasible,
        explanation=explanation,
        sensitivity=sensitivity,
        warnings=warnings,
        snap=snap,
    )
