"""HTTP endpoints. Routing logic lives in pathable.engine.pipeline."""

from __future__ import annotations

import hmac
import os
from typing import Any

from fastapi import APIRouter, Query, Request, Response

from pathable.api.errors import ApiError
from pathable.api.state import AppState, get_state
from pathable.engine.pipeline import plan_route
from pathable.engine.profiles import PROFILE_REGISTRY, parameter_specs
from pathable.geocode import ATTRIBUTION, GeocodeError
from pathable.graph.area import area_contains
from pathable.graph.loader import graph_counts, haversine_m
from pathable.models import Risk
from pathable.reports.status import is_active
from pathable.schemas import (
    AreasResponse,
    GeocodeResponse,
    HealthResponse,
    ProfilesResponse,
    ReportCreate,
    ReportCreateResponse,
    ReportGetResponse,
    ReportOut,
    ReportPatch,
    ReportPatchResponse,
    RouteRequest,
    RouteResponse,
    Warning,
)

router = APIRouter(prefix="/api")


def _require_graph(state: AppState) -> None:
    if state.graph is None or state.meta is None:
        raise ApiError(
            503,
            "graph_unavailable",
            "The pedestrian network is not loaded. Run `make data` and restart the API, "
            "or start with `PATHABLE_DEMO=1` to use the labeled sample extract.",
            details={"graph_error": state.graph_error or "not loaded"},
        )


def _report_out(report: dict[str, Any], expiry_days: int) -> ReportOut:
    return ReportOut(
        id=int(report["id"]),
        lat=float(report["lat"]),
        lon=float(report["lon"]),
        category=str(report["category"]),
        description=str(report.get("description") or ""),
        created_at=str(report["created_at"]),
        status=str(report["status"]),  # type: ignore[arg-type]
        reviewed_at=report.get("reviewed_at"),
        last_confirmed_at=report.get("last_confirmed_at"),
        influence=is_active(report, expiry_days),
    )


def _parse_bbox(bbox: str, max_span: float) -> tuple[float, float, float, float]:
    parts = bbox.split(",")
    if len(parts) != 4:
        raise ApiError(
            422, "invalid_bbox", "bbox must be minLon,minLat,maxLon,maxLat (four numbers)."
        )
    try:
        min_lon, min_lat, max_lon, max_lat = (float(p) for p in parts)
    except ValueError as exc:
        raise ApiError(422, "invalid_bbox", "bbox must contain four decimal numbers.") from exc
    if not (-180 <= min_lon <= max_lon <= 180 and -90 <= min_lat <= max_lat <= 90):
        raise ApiError(422, "invalid_bbox", "bbox coordinates are out of range or reversed.")
    if (max_lon - min_lon) > max_span or (max_lat - min_lat) > max_span:
        raise ApiError(
            422,
            "bbox_too_large",
            f"bbox spans more than {max_span} degrees on a side; zoom in or narrow the box.",
        )
    return min_lon, min_lat, max_lon, max_lat


def _client_id(request: Request) -> str:
    # Do not trust X-Forwarded-For without an explicit proxy configuration.
    return request.client.host if request.client else "unknown"


def _admin_token() -> str:
    return os.environ.get("PATHABLE_ADMIN_TOKEN", "").strip()


def _provided_token(request: Request) -> str:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return request.headers.get("x-admin-token", "").strip()


def _health_payload(state: AppState) -> HealthResponse:
    meta = state.meta
    warnings: list[Warning] = []
    if state.graph is None:
        warnings.append(
            Warning(
                code="graph_unavailable",
                message="The pedestrian graph is not loaded; route requests will fail.",
                severity="error",
            )
        )
    node_count = edge_count = 0
    if state.graph is not None:
        node_count, edge_count = graph_counts(state.graph)
    return HealthResponse(
        status="ok" if state.graph is not None else "degraded",
        graph_loaded=state.graph is not None,
        area=state.area_out(),
        areas=state.areas_out(),
        data_date=meta.fetched_at if meta else None,
        source=meta.source if meta else None,
        demo_mode=meta.demo_mode if meta else state.config.demo_forced,
        nodes=node_count,
        edges=edge_count,
        reports_database=str(state.store.path),
        profiles=sorted(PROFILE_REGISTRY),
        field_audits=state.field_audits,
        admin_token_configured=bool(_admin_token()),
        graph_error=state.graph_error,
        warnings=warnings,
    )


@router.get("/health", response_model=HealthResponse)
def health(request: Request) -> HealthResponse:
    return _health_payload(get_state(request))


@router.get("/areas", response_model=AreasResponse)
def list_areas(request: Request) -> AreasResponse:
    state = get_state(request)
    return AreasResponse(areas=state.areas_out(), active=state.area_out())


@router.post("/areas/{area_id}/activate", response_model=HealthResponse)
def activate_area(request: Request, area_id: str) -> HealthResponse:
    state = get_state(request)
    if state.area_by_id(area_id) is None:
        raise ApiError(
            404,
            "area_not_found",
            f"Unknown mapping area: {area_id}",
            details={"area_id": area_id},
        )
    try:
        state.switch_area(area_id)
    except Exception as exc:
        # Do not leave the client believing the switch succeeded. The previous
        # area stays active, and the next health call reports the real state.
        raise ApiError(
            503,
            "area_unavailable",
            f"Could not load {area_id}. {type(exc).__name__}: {exc}",
            details={"area_id": area_id},
        ) from exc
    return _health_payload(state)


