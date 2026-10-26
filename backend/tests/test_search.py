from __future__ import annotations

import networkx as nx
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from pathable.engine.cost import compute_edge_cost
from pathable.engine.search import (
    SnapTooFarError,
    a_star,
    dijkstra,
    haversine_heuristic,
    length_weight,
    routable_nodes,
    snap_to_node,
)
from pathable.graph.loader import haversine_m
from pathable.graph.model import EdgeFeatures, NodeFeatures
from pathable.models import Profile, Provenance, Risk
from tests.fixtures.diamond import build_diamond, build_disconnected

PROFILE = Profile(
    name="property_test",
    steps="penalize",
    respect_wheelchair_tag=False,
    soft_grade_up_pct=20.0,
    hard_grade_up_pct=40.0,
    soft_grade_down_pct=20.0,
    hard_grade_down_pct=40.0,
    hard_grade_action="penalize",
    unknown_surface_factor=0.0,
    unknown_smoothness_factor=0.0,
    unknown_width_factor=0.0,
    unknown_grade_factor=0.0,
    unknown_steps_factor=0.0,
    kerb_unknown_penalty_m=0.0,
    kerb_raised_penalty_m=0.0,
    crossing_unknown_penalty_m=0.0,
    crossing_uncontrolled_penalty_m=0.0,
)

ROUGHNESS = st.sampled_from(["smooth", "moderate", "rough", "very_rough"])


def _feature(length: float, roughness: str, narrow: bool) -> EdgeFeatures:
    return EdgeFeatures(
        length_m=length,
        highway="footway",
        surface="asphalt",
        surface_prov=Provenance.OSM_MAPPED,
        smoothness="good",
        smoothness_prov=Provenance.OSM_MAPPED,
        roughness_class=roughness,
        roughness_prov=Provenance.OSM_MAPPED,
        width_m=0.7 if narrow else 1.5,
        width_prov=Provenance.OSM_MAPPED,
        grade_pct=0.0,
        grade_prov=Provenance.OSM_MAPPED,
        steps_known=True,
        steps_prov=Provenance.OSM_MAPPED,
        access_ok=True,
        access_prov=Provenance.OSM_MAPPED,
        lit=True,
        lit_prov=Provenance.OSM_MAPPED,
    )


@st.composite
def random_walk_graph(draw):
    n = draw(st.integers(min_value=2, max_value=7))
    graph = nx.MultiDiGraph()
    coords = {}
    for node in range(n):
        lat = 40.0 + draw(st.floats(min_value=-0.004, max_value=0.004, allow_nan=False))
        lon = -75.0 + draw(st.floats(min_value=-0.004, max_value=0.004, allow_nan=False))
        coords[node] = (lat, lon)
        graph.add_node(node, x=lon, y=lat, features=NodeFeatures(lat=lat, lon=lon))

    def add_edge(u: int, v: int, key: int) -> None:
        straight = haversine_m(coords[u][0], coords[u][1], coords[v][0], coords[v][1])
        factor = draw(st.floats(min_value=1.0, max_value=2.0, allow_nan=False))
        roughness = draw(ROUGHNESS)
        narrow = draw(st.booleans())
        length = max(straight * factor, straight)
        graph.add_edge(
            u,
            v,
            key=key,
            features=_feature(length, roughness, narrow),
            length=length,
        )

    # Guarantee a path from 0 to n-1.
    for node in range(n - 1):
        add_edge(node, node + 1, 0)
    for u in range(n):
        for v in range(n):
            if u != v and draw(st.booleans()):
                add_edge(u, v, 0)
                if draw(st.booleans()):
                    add_edge(u, v, 1)
    return graph, n


def _cost_weight(profile: Profile):
    def weight(_u, _v, _key, features):
        breakdown = compute_edge_cost(features, profile, Risk.BALANCED)
        return None if breakdown.hard_block else breakdown.total_m_eq

    return weight


