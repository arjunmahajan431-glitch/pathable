from __future__ import annotations

import pytest

from pathable.geocode import GeocodeError
from pathable.schemas import GeocodeResult


def test_health_and_profiles(client) -> None:
    health = client.get("/api/health")
    assert health.status_code == 200
    body = health.json()
    assert body["status"] == "ok"
    assert body["graph_loaded"] is True
    assert body["nodes"] == 7
    assert body["demo_mode"] is True
    assert "wheelchair" in body["profiles"]

    profiles = client.get("/api/profiles")
    assert profiles.status_code == 200
    payload = profiles.json()
    assert {p["name"] for p in payload["profiles"]} == {"wheelchair", "limited_mobility"}
    assert any(spec["key"] == "soft_grade_up_pct" for spec in payload["parameter_specs"])
    assert "not medical advice" in payload["disclaimer"].lower()


def test_route_contract(client, route_body) -> None:
    response = client.post("/api/route", json=route_body)
    assert response.status_code == 200
    payload = response.json()
    assert payload["shortest"]["distance_m"] == pytest.approx(300.0)
    assert payload["preferred"]["distance_m"] == pytest.approx(380.0)
    assert payload["preferred"]["cost_m_eq"] == pytest.approx(405.0)
    assert payload["shortest"]["geometry"]["type"] == "LineString"
    assert len(payload["preferred"]["segments"]) == 3
    assert payload["shortest"]["barriers"][0]["attribute"] == "steps"
    assert payload["explanation"]["why_not_shortest"]
    assert payload["sensitivity"]
    assert response.headers["cache-control"] == "no-store"
    assert "not how good the route" in payload["request_note"]


def test_route_invalid_profile(client, route_body) -> None:
    route_body["profile"] = "not-a-profile"
    response = client.post("/api/route", json=route_body)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_profile"


def test_route_out_of_area(client, route_body) -> None:
    route_body["start"] = {"lat": 41.0, "lon": -75.0}
    response = client.post("/api/route", json=route_body)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "out_of_area"


def test_route_invalid_coordinates(client, route_body) -> None:
    route_body["start"] = {"lat": 91.0, "lon": -75.0}
    response = client.post("/api/route", json=route_body)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_request"


def test_route_snap_too_far(client, route_body) -> None:
    # Inside the 1 km pilot circle but far from the synthetic network.
    route_body["start"] = {"lat": 40.0080, "lon": -75.0}
    response = client.post("/api/route", json=route_body)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "snap_too_far"


