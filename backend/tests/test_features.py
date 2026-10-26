from __future__ import annotations

import networkx as nx

from pathable.graph.features import (
    apply_audit,
    apply_elevation,
    parse_incline,
    parse_width_m,
)
from pathable.graph.loader import normalize_graph
from pathable.graph.model import GraphMeta
from pathable.models import Provenance


def _meta() -> GraphMeta:
    return GraphMeta(
        area_id="raw-test",
        area_name="Raw normalization test",
        center_lat=40.0,
        center_lon=-75.0,
        radius_m=1000,
        source="test",
        fetched_at="2026-01-01",
    )


def _raw() -> nx.MultiDiGraph:
    graph = nx.MultiDiGraph()
    graph.add_node("u", x=-75.0, y=40.0)
    graph.add_node("v", x=-74.999, y=40.0)
    return graph


def _normalize_one(**attrs) -> object:
    raw = _raw()
    base = {"highway": "footway", "length": 100.0}
    base.update(attrs)
    raw.add_edge("u", "v", key=0, **base)
    normalized = normalize_graph(raw, _meta())
    return normalized["u"]["v"][0]["features"]


def test_directional_incline_flips_on_reversed_edges() -> None:
    raw = _raw()
    raw.add_edge("u", "v", key=0, highway="footway", length=100.0, incline="10%", reversed=False)
    raw.add_edge("v", "u", key=0, highway="footway", length=100.0, incline="10%", reversed=True)
    graph = normalize_graph(raw, _meta())
    forward = graph["u"]["v"][0]["features"]
    backward = graph["v"]["u"][0]["features"]
    assert forward.grade_pct == 10.0
    assert forward.grade_prov is Provenance.OSM_MAPPED
    assert backward.grade_pct == -10.0
    assert backward.grade_prov is Provenance.OSM_MAPPED


def test_incline_down_and_up_tags() -> None:
    down = _normalize_one(incline="down")
    assert down.grade_pct is None  # direction known, steepness not mapped
    assert down.incline_sign == -1
    assert down.grade_prov is Provenance.UNKNOWN

    numeric_down = _normalize_one(incline="-8%")
    assert numeric_down.grade_pct == -8.0


def test_ambiguous_reversed_list_makes_direction_unknown() -> None:
    edge = _normalize_one(incline="10%", reversed=[False, True])
    assert edge.grade_pct is None
    assert edge.grade_prov is Provenance.UNKNOWN
    assert any("ambiguous reversed" in note for note in edge.notes)


def test_list_tags_use_conservative_normalization() -> None:
    edge = _normalize_one(
        highway=["footway", "steps"],
        surface=["asphalt", "cobblestone"],
        width=["2", "1.2"],
    )
    # Steps anywhere in a merged edge is treated as steps.
    assert edge.is_steps is True
    # Worst roughness class wins.
    assert edge.roughness_class == "rough"
    # Narrowest width wins.
    assert edge.width_m == 1.2


def test_absent_tags_are_unknown_not_safe() -> None:
    edge = _normalize_one(highway=None)
    assert edge.surface_prov is Provenance.UNKNOWN
    assert edge.smoothness_prov is Provenance.UNKNOWN
    assert edge.width_prov is Provenance.UNKNOWN
    assert edge.grade_prov is Provenance.UNKNOWN
    assert edge.steps_prov is Provenance.UNKNOWN
    assert edge.wheelchair_prov is Provenance.UNKNOWN
    assert edge.access_ok is True  # network inclusion is evidence, see docs


def test_width_parsing() -> None:
    assert parse_width_m("1.5")[0] == 1.5
    assert parse_width_m("120 cm")[0] == 1.2
    assert parse_width_m("36 in")[0] == 0.9144
    assert parse_width_m("4'")[0] == 1.2192
    assert parse_width_m("4'6\"")[0] == 1.3716
    assert parse_width_m("narrow")[0] is None


def test_incline_parsing_units() -> None:
    grade, sign, magnitude, _ = parse_incline("8%", False)
    assert grade == 8.0 and sign == 1 and magnitude == 8.0
    grade, _, _, _ = parse_incline("8%", True)
    assert grade == -8.0
    grade, _, _, _ = parse_incline("up", False)
    assert grade is None


def test_dem_grade_rejects_short_and_implausible_edges() -> None:
    short = _normalize_one()
    apply_elevation(short, 10.0, 13.0)  # 3 m over 100 m -> 3%, but edge is long here
    assert short.grade_pct == 3.0
    assert short.grade_prov is Provenance.DEM_ESTIMATED

    tiny = _normalize_one(length=5.0)
    apply_elevation(tiny, 10.0, 13.0)
    assert tiny.grade_pct is None
    assert tiny.grade_prov is Provenance.UNKNOWN

    implausible = _normalize_one(length=100.0)
    apply_elevation(implausible, 0.0, 50.0)  # 50% is rejected at 30 m resolution
    assert implausible.grade_pct is None
    assert implausible.grade_prov is Provenance.UNKNOWN


def test_field_audit_overrides_and_preserves_osm_values() -> None:
    edge = _normalize_one(width="2", incline="2%")
    original_grade = edge.grade_pct
    original_width = edge.width_m
    apply_audit(
        edge,
        {
            "curb_ramp": "damaged",
            "measured_slope_pct": 9.5,
            "clear_width_m": 0.8,
            "obstacle": "planter",
        },
    )
    assert edge.kerb == "damaged"
    assert edge.kerb_prov is Provenance.FIELD_AUDIT
    assert edge.grade_pct == 9.5
    assert edge.grade_prov is Provenance.FIELD_AUDIT
    assert edge.width_m == 0.8
    assert edge.width_prov is Provenance.FIELD_AUDIT
    assert edge.barrier == "planter"
    assert edge.osm_grade_pct == original_grade
    assert edge.osm_width_m == original_width


def test_node_kerb_and_barrier_attach_to_arrival_edge() -> None:
    raw = _raw()
    raw.nodes["v"]["kerb"] = "raised"
    raw.nodes["v"]["tactile_paving"] = "yes"
    raw.nodes["v"]["barrier"] = "bollard"
    raw.add_edge("u", "v", key=0, highway="footway", length=100.0, crossing="marked")
    edge = normalize_graph(raw, _meta())["u"]["v"][0]["features"]
    assert edge.is_crossing is True
    assert edge.kerb == "raised"
    assert edge.kerb_prov is Provenance.OSM_MAPPED
    assert edge.tactile_paving == "yes"
    assert edge.barrier == "bollard"


def test_access_restriction_is_known() -> None:
    edge = _normalize_one(foot="private")
    assert edge.access_ok is False
    assert edge.access_prov is Provenance.OSM_MAPPED
    assert "private" in edge.access_reason


def test_barrier_kerb_node_is_not_an_obstruction() -> None:
    raw = _raw()
    raw.nodes["v"]["barrier"] = "kerb"
    raw.add_edge("u", "v", key=0, highway="footway", length=100.0)
    edge = normalize_graph(raw, _meta())["u"]["v"][0]["features"]
    assert edge.barrier is None
