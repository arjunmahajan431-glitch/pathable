"""Synthetic four-route diamond used by the hand-calculated routing tests.

THIS GRAPH IS SYNTHETIC. It is not a real place and its coordinates are only
used to keep the A* heuristic geometrically consistent. Every length is an
explicit constant so the expected costs in the tests can be computed by hand.

Route 1 (via A): 250 m + 50 m = 300 m, the last edge is mapped steps.
Route 2 (via B): 100 m flat + 100 m at 6% grade + 180 m flat = 380 m.
Route 3 (via C): 190 m flat + 150 m very rough = 340 m.
Route 4 (via D): 400 m flat + 120 m flat crossing with an unknown kerb = 520 m.

All routes except the steps edge and the unknown kerb are fully mapped, which
keeps the hand arithmetic isolated: any unexpected unknown-data penalty in the
test profile would make the expected numbers fail.
"""

from __future__ import annotations

import networkx as nx

from pathable.graph.model import EdgeFeatures, GraphMeta, NodeFeatures
from pathable.models import Profile, Provenance

# Coordinates are near (40.0000, -75.0000), a neutral synthetic location.
COORDS = {
    "S": (40.0000, -75.0000),
    "T": (40.0020, -75.0000),
    "A": (40.0018, -74.9997),
    "B": (40.0006, -75.0005),
    "B2": (40.0012, -75.0008),
    "C": (40.0010, -74.9989),
    "D": (40.0022, -74.9990),
}

TEST_PROFILE = Profile(
    name="test_wheelchair",
    label="Synthetic test profile",
    description="Tests only. Not a recommended real-world profile.",
    steps="block",
    steps_penalty_m=0.0,
    respect_wheelchair_tag=False,
    soft_grade_up_pct=5.0,
    hard_grade_up_pct=8.0,
    soft_grade_down_pct=5.0,
    hard_grade_down_pct=8.0,
    grade_factor_up=0.25,
    grade_factor_down=0.25,
    hard_grade_action="block",
    hard_grade_penalty_m=0.0,
    surface_multipliers={"smooth": 1.0, "moderate": 1.5, "rough": 2.0, "very_rough": 3.0},
    unknown_surface_factor=0.0,
    unknown_smoothness_factor=0.0,
    unknown_width_factor=0.0,
    unknown_grade_factor=0.0,
    unknown_steps_factor=0.0,
    unknown_lit_factor=0.0,
    kerb_raised_penalty_m=75.0,
    kerb_unknown_penalty_m=75.0,
    crossing_uncontrolled_penalty_m=0.0,
    crossing_unknown_penalty_m=0.0,
    barrier_penalty_m=0.0,
    min_width_m=0.9,
    walking_speed_mps=0.8,
)


def _features(length_m: float, **overrides: object) -> EdgeFeatures:
    base = EdgeFeatures(
        length_m=length_m,
        highway="footway",
        footway="sidewalk",
        street_name="Synthetic Street",
        surface="asphalt",
        surface_prov=Provenance.OSM_MAPPED,
        smoothness="good",
        smoothness_prov=Provenance.OSM_MAPPED,
        roughness_class="smooth",
        roughness_prov=Provenance.OSM_MAPPED,
        width_m=1.5,
        width_prov=Provenance.OSM_MAPPED,
        grade_pct=0.0,
        grade_prov=Provenance.OSM_MAPPED,
        steps_known=True,
        steps_prov=Provenance.OSM_MAPPED,
        access_ok=True,
        access_reason="synthetic fixture",
        access_prov=Provenance.OSM_MAPPED,
        lit=True,
        lit_prov=Provenance.OSM_MAPPED,
        crossing_prov=Provenance.OSM_MAPPED,
        coords=(),
    )
    for key, value in overrides.items():
        setattr(base, key, value)
    return base


