from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from pathable.api.main import create_app
from pathable.config import AreaConfig, Center, load_config
from pathable.graph.loader import GraphBundle
from pathable.reports.store import ReportStore
from tests.fixtures.diamond import COORDS, TEST_PROFILE, build_diamond


@pytest.fixture
def test_config(tmp_path: Path):
    cfg = load_config()
    area = AreaConfig(
        id="synthetic-diamond",
        name="Synthetic diamond (test)",
        center=Center(lat=40.001, lon=-75.0),
        radius_m=1000,
        is_placeholder=False,
    )
    reports = cfg.reports.model_copy(
        update={
            "database": str(tmp_path / "reports.db"),
            "rate_limit_per_hour": 3,
            "max_bbox_span_deg": 0.05,
        }
    )
    return cfg.model_copy(update={"areas": [area], "active_area": area.id, "reports": reports})


@pytest.fixture
def diamond_bundle() -> GraphBundle:
    graph = build_diamond()
    return GraphBundle(graph=graph, meta=graph.graph["meta"], warnings=[])


@pytest.fixture
def client(test_config, diamond_bundle, tmp_path: Path):
    store = ReportStore(tmp_path / "reports.db")
    app = create_app(test_config, graph_bundle=diamond_bundle, store=store)
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def profile_payload() -> dict:
    return TEST_PROFILE.model_dump(mode="json")


@pytest.fixture
def route_body(profile_payload: dict) -> dict:
    return {
        "start": {"lat": COORDS["S"][0], "lon": COORDS["S"][1]},
        "end": {"lat": COORDS["T"][0], "lon": COORDS["T"][1]},
        "profile": profile_payload,
        "risk": "balanced",
    }
