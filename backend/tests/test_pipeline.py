from __future__ import annotations

import pytest

from pathable.config import AreaConfig, Center
from pathable.engine.pipeline import OutOfAreaError, plan_route
from pathable.graph.loader import GraphBundle
from pathable.models import Risk
from pathable.schemas import RouteRequest
from tests.fixtures.diamond import (
    COORDS,
    TEST_PROFILE,
    build_diamond,
    build_disconnected,
    build_steps_only,
)


def _request(start=COORDS["S"], end=COORDS["T"], **profile_updates) -> RouteRequest:
    profile = TEST_PROFILE.model_dump()
    profile.update(profile_updates)
    return RouteRequest(
        start={"lat": start[0], "lon": start[1]},
        end={"lat": end[0], "lon": end[1]},
        profile=profile,
        risk=Risk.BALANCED,
    )


def _bundle(graph):
    return GraphBundle(graph=graph, meta=graph.graph["meta"], warnings=[])


def test_plan_uses_the_selected_area_not_the_config_default(test_config) -> None:
    graph = build_diamond()
    selected = AreaConfig(
        id="selected-city",
        name="Selected city (test)",
        center=Center(lat=COORDS["S"][0], lon=COORDS["S"][1]),
        radius_m=1000,
    )
    response = plan_route(
        test_config,
        graph,
        graph.graph["meta"],
        _request(),
        area=selected,
    )
    assert response.area.id == "selected-city"
    assert response.area.name == "Selected city (test)"


def test_plan_rejects_points_outside_the_selected_area(test_config) -> None:
    graph = build_diamond()
    elsewhere = AreaConfig(
        id="somewhere-else",
        name="Somewhere else (test)",
        center=Center(lat=41.0, lon=-74.0),
        radius_m=500,
    )
    with pytest.raises(OutOfAreaError):
        plan_route(
            test_config,
            graph,
            graph.graph["meta"],
            _request(),
            area=elsewhere,
        )


def test_plan_returns_both_routes_and_explanation(test_config) -> None:
    graph = build_diamond()
    response = plan_route(test_config, graph, graph.graph["meta"], _request())
    assert response.shortest is not None
    assert response.preferred is not None
    assert response.shortest.distance_m == pytest.approx(300.0)
    assert response.preferred.distance_m == pytest.approx(380.0)
    assert response.preferred.cost_m_eq == pytest.approx(405.0)
    assert response.no_feasible_route is None
    assert response.explanation is not None
    assert "+80 m" in response.explanation.summary
    assert "+27%" in response.explanation.summary
    assert any("BLOCKED" in line for line in response.explanation.why_not_shortest)
    assert response.preferred.coverage.overall == pytest.approx(1.0)
    assert response.preferred.estimated_minutes > 0


def test_explanations_are_deterministic(test_config) -> None:
    graph = build_diamond()
    first = plan_route(test_config, graph, graph.graph["meta"], _request())
    second = plan_route(test_config, graph, graph.graph["meta"], _request())
    assert first.model_dump() == second.model_dump()


def test_no_feasible_route_with_steps_only(test_config) -> None:
    graph = build_steps_only()
    response = plan_route(
        test_config, graph, graph.graph["meta"], _request((40.0, -75.0), (40.0, -74.999))
    )
    assert response.shortest is not None
    assert response.shortest.distance_m == pytest.approx(50.0)
    assert response.preferred is None
    assert response.no_feasible_route is not None
    assert response.no_feasible_route.code == "hard_constraints"
    assert "steps" in response.no_feasible_route.message
    # A clearly labeled relaxed alternative is allowed, with its constraint listed.
    assert response.relaxed_alternative is not None
    assert response.relaxed_alternative.is_relaxed is True
    assert "steps" in response.relaxed_alternative.relaxed_constraints


def test_disconnected_route(test_config) -> None:
    graph = build_disconnected()
    response = plan_route(
        test_config, graph, graph.graph["meta"], _request((40.0, -75.0), (40.0, -74.999))
    )
    assert response.shortest is None
    assert response.preferred is None
    assert response.no_feasible_route is not None
    assert response.no_feasible_route.code == "disconnected"


def test_start_equals_goal(test_config) -> None:
    graph = build_diamond()
    response = plan_route(
        test_config, graph, graph.graph["meta"], _request(COORDS["S"], COORDS["S"])
    )
    assert response.shortest is not None and response.preferred is not None
    assert response.shortest.distance_m == 0.0
    assert response.preferred.distance_m == 0.0
    assert response.preferred.segments == []
    assert response.snap.start_distance_m == pytest.approx(0.0, abs=0.2)


def test_sensitivity_changes_route_when_grade_limit_moves(test_config) -> None:
    graph = build_diamond()
    response = plan_route(
        test_config,
        graph,
        graph.graph["meta"],
        _request(hard_grade_up_pct=5.5),
    )
    assert response.preferred is not None
    assert response.preferred.segments[0].id.startswith("S:D")
    assert response.sensitivity
    values = {variant.value: variant for variant in response.sensitivity[0].variants}
    # Loosening to 6.5 makes Route 2 feasible again, so the route must change.
    assert any(variant.differs_from_baseline for variant in response.sensitivity[0].variants)
    assert values[6.5].route_available is True


def test_relaxed_route_does_not_relax_legal_access(test_config) -> None:
    graph = build_diamond()
    graph["S"]["A"][0]["features"].access_ok = False
    graph["S"]["A"][0]["features"].access_reason = "foot=private"
    graph["S"]["A"][0]["features"].is_steps = True
    response = plan_route(
        test_config,
        graph,
        graph.graph["meta"],
        _request(hard_grade_up_pct=5.5),
    )
    # Access restrictions never become legal alternatives.
    if response.relaxed_alternative is not None:
        assert "access" not in response.relaxed_alternative.relaxed_constraints
