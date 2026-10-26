from __future__ import annotations

import pytest

from pathable.engine.coverage import compute_coverage
from pathable.engine.search import a_star, haversine_heuristic
from pathable.graph.model import EdgeFeatures
from pathable.models import Provenance, Risk
from tests.fixtures.diamond import TEST_PROFILE, build_diamond


def _preferred(graph, risk=Risk.BALANCED, profile=TEST_PROFILE):
    from pathable.engine.cost import compute_edge_cost

    def weight(u, v, k, f):
        b = compute_edge_cost(f, profile, risk)
        return None if b.hard_block else b.total_m_eq

    return a_star(graph, "S", "T", weight, haversine_heuristic(graph, "T"))


def test_fully_mapped_route_has_full_coverage() -> None:
    graph = build_diamond()
    path = _preferred(graph)
    assert path is not None
    features = [graph[e.u][e.v][e.key]["features"] for e in path.edges]
    coverage = compute_coverage(features, TEST_PROFILE)
    assert coverage.overall == pytest.approx(1.0)
    for attribute in ("steps", "surface", "smoothness", "width", "grade"):
        assert coverage.attributes[attribute].coverage == pytest.approx(1.0)


def test_unknown_crossing_kerb_lowers_coverage_by_one_attribute() -> None:
    graph = build_diamond()
    profile = TEST_PROFILE.model_copy(update={"hard_grade_up_pct": 5.5})
    path = _preferred(graph, Risk.DIRECT, profile)
    assert path is not None and path.nodes[1] == "D"
    features = [graph[e.u][e.v][e.key]["features"] for e in path.edges]
    coverage = compute_coverage(features, profile)
    assert coverage.attributes["kerb"].coverage == pytest.approx(0.0)
    # Five fully mapped attributes and one zero attribute -> 5/6
    assert coverage.overall == pytest.approx(5.0 / 6.0, abs=1e-6)


def test_kerb_denominator_only_counts_crossings() -> None:
    features = [
        EdgeFeatures(length_m=100.0, steps_known=True),
        EdgeFeatures(
            length_m=100.0,
            steps_known=True,
            is_crossing=True,
            kerb="lowered",
            kerb_prov=Provenance.OSM_MAPPED,
        ),
    ]
    coverage = compute_coverage(features, TEST_PROFILE)
    assert coverage.attributes["kerb"].total_length_m == pytest.approx(100.0)
    assert coverage.attributes["kerb"].coverage == pytest.approx(1.0)
    # Non-crossing edge is not in the kerb denominator.
    assert coverage.attributes["kerb"].note


def test_coverage_is_length_weighted() -> None:
    known = EdgeFeatures(
        length_m=300.0,
        surface="asphalt",
        surface_prov=Provenance.OSM_MAPPED,
        steps_known=True,
    )
    unknown = EdgeFeatures(length_m=100.0, surface_prov=Provenance.UNKNOWN, steps_known=True)
    coverage = compute_coverage([known, unknown], TEST_PROFILE)
    assert coverage.attributes["surface"].coverage == pytest.approx(0.75)
    assert coverage.attributes["surface"].known_length_m == pytest.approx(300.0)
    assert coverage.attributes["surface"].total_length_m == pytest.approx(400.0)


def test_empty_route_has_no_overall_coverage() -> None:
    coverage = compute_coverage([], TEST_PROFILE)
    assert coverage.overall is None
    assert coverage.attributes["surface"].coverage is None