def build_diamond() -> nx.MultiDiGraph:
    graph = nx.MultiDiGraph()
    meta = GraphMeta(
        area_id="synthetic-diamond",
        area_name="Synthetic diamond (test fixture)",
        center_lat=40.001,
        center_lon=-75.0,
        radius_m=500,
        source="synthetic test fixture",
        fetched_at="2026-01-01",
        demo_mode=True,
        demo_reason="unit test fixture",
    )
    graph.graph["meta"] = meta
    for node, (lat, lon) in COORDS.items():
        graph.add_node(node, x=lon, y=lat, features=NodeFeatures(lat=lat, lon=lon))

    def add(u: str, v: str, length: float, **overrides: object) -> None:
        coords = (
            (COORDS[u][1], COORDS[u][0]),
            (COORDS[v][1], COORDS[v][0]),
        )
        graph.add_edge(
            u, v, key=0, length=length, features=_features(length, coords=coords, **overrides)
        )

    # Route 1: the last edge is steps, so the whole route is blocked in the test profile.
    add("S", "A", 250.0)
    add(
        "A",
        "T",
        50.0,
        is_steps=True,
        highway="steps",
        steps_known=True,
        steps_prov=Provenance.OSM_MAPPED,
        surface="concrete",
        surface_prov=Provenance.OSM_MAPPED,
    )

    # Route 2: the middle edge is the 100 m, 6% uphill segment.
    add("S", "B", 100.0)
    add(
        "B",
        "B2",
        100.0,
        grade_pct=6.0,
        grade_prov=Provenance.OSM_MAPPED,
        incline_raw="6%",
    )
    add("B2", "T", 180.0)

    # Route 3: the final edge is very rough.
    add("S", "C", 190.0)
    add(
        "C",
        "T",
        150.0,
        surface="cobblestone",
        surface_prov=Provenance.OSM_MAPPED,
        smoothness="bad",
        smoothness_prov=Provenance.OSM_MAPPED,
        roughness_class="very_rough",
        roughness_prov=Provenance.OSM_MAPPED,
    )

    # Route 4: a marked crossing whose arrival kerb is not mapped.
    add("S", "D", 400.0)
    add(
        "D",
        "T",
        120.0,
        is_crossing=True,
        crossing="marked",
        crossing_prov=Provenance.OSM_MAPPED,
        kerb=None,
        kerb_prov=Provenance.UNKNOWN,
    )
    return graph


def build_steps_only() -> nx.MultiDiGraph:
    """Tiny fixture: the only connection contains steps."""
    graph = nx.MultiDiGraph()
    graph.graph["meta"] = GraphMeta(
        area_id="synthetic-steps",
        area_name="Synthetic steps-only (test fixture)",
        center_lat=40.0,
        center_lon=-75.0,
        radius_m=100,
        source="synthetic test fixture",
        fetched_at="2026-01-01",
        demo_mode=True,
    )
    for node, (lat, lon) in {"S": (40.0, -75.0), "T": (40.0, -74.999)}.items():
        graph.add_node(node, x=lon, y=lat, features=NodeFeatures(lat=lat, lon=lon))
    graph.add_edge(
        "S",
        "T",
        key=0,
        length=50.0,
        features=_features(50.0, is_steps=True, highway="steps"),
    )
    return graph


def build_disconnected() -> nx.MultiDiGraph:
    graph = nx.MultiDiGraph()
    graph.graph["meta"] = GraphMeta(
        area_id="synthetic-disconnected",
        area_name="Synthetic disconnected (test fixture)",
        center_lat=40.0,
        center_lon=-75.0,
        radius_m=100,
        source="synthetic test fixture",
        fetched_at="2026-01-01",
        demo_mode=True,
    )
    for node, (lat, lon) in {"S": (40.0, -75.0), "T": (40.0, -74.999)}.items():
        graph.add_node(node, x=lon, y=lat, features=NodeFeatures(lat=lat, lon=lon))
    return graph