def test_route_rejects_oversized_body(client) -> None:
    response = client.post(
        "/api/route",
        content=b"x" * 200_000,
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 413


def test_report_create_list_and_validation(client) -> None:
    created = client.post(
        "/api/reports",
        json={
            "lat": 40.0005,
            "lon": -75.0005,
            "category": "construction",
            "description": "Sidewalk closed; use the other side.",
        },
    )
    assert created.status_code == 201
    body = created.json()
    assert body["status"] == "unverified"
    assert body["id"] > 0

    listed = client.get("/api/reports?bbox=-75.01,39.99,-74.99,40.01")
    assert listed.status_code == 200
    payload = listed.json()
    assert payload["count"] == 1
    report = payload["reports"][0]
    assert report["status"] == "unverified"
    assert report["influence"] is True
    assert "client_hash" not in report

    too_long = client.post(
        "/api/reports",
        json={
            "lat": 40.0005,
            "lon": -75.0005,
            "category": "other",
            "description": "x" * 501,
        },
    )
    assert too_long.status_code == 422

    bad_category = client.post(
        "/api/reports",
        json={"lat": 40.0, "lon": -75.0, "category": "aliens", "description": ""},
    )
    assert bad_category.status_code == 422

    outside = client.post(
        "/api/reports",
        json={"lat": 40.5, "lon": -75.0, "category": "other", "description": ""},
    )
    assert outside.status_code == 422
    assert outside.json()["error"]["code"] == "report_out_of_area"


def test_report_honeypot_does_not_store(client) -> None:
    response = client.post(
        "/api/reports",
        json={
            "lat": 40.0005,
            "lon": -75.0005,
            "category": "other",
            "description": "spam",
            "website": "https://spam.example",
        },
    )
    assert response.status_code == 202
    listed = client.get("/api/reports?bbox=-75.01,39.99,-74.99,40.01").json()
    assert listed["count"] == 0


def test_report_rate_limit(client) -> None:
    payload = {
        "lat": 40.0005 + 0.00001,
        "lon": -75.0005,
        "category": "other",
        "description": "rate limit",
    }
    for _ in range(3):
        assert client.post("/api/reports", json=payload).status_code == 201
    blocked = client.post("/api/reports", json=payload)
    assert blocked.status_code == 429
    assert blocked.headers.get("retry-after") == "3600"


def test_report_bbox_validation(client) -> None:
    assert client.get("/api/reports?bbox=garbage").status_code == 422
    assert client.get("/api/reports?bbox=-75.1,39.9,-74.9,40.1").status_code == 422
    assert client.get("/api/reports?bbox=-75.01,39.99,-74.99,40.01").status_code == 200


def test_admin_token_enforcement(client, monkeypatch) -> None:
    created = client.post(
        "/api/reports",
        json={"lat": 40.0005, "lon": -75.0005, "category": "other", "description": "x"},
    )
    report_id = created.json()["id"]

    # No token configured -> 503.
    monkeypatch.delenv("PATHABLE_ADMIN_TOKEN", raising=False)
    unavailable = client.patch(f"/api/reports/{report_id}", json={"status": "reviewed"})
    assert unavailable.status_code == 503

    monkeypatch.setenv("PATHABLE_ADMIN_TOKEN", "test-admin-token")
    forbidden = client.patch(f"/api/reports/{report_id}", json={"status": "reviewed"})
    assert forbidden.status_code == 403

    wrong = client.patch(
        f"/api/reports/{report_id}",
        json={"status": "reviewed"},
        headers={"Authorization": "Bearer wrong-token"},
    )
    assert wrong.status_code == 403

    ok = client.patch(
        f"/api/reports/{report_id}",
        json={"status": "reviewed", "reconfirm": True},
        headers={"Authorization": "Bearer test-admin-token"},
    )
    assert ok.status_code == 200
    body = ok.json()
    assert body["report"]["status"] == "reviewed"
    assert body["report"]["influence"] is True

    missing = client.patch(
        "/api/reports/99999",
        json={"status": "reviewed"},
        headers={"X-Admin-Token": "test-admin-token"},
    )
    assert missing.status_code == 404


def test_geocode_proxy_success_and_failure(client, monkeypatch) -> None:
    state = client.app.state.pathable
    calls = {}

    def fake_search(query, *, center_lat, center_lon, radius_m):
        calls["query"] = query
        return [GeocodeResult(display_name="Civic Center Plaza", lat=37.7793, lon=-122.4193)], True

    monkeypatch.setattr(state.geocoder, "search", fake_search)
    response = client.get("/api/geocode", params={"q": "Civic Center"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["results"][0]["display_name"] == "Civic Center Plaza"
    assert payload["cached"] is True
    assert "OpenStreetMap" in payload["attribution"]
    assert calls["query"] == "Civic Center"

    def unavailable(*args, **kwargs):
        raise GeocodeError("service down")

    monkeypatch.setattr(state.geocoder, "search", unavailable)
    failure = client.get("/api/geocode", params={"q": "Civic Center"})
    assert failure.status_code == 502
    assert failure.json()["error"]["code"] == "geocode_unavailable"


def test_openapi_docs_available(client) -> None:
    assert client.get("/api/openapi.json").status_code == 200
    assert client.get("/api/docs").status_code == 200