@router.get("/profiles", response_model=ProfilesResponse)
def profiles() -> ProfilesResponse:
    return ProfilesResponse(
        profiles=list(PROFILE_REGISTRY.values()),
        parameter_specs=parameter_specs(),
        risks=[Risk.DIRECT, Risk.BALANCED, Risk.CAUTIOUS],
        risk_note=(
            "Risk scales the price of unknown data only: direct = 1/3, balanced = 1, "
            "cautious = 8/3. It never turns unknown into safe or into a barrier."
        ),
        disclaimer=(
            "Default thresholds are starting points from design guidance and explicit "
            "assumptions. They are not medical advice or a legal accessibility "
            "determination. Adjust them for your own needs."
        ),
    )


@router.post("/route", response_model=RouteResponse)
def create_route(request: Request, body: RouteRequest) -> RouteResponse:
    state = get_state(request)
    _require_graph(state)
    assert state.graph is not None and state.meta is not None
    return plan_route(
        state.config,
        state.graph,
        state.meta,
        body,
        area=state.area,
        reports=state.store.routing_reports(),
        load_warnings=state.route_load_warnings(),
    )


@router.get("/reports", response_model=ReportGetResponse)
def list_reports(
    request: Request,
    bbox: str = Query(..., description="minLon,minLat,maxLon,maxLat"),
) -> ReportGetResponse:
    state = get_state(request)
    min_lon, min_lat, max_lon, max_lat = _parse_bbox(bbox, state.config.reports.max_bbox_span_deg)
    rows = state.store.list_reports(
        min_lat=min_lat, min_lon=min_lon, max_lat=max_lat, max_lon=max_lon
    )
    return ReportGetResponse(
        bbox=bbox,
        count=len(rows),
        reports=[_report_out(row, state.config.reports.expiry_days) for row in rows],
    )


@router.post("/reports", response_model=ReportCreateResponse, status_code=201)
def create_report(request: Request, body: ReportCreate, response: Response) -> ReportCreateResponse:
    state = get_state(request)
    if body.website.strip():
        # Honeypot. Pretend success, store nothing, do not reveal the trap.
        response.status_code = 202
        return ReportCreateResponse(
            id=0,
            status="unverified",
            message="Thank you. Your report was received for review.",
        )
    if len(body.description) > state.config.reports.max_description_chars:
        raise ApiError(
            422,
            "description_too_long",
            (
                "Description must be "
                f"{state.config.reports.max_description_chars} characters or fewer."
            ),
        )
    if not area_contains(state.area, body.lat, body.lon):
        distance = haversine_m(state.area.center.lat, state.area.center.lon, body.lat, body.lon)
        raise ApiError(
            422,
            "report_out_of_area",
            (f"Reports must be inside {state.area.name}. Choose a point within the selected city."),
            details={
                "distance_m": round(distance, 1),
                "radius_m": state.area.radius_m,
                "area_name": state.area.name,
            },
        )
    client_hash = state.store.client_hash(_client_id(request))
    recent = state.store.recent_report_count(client_hash, hours=1)
    if recent >= state.config.reports.rate_limit_per_hour:
        raise ApiError(
            429,
            "rate_limited",
            "Too many reports from this client in the last hour. Please try again later.",
            headers={"Retry-After": "3600"},
        )
    report = state.store.create_report(
        lat=body.lat,
        lon=body.lon,
        category=body.category,
        description=body.description,
        client_hash=client_hash,
    )
    return ReportCreateResponse(
        id=int(report["id"]),
        status="unverified",
        message=(
            "Thank you. This report is unverified until a reviewer checks it; it affects "
            "routing with half weight while unverified."
        ),
    )


@router.patch("/reports/{report_id}", response_model=ReportPatchResponse)
def review_report(request: Request, report_id: int, body: ReportPatch) -> ReportPatchResponse:
    state = get_state(request)
    expected = _admin_token()
    if not expected:
        raise ApiError(
            503,
            "admin_not_configured",
            "Admin review is disabled because PATHABLE_ADMIN_TOKEN is not set.",
        )
    provided = _provided_token(request)
    if not provided or not hmac.compare_digest(provided, expected):
        raise ApiError(403, "admin_required", "A valid admin token is required for this action.")
    updated = state.store.update_status(report_id, body.status, reconfirm=body.reconfirm)
    if updated is None:
        raise ApiError(404, "report_not_found", "That report does not exist.")
    return ReportPatchResponse(
        report=_report_out(updated, state.config.reports.expiry_days),
        message="Report status updated.",
    )


@router.get("/geocode", response_model=GeocodeResponse)
def geocode(
    request: Request,
    q: str = Query(..., min_length=2, max_length=120, description="Street address or place"),
) -> GeocodeResponse:
    state = get_state(request)
    try:
        results, cached = state.geocoder.search(
            q,
            center_lat=state.area.center.lat,
            center_lon=state.area.center.lon,
            radius_m=state.area.radius_m,
        )
    except GeocodeError as exc:
        raise ApiError(502, "geocode_unavailable", str(exc)) from exc
    return GeocodeResponse(results=results, attribution=ATTRIBUTION, cached=cached)
