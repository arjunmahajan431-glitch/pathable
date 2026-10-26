"""Shared domain models for PathAble.

These types are deliberately independent of FastAPI so that the routing engine
can be imported and tested without a web server. Pydantic is used for input
validation where values are user-tunable.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

REPORT_CATEGORIES: tuple[str, ...] = (
    "blocked_sidewalk",
    "missing_or_damaged_curb_ramp",
    "stairs_or_inaccessible_entrance",
    "rough_or_damaged_pavement",
    "construction",
    "other",
)


class Provenance(StrEnum):
    """Where a value came from.

    The ordering matters: when two sources disagree we keep both but use the
    stronger one for routing. It is the tier order from the project brief.
    """

    FIELD_AUDIT = "FIELD_AUDIT"
    OSM_MAPPED = "OSM_MAPPED"
    COMMUNITY_REPORT = "COMMUNITY_REPORT"
    DEM_ESTIMATED = "DEM_ESTIMATED"
    UNKNOWN = "UNKNOWN"

    @property
    def rank(self) -> int:
        return _PROVENANCE_RANK[self]

    @property
    def is_known(self) -> bool:
        return self is not Provenance.UNKNOWN

    def __lt__(self, other: Provenance) -> bool:  # type: ignore[override]
        return self.rank < other.rank


_PROVENANCE_RANK = {
    Provenance.FIELD_AUDIT: 5,
    Provenance.OSM_MAPPED: 4,
    Provenance.COMMUNITY_REPORT: 3,
    Provenance.DEM_ESTIMATED: 2,
    Provenance.UNKNOWN: 1,
}


class Risk(StrEnum):
    """How much the user wants to pay for unknown data."""

    DIRECT = "direct"
    BALANCED = "balanced"
    CAUTIOUS = "cautious"


# The three risk multipliers are applied only to *uncertainty* prices.
# They are chosen so that the synthetic fixture profile's 75 m-eq balanced
# unknown-kerb penalty becomes exactly 25 (direct) and 200 (cautious); see
# docs/COST_MODEL.md. They are an ASSUMPTION, not a standard.
RISK_SCALE: dict[Risk, float] = {
    Risk.DIRECT: 1.0 / 3.0,
    Risk.BALANCED: 1.0,
    Risk.CAUTIOUS: 8.0 / 3.0,
}


class Point(BaseModel):
    model_config = ConfigDict(extra="forbid")
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


class HardBlock(BaseModel):
    """An explicit restriction. Never represented by infinity or a magic cost."""

    reason: str
    attribute: str
    provenance: Provenance


class CostTerm(BaseModel):
    """One contributor to an edge's generalized cost."""

    name: str
    kind: Literal["multiplier", "penalty"]
    value: float
    m_eq: float
    reason: str
    provenance: Provenance


class CostBreakdown(BaseModel):
    """Explainable edge cost in meter-equivalents (m-eq).

    ``total_m_eq`` is computed even when ``hard_block`` is set; the block is a
    separate flag so explanations can say *why* the shortest route fails the
    user's profile instead of printing a meaningless infinity.
    """

    length_m: float
    base_m_eq: float
    terms: list[CostTerm] = Field(default_factory=list)
    total_m_eq: float
    hard_block: HardBlock | None = None
    profile: str
    risk: Risk

    @property
    def blocked(self) -> bool:
        return self.hard_block is not None


