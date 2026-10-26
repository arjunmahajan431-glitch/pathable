from __future__ import annotations

import pytest
from pydantic import ValidationError

from pathable.config import AreaConfig, Center, load_config
from pathable.graph.features import MAX_ABS_DEM_GRADE_PCT
from pathable.graph.loader import load_area_graph
from pathable.models import Provenance


def test_active_area_is_explicit() -> None:
    config = load_config()
    # The shipped city area is a real public area, not a placeholder. A
    # placeholder is still valid configuration, but it must be labeled so the
    # interface and health endpoint can warn about it.
    assert config.area.is_placeholder is False
    assert "PLACEHOLDER" not in config.area.name.upper()
    assert config.area.radius_m <= config.max_radius_m


def test_area_radius_cap() -> None:
    # The original neighborhood cap was 3 km. Whole-city mapping raises it to
    # 12 km, but an unbounded area is still rejected.
    with pytest.raises(ValidationError):
        AreaConfig(
            id="too-big",
            name="Too big",
            center=Center(lat=40.0, lon=-75.0),
            radius_m=12_001,
        )


def test_committed_sample_graph_loads_without_network() -> None:
    config = load_config()
    bundle = load_area_graph(config, demo_mode=True)
    assert bundle.meta.demo_mode is True
    assert bundle.graph.number_of_nodes() > 500
    assert bundle.graph.number_of_edges() > 1000
    assert all("features" in data for _, data in bundle.graph.nodes(data=True))

    grades = []
    unknown_grades = 0
    for _, _, _, data in bundle.graph.edges(keys=True, data=True):
        features = data["features"]
        if features.grade_prov is Provenance.DEM_ESTIMATED:
            grades.append(features.grade_pct)
        elif features.grade_prov is Provenance.UNKNOWN:
            unknown_grades += 1
    assert len(grades) > 1000
    assert unknown_grades > 0
    assert max(abs(g) for g in grades) <= MAX_ABS_DEM_GRADE_PCT
    assert bundle.meta.elevation_source


def test_sample_graph_keeps_accessibility_tags() -> None:
    config = load_config()
    graph = load_area_graph(config, demo_mode=True).graph
    surfaces = {
        data["features"].surface
        for _, _, _, data in graph.edges(keys=True, data=True)
        if data["features"].surface
    }
    assert surfaces
    assert any(data["features"].is_crossing for _, _, _, data in graph.edges(keys=True, data=True))
    assert any(data["features"].is_steps for _, _, _, data in graph.edges(keys=True, data=True))