@settings(max_examples=50, deadline=None)
@given(random_walk_graph())
def test_astar_matches_dijkstra_and_networkx_oracle(graph_and_n) -> None:
    graph, n = graph_and_n
    weight = _cost_weight(PROFILE)
    d = dijkstra(graph, 0, n - 1, weight)
    a = a_star(graph, 0, n - 1, weight, haversine_heuristic(graph, n - 1))
    assert d is not None and a is not None
    assert a.cost == pytest.approx(d.cost, abs=1e-6)
    assert a.length_m == pytest.approx(d.length_m, abs=1e-6)

    # Independent oracle: collapse parallel edges to their minimum weight.
    simple = nx.DiGraph()
    for u in range(n):
        simple.add_node(u)
    for u, v, _key, data in graph.edges(keys=True, data=True):
        cost = weight(u, v, _key, data["features"])
        if cost is None:
            continue
        if not simple.has_edge(u, v) or cost < simple[u][v]["w"]:
            simple.add_edge(u, v, w=cost)
    expected = nx.dijkstra_path_length(simple, 0, n - 1, weight="w")
    assert a.cost == pytest.approx(expected, abs=1e-6)


@settings(max_examples=30, deadline=None)
@given(random_walk_graph())
def test_astar_length_matches_dijkstra_length(graph_and_n) -> None:
    graph, n = graph_and_n
    d = dijkstra(graph, 0, n - 1, length_weight)
    a = a_star(graph, 0, n - 1, length_weight, haversine_heuristic(graph, n - 1))
    assert d is not None and a is not None
    assert a.cost == pytest.approx(d.cost, abs=1e-6)


def test_parallel_edges_pick_the_minimum() -> None:
    graph = nx.MultiDiGraph()
    graph.add_node("S", x=-75.0, y=40.0, features=NodeFeatures(lat=40.0, lon=-75.0))
    graph.add_node("T", x=-74.999, y=40.0, features=NodeFeatures(lat=40.0, lon=-74.999))
    graph.add_edge("S", "T", key=0, features=_feature(100.0, "smooth", False))
    graph.add_edge("S", "T", key=1, features=_feature(100.0, "rough", False))
    path = dijkstra(graph, "S", "T", _cost_weight(PROFILE))
    assert path is not None
    assert path.edges[0].key == 0
    assert path.cost == pytest.approx(100.0)


def test_ties_are_deterministic() -> None:
    graph = build_diamond()
    weight = _cost_weight(PROFILE)
    first = a_star(graph, "S", "T", weight, haversine_heuristic(graph, "T"))
    second = a_star(graph, "S", "T", weight, haversine_heuristic(graph, "T"))
    assert first is not None and second is not None
    assert first.cost == second.cost
    assert first.nodes == second.nodes


def test_disconnected_returns_none() -> None:
    graph = build_disconnected()
    path = dijkstra(graph, "S", "T", length_weight)
    assert path is None


def test_start_equals_goal() -> None:
    graph = build_diamond()
    path = dijkstra(graph, "S", "S", length_weight)
    assert path is not None
    assert path.cost == 0.0
    assert path.edges == ()


def test_snap_prefers_the_connected_network() -> None:
    graph = build_diamond()
    # A two-node fragment sits almost exactly under the query point. It is
    # closer than the main network but cannot reach it.
    for node, lat, lon in [("frag_a", 40.0, -74.99992), ("frag_b", 40.0, -74.99982)]:
        graph.add_node(node, x=lon, y=lat, features=NodeFeatures(lat=lat, lon=lon))
    features = _feature(8.0, "smooth", narrow=False)
    graph.add_edge("frag_a", "frag_b", key=0, length=8.0, features=features)
    graph.add_edge("frag_b", "frag_a", key=0, length=8.0, features=features)

    eligible = routable_nodes(graph)
    assert "frag_a" not in eligible
    node, distance = snap_to_node(graph, 40.0, -74.99992, 150.0, eligible=eligible)
    assert node == "S"
    assert 0.0 < distance < 15.0


def test_snap_refuses_far_points() -> None:
    graph = build_diamond()
    node, distance = snap_to_node(graph, 40.0, -75.0, 150.0)
    assert node == "S"
    assert distance == pytest.approx(0.0, abs=0.2)
    with pytest.raises(SnapTooFarError):
        snap_to_node(graph, 41.0, -75.0, 150.0)


def test_missing_node_is_an_error() -> None:
    graph = build_diamond()
    with pytest.raises(KeyError):
        dijkstra(graph, "S", "missing", length_weight)
