"""Hand-calculated cost tests.

Expected values are literals with arithmetic comments. They are never derived
by running the implementation.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from pathable.engine.cost import compute_edge_cost
from pathable.engine.profiles import WHEELCHAIR, resolve_profile
from pathable.engine.search import a_star, haversine_heuristic, length_weight
from pathable.graph.model import EdgeFeatures
from pathable.models import Profile, Provenance, Risk
from tests.fixtures.diamond import TEST_PROFILE, build_diamond


def _profile(**updates: object) -> Profile:
    return Profile.model_validate({**TEST_PROFILE.model_dump(), **updates})


def _route(graph, profile: Profile, risk: Risk):
    def weight(u, v, key, features):
        breakdown = compute_edge_cost(features, profile, risk)
        return None if breakdown.hard_block else breakdown.total_m_eq

    return a_star(graph, "S", "T", weight, haversine_heuristic(graph, "T"))


def _route_cost(graph, path, profile: Profile, risk: Risk) -> float:
    return sum(
        compute_edge_cost(graph[e.u][e.v][e.key]["features"], profile, risk).total_m_eq
        for e in path.edges
    )


def test_shortest_is_length_only_and_uses_the_steps_route() -> None:
    graph = build_diamond()
    path = a_star(graph, "S", "T", length_weight, haversine_heuristic(graph, "T"))
    assert path is not None
    # 250 + 50 = 300 m
    assert path.length_m == pytest.approx(300.0)
    assert path.nodes == ("S", "A", "T")


def test_route_one_is_hard_blocked_by_steps() -> None:
    graph = build_diamond()
    profile = _profile()
    path = _route(graph, profile, Risk.BALANCED)
    assert path is not None
    assert path.nodes != ("S", "A", "T")

    steps_edge = graph["A"]["T"][0]["features"]
    breakdown = compute_edge_cost(steps_edge, profile, Risk.BALANCED)
    assert breakdown.hard_block is not None
    assert breakdown.hard_block.attribute == "steps"
    # Total is still computed for explanation purposes: 50 m + no other terms.
    assert breakdown.total_m_eq == pytest.approx(50.0)


@pytest.mark.parametrize("risk", list(Risk))
def test_preferred_is_route_two_at_every_risk(risk: Risk) -> None:
    graph = build_diamond()
    profile = _profile()
    path = _route(graph, profile, risk)
    assert path is not None
    assert path.nodes == ("S", "B", "B2", "T")
    # Route 2: 280 m flat + 100 m at 6%.
    # grade multiplier = 1 + 0.25 * (6 - 5) = 1.25
    # cost = 100 + 100 * 1.25 + 180 = 405 m-eq
    assert _route_cost(graph, path, profile, risk) == pytest.approx(405.0)


def test_route_two_hand_calculation() -> None:
    graph = build_diamond()
    profile = _profile()
    edge = graph["B"]["B2"][0]["features"]
    breakdown = compute_edge_cost(edge, profile, Risk.BALANCED)
    # 100 m at 6% = 100 * 1.25 = 125 m-eq
    assert breakdown.total_m_eq == pytest.approx(125.0)
    assert graph["S"]["B"][0]["features"].length_m == pytest.approx(100.0)


def test_route_three_hand_calculation_and_choice() -> None:
    graph = build_diamond()
    profile = _profile()
    thorough = graph["C"]["T"][0]["features"]
    breakdown = compute_edge_cost(thorough, profile, Risk.BALANCED)
    # 150 m * 3.0 rough multiplier = 450 m-eq
    assert breakdown.total_m_eq == pytest.approx(450.0)
    # Whole route: 190 + 450 = 640 m-eq
    path = a_star(
        graph,
        "S",
        "T",
        lambda u, v, k, f: (
            None
            if compute_edge_cost(f, profile, Risk.BALANCED).hard_block
            else compute_edge_cost(f, profile, Risk.BALANCED).total_m_eq
        ),
        haversine_heuristic(graph, "T"),
    )
    assert path is not None
    assert _route_cost(graph, path, profile, Risk.BALANCED) == pytest.approx(405.0)


@pytest.mark.parametrize(
    ("risk", "expected_cost"),
    [
        (Risk.DIRECT, 545.0),  # 520 + 75 * 1/3  = 545
        (Risk.BALANCED, 595.0),  # 520 + 75 * 1    = 595
        (Risk.CAUTIOUS, 720.0),  # 520 + 75 * 8/3  = 720
    ],
)
def test_route_four_unknown_kerb_by_risk(risk: Risk, expected_cost: float) -> None:
    graph = build_diamond()
    profile = _profile()
    crossing = graph["D"]["T"][0]["features"]
    breakdown = compute_edge_cost(crossing, profile, risk)
    assert breakdown.hard_block is None
    # Whole route: 400 + (120 + 25/75/200) = 545 / 595 / 720
    assert breakdown.total_m_eq == pytest.approx(120.0 + expected_cost - 520.0)
    assert 400.0 + breakdown.total_m_eq == pytest.approx(expected_cost)


def test_loosening_hard_grade_to_ten_keeps_route_two() -> None:
    graph = build_diamond()
    profile = _profile(hard_grade_up_pct=10.0)
    path = _route(graph, profile, Risk.BALANCED)
    assert path is not None
    assert path.nodes == ("S", "B", "B2", "T")


@pytest.mark.parametrize(
    ("risk", "expected_first_node"),
    [
        # Route 2's 6% edge is now blocked. Route 4: 545 direct, 595 balanced.
        (Risk.DIRECT, "D"),
        (Risk.BALANCED, "D"),
        # Cautious Route 4 = 720, Route 3 = 640, so Route 3 wins.
        (Risk.CAUTIOUS, "C"),
    ],
)
def test_tightening_hard_grade_to_5_5_switches_route(risk: Risk, expected_first_node: str) -> None:
    graph = build_diamond()
    profile = _profile(hard_grade_up_pct=5.5)
    path = _route(graph, profile, risk)
    assert path is not None
    assert path.nodes[1] == expected_first_node


def test_route_three_vs_four_threshold_is_120_m_eq() -> None:
    graph = build_diamond()
    # 640 - 520 = 120: at exactly 120 both routes cost 640 and the tie-break
    # is not part of this test. Use either side of the threshold.
    below = _profile(hard_grade_up_pct=5.5, kerb_unknown_penalty_m=119.0)
    above = _profile(hard_grade_up_pct=5.5, kerb_unknown_penalty_m=121.0)

    path_below = _route(graph, below, Risk.BALANCED)
    path_above = _route(graph, above, Risk.BALANCED)
    assert path_below is not None and path_above is not None
    # Route 4 = 520 + 119 = 639 < 640; Route 3 = 640.
    assert _route_cost(graph, path_below, below, Risk.BALANCED) == pytest.approx(639.0)
    assert path_below.nodes[1] == "D"
    # Route 4 = 520 + 121 = 641 > 640.
    assert _route_cost(graph, path_above, above, Risk.BALANCED) == pytest.approx(640.0)
    assert path_above.nodes[1] == "C"


def test_cost_is_never_below_length() -> None:
    graph = build_diamond()
    for profile in (TEST_PROFILE, WHEELCHAIR, resolve_profile("limited_mobility")):
        for risk in Risk:
            for _, _, _, data in graph.edges(keys=True, data=True):
                breakdown = compute_edge_cost(data["features"], profile, risk)
                assert breakdown.total_m_eq >= data["features"].length_m - 1e-9


def test_terms_are_additive_and_explain_the_total() -> None:
    graph = build_diamond()
    breakdown = compute_edge_cost(graph["B"]["B2"][0]["features"], TEST_PROFILE, Risk.BALANCED)
    assert breakdown.base_m_eq + sum(term.m_eq for term in breakdown.terms) == pytest.approx(
        breakdown.total_m_eq
    )
    assert all(term.m_eq >= 0 for term in breakdown.terms)


def test_unknown_data_is_priced_by_risk() -> None:
    profile = WHEELCHAIR
    edge = EdgeFeatures(
        length_m=100.0,
        highway="footway",
        surface=None,
        surface_prov=Provenance.UNKNOWN,
        smoothness=None,
        smoothness_prov=Provenance.UNKNOWN,
        roughness_class=None,
        roughness_prov=Provenance.UNKNOWN,
        width_m=None,
        width_prov=Provenance.UNKNOWN,
        grade_pct=None,
        grade_prov=Provenance.UNKNOWN,
        steps_known=True,
        steps_prov=Provenance.OSM_MAPPED,
        access_ok=True,
        access_prov=Provenance.OSM_MAPPED,
    )
    direct = compute_edge_cost(edge, profile, Risk.DIRECT).total_m_eq
    balanced = compute_edge_cost(edge, profile, Risk.BALANCED).total_m_eq
    cautious = compute_edge_cost(edge, profile, Risk.CAUTIOUS).total_m_eq
    assert direct < balanced < cautious
    assert direct >= 100.0


def test_stricter_risk_never_lowers_an_edge_cost() -> None:
    graph = build_diamond()
    for _, _, _, data in graph.edges(keys=True, data=True):
        direct = compute_edge_cost(data["features"], WHEELCHAIR, Risk.DIRECT).total_m_eq
        balanced = compute_edge_cost(data["features"], WHEELCHAIR, Risk.BALANCED).total_m_eq
        cautious = compute_edge_cost(data["features"], WHEELCHAIR, Risk.CAUTIOUS).total_m_eq
        assert direct <= balanced <= cautious


def test_steps_can_be_penalized_instead_of_blocked() -> None:
    graph = build_diamond()
    profile = _profile(steps="penalize", steps_penalty_m=500.0)
    breakdown = compute_edge_cost(graph["A"]["T"][0]["features"], profile, Risk.BALANCED)
    # 50 m base + 500 m-eq penalty
    assert breakdown.hard_block is None
    assert breakdown.total_m_eq == pytest.approx(550.0)


def test_profile_validation_rejects_bad_parameters() -> None:
    with pytest.raises(ValidationError):
        Profile(soft_grade_up_pct=9.0, hard_grade_up_pct=8.0)
    with pytest.raises(ValidationError):
        Profile(surface_multipliers={"smooth": 0.5})
    with pytest.raises(ValidationError):
        Profile(kerb_unknown_penalty_m=-1)
    with pytest.raises(ValidationError):
        Profile(steps="sometimes")