class Profile(BaseModel):
    """User-tunable cost parameters.

    Every default is either sourced in docs/STANDARDS.md or explicitly marked
    there as an ASSUMPTION. The defaults below define the packaged
    ``wheelchair`` profile; other packaged profiles override a subset in
    ``pathable/engine/profiles.py``.
    """

    model_config = ConfigDict(extra="forbid")

    name: str = Field(default="wheelchair", min_length=1, max_length=64)
    label: str = Field(default="Wheelchair", max_length=80)
    description: str = Field(default="", max_length=500)

    # --- steps -------------------------------------------------------------
    steps: Literal["block", "penalize"] = "block"
    steps_penalty_m: float = Field(default=750.0, ge=0)  # ASSUMPTION
    steps_per_step_penalty_m: float = Field(default=10.0, ge=0)  # ASSUMPTION
    unknown_steps_factor: float = Field(default=0.20, ge=0, le=5)  # ASSUMPTION

    # --- OSM wheelchair tag -------------------------------------------------
    respect_wheelchair_tag: bool = True
    wheelchair_limited_penalty_m: float = Field(default=100.0, ge=0)  # ASSUMPTION

    # --- grade -------------------------------------------------------------
    # Soft = no penalty at or below this running grade. Hard = the blocking or
    # high-penalty threshold. Sources and scope are in docs/STANDARDS.md.
    soft_grade_up_pct: float = Field(default=5.0, ge=0, le=50)
    hard_grade_up_pct: float = Field(default=8.33, gt=0, le=50)
    soft_grade_down_pct: float = Field(default=8.0, ge=0, le=50)
    hard_grade_down_pct: float = Field(default=12.0, gt=0, le=50)
    grade_factor_up: float = Field(default=0.25, ge=0, le=5)
    grade_factor_down: float = Field(default=0.15, ge=0, le=5)
    hard_grade_action: Literal["block", "penalize"] = "block"
    hard_grade_penalty_m: float = Field(default=500.0, ge=0)  # ASSUMPTION
    # Estimated (DEM) grades get this fraction of a mapped grade's penalty and
    # never hard-block: 30 m elevation data is not a sidewalk measurement.
    dem_confidence: float = Field(default=0.6, ge=0, le=1)

    # --- surface / smoothness ----------------------------------------------
    surface_multipliers: dict[str, float] = Field(
        default_factory=lambda: {
            "smooth": 1.0,
            "moderate": 1.35,
            "rough": 2.2,
            "very_rough": 4.0,
        }
    )
    unknown_surface_factor: float = Field(default=0.06, ge=0, le=5)
    unknown_smoothness_factor: float = Field(default=0.06, ge=0, le=5)

    # --- width --------------------------------------------------------------
    # PROWAG R302.2 (2023) sets 48 in / 1.22 m as the continuous clear width
    # for a pedestrian access route in the public right-of-way. ADA 2010
    # 403.5.1's 36 in / 0.915 m applies to accessible routes on a site; it is
    # shown in docs/STANDARDS.md for comparison, not used as the default here.
    min_width_m: float = Field(default=1.22, gt=0, le=5)
    width_penalty_factor: float = Field(default=0.5, ge=0, le=5)
    unknown_width_factor: float = Field(default=0.08, ge=0, le=5)

    # --- crossings / kerbs --------------------------------------------------
    kerb_raised_penalty_m: float = Field(default=150.0, ge=0)
    kerb_unknown_penalty_m: float = Field(default=100.0, ge=0)
    crossing_uncontrolled_penalty_m: float = Field(default=20.0, ge=0)
    crossing_unknown_penalty_m: float = Field(default=10.0, ge=0)
    barrier_penalty_m: float = Field(default=30.0, ge=0)

    # --- lighting / crossings preference ------------------------------------
    avoid_unlit: bool = False
    lit_off_penalty_m: float = Field(default=40.0, ge=0)
    unknown_lit_factor: float = Field(default=0.03, ge=0, le=5)

    # --- community reports ---------------------------------------------------
    community_report_penalties_m: dict[str, float] = Field(
        default_factory=lambda: {
            "blocked_sidewalk": 300.0,
            "missing_or_damaged_curb_ramp": 150.0,
            "stairs_or_inaccessible_entrance": 300.0,
            "rough_or_damaged_pavement": 120.0,
            "construction": 200.0,
            "other": 50.0,
        }
    )

    # --- time estimate (an assumption, shown as an estimate) ----------------
    walking_speed_mps: float = Field(default=0.8, ge=0.1, le=3.0)

    # --- unknown grade -------------------------------------------------------
    unknown_grade_factor: float = Field(default=0.15, ge=0, le=5)

    @model_validator(mode="after")
    def _validate_profile(self) -> Profile:
        if self.soft_grade_up_pct > self.hard_grade_up_pct:
            raise ValueError("soft_grade_up_pct must be <= hard_grade_up_pct")
        if self.soft_grade_down_pct > self.hard_grade_down_pct:
            raise ValueError("soft_grade_down_pct must be <= hard_grade_down_pct")
        required_roughness = {"smooth", "moderate", "rough", "very_rough"}
        if set(self.surface_multipliers) != required_roughness:
            raise ValueError(
                "surface_multipliers must define exactly " + ", ".join(sorted(required_roughness))
            )
        for cls, mult in self.surface_multipliers.items():
            if mult < 1.0:
                raise ValueError(f"surface multiplier for {cls} must be >= 1 (no rewards)")
        for category, penalty in self.community_report_penalties_m.items():
            if category not in REPORT_CATEGORIES:
                raise ValueError(f"unknown report category in profile: {category}")
            if penalty < 0:
                raise ValueError("community report penalties must be >= 0")
        for category in REPORT_CATEGORIES:
            if category not in self.community_report_penalties_m:
                raise ValueError(f"missing community report penalty for {category}")
        return self

    def risk_scale(self, risk: Risk) -> float:
        return RISK_SCALE[risk]
