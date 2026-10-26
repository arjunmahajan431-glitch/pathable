"""Pydantic request/response models for the HTTP API.

Kept outside ``api/`` so the routing engine can build its result objects
without importing FastAPI.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from pathable.models import (
    REPORT_CATEGORIES,
    CostBreakdown,
    Point,
    Profile,
    Provenance,
    Risk,
)

Severity = Literal["info", "warning", "error"]
ReportStatus = Literal["unverified", "reviewed", "resolved", "rejected"]


class Warning(BaseModel):
    code: str
    message: str
    severity: Severity = "warning"


class AreaOut(BaseModel):
    id: str
    name: str
    center: Point
    radius_m: float
    is_placeholder: bool
    note: str = ""
    # GeoJSON geometry and [min_lon, min_lat, max_lon, max_lat]. The frontend
    # uses them to draw the real city line, not a misleading circle.
    boundary: dict[str, Any] | None = None
    bbox: list[float] | None = None


class DataOut(BaseModel):
    source: str
    fetched_at: str
    demo_mode: bool
    demo_reason: str = ""
    elevation_source: str = ""
    elevation_date: str = ""
    nodes: int
    edges: int


class AttributeCoverage(BaseModel):
    label: str
    known_length_m: float
    total_length_m: float
    coverage: float | None
    note: str = ""


class CoverageOut(BaseModel):
    attributes: dict[str, AttributeCoverage]
    overall: float | None
    note: str


class BarrierOut(BaseModel):
    segment_id: str
    reason: str
    attribute: str
    provenance: Provenance
    street_name: str | None = None
    distance_m: float


class SegmentOut(BaseModel):
    id: str
    u: str
    v: str
    key: str
    street_name: str | None
    highway: str | None
    coords: list[tuple[float, float]]
    length_m: float
    surface: str | None
    smoothness: str | None
    width_m: float | None
    grade_pct: float | None
    is_crossing: bool
    kerb: str | None
    provenance: dict[str, Provenance]
    unknown_attributes: list[str]
    cost: CostBreakdown
    field_audit: bool = False


class RouteOut(BaseModel):
    kind: Literal["shortest", "preferred", "relaxed"]
    distance_m: float
    cost_m_eq: float
    estimated_minutes: float
    speed_mps: float
    geometry: dict[str, Any]
    segments: list[SegmentOut]
    barriers: list[BarrierOut]
    coverage: CoverageOut
    is_relaxed: bool = False
    relaxed_constraints: list[str] = Field(default_factory=list)


class ExplanationOut(BaseModel):
    summary: str
    why_this_route: list[str]
    why_not_shortest: list[str]
    what_we_dont_know: list[str]
    reports: list[str]
    assumptions: list[str]
    coverage_note: str


class SensitivityVariant(BaseModel):
    value: float
    distance_m: float | None
    cost_m_eq: float | None
    differs_from_baseline: bool
    route_available: bool
    description: str


class SensitivityOut(BaseModel):
    parameter: str
    label: str
    baseline_value: float
    unit: str
    variants: list[SensitivityVariant]
    note: str


class NoFeasibleRouteOut(BaseModel):
    code: Literal["disconnected", "hard_constraints"]
    message: str
    blocking_reasons: list[str]
    shortest_route_available: bool
    relaxed_alternative_available: bool


class SnapOut(BaseModel):
    start_distance_m: float
    end_distance_m: float


class RouteResponse(BaseModel):
    area: AreaOut
    data: DataOut
    profile: dict[str, Any]
    risk: Risk
    shortest: RouteOut | None
    preferred: RouteOut | None
    relaxed_alternative: RouteOut | None
    no_feasible_route: NoFeasibleRouteOut | None
    explanation: ExplanationOut | None
    sensitivity: list[SensitivityOut]
    warnings: list[Warning]
    snap: SnapOut
    request_note: str = (
        "Coverage counts how much of the route has a mapped value, not how good the route "
        "is. Unknown data is neither safe nor blocked; it is priced according to your risk "
        "setting."
    )


class RouteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    start: Point
    end: Point
    profile: str | dict[str, Any] = "wheelchair"
    risk: Risk = Risk.BALANCED


class AreasResponse(BaseModel):
    areas: list[AreaOut]
    active: AreaOut


class HealthResponse(BaseModel):
    status: str
    graph_loaded: bool
    area: AreaOut | None
    areas: list[AreaOut] = Field(default_factory=list)
    data_date: str | None
    source: str | None
    demo_mode: bool
    nodes: int
    edges: int
    reports_database: str
    profiles: list[str]
    field_audits: int = 0
    admin_token_configured: bool = False
    graph_error: str | None = None
    warnings: list[Warning] = Field(default_factory=list)


class ReportCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    category: str
    description: str = Field(default="", max_length=500)
    # Honeypot: humans never see this field; bots that fill it get a generic reply.
    website: str = Field(default="", max_length=200)

    @field_validator("category")
    @classmethod
    def _category(cls, value: str) -> str:
        if value not in REPORT_CATEGORIES:
            raise ValueError("category must be one of: " + ", ".join(REPORT_CATEGORIES))
        return value

    @field_validator("description")
    @classmethod
    def _description(cls, value: str) -> str:
        text = value.strip()
        if len(text) > 500:
            raise ValueError("description must be 500 characters or fewer")
        return text


class ReportOut(BaseModel):
    id: int
    lat: float
    lon: float
    category: str
    description: str
    created_at: str
    status: ReportStatus
    reviewed_at: str | None
    last_confirmed_at: str | None
    influence: bool


class ReportCreateResponse(BaseModel):
    id: int
    status: ReportStatus
    message: str


class ReportGetResponse(BaseModel):
    bbox: str
    count: int
    reports: list[ReportOut]


class ReportPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: ReportStatus
    reconfirm: bool = False


class GeocodeResult(BaseModel):
    display_name: str
    lat: float
    lon: float
    category: str = ""


class GeocodeResponse(BaseModel):
    results: list[GeocodeResult]
    attribution: str
    cached: bool


class ProfilesResponse(BaseModel):
    profiles: list[Profile]
    parameter_specs: list[dict[str, Any]]
    risks: list[Risk]
    risk_note: str
    disclaimer: str


class AdminInfo(BaseModel):
    admin_token_configured: bool


class ErrorBody(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    error: ErrorBody


class ReportPatchResponse(BaseModel):
    report: ReportOut
    message: str


class GeocodeAttribution(BaseModel):
    """Reserved for future attribution metadata; kept small on purpose."""

    text: str
    url: str
    timestamp: datetime | None = None


def default_speed_note(profile: Profile) -> str:
    return (
        f"Travel time is an estimate using {profile.walking_speed_mps:.2f} m/s, "
        "a user-adjustable assumption, not a guarantee."
    )
