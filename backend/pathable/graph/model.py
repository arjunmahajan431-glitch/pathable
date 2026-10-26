"""Internal, normalized graph features.

Raw OpenStreetMap tags are messy: after OSMnx simplification a single edge can
carry a list of values, and most accessibility attributes are simply absent.
``EdgeFeatures`` is the router-facing view: one value per attribute plus an
explicit provenance tier. Absent data is ``None`` with ``Provenance.UNKNOWN``;
it is never silently treated as safe.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from pathable.models import Provenance

ROUGHNESS_CLASSES = ("smooth", "moderate", "rough", "very_rough")


@dataclass(slots=True)
class NodeFeatures:
    lat: float
    lon: float
    kerb: str | None = None
    kerb_prov: Provenance = Provenance.UNKNOWN
    tactile_paving: str | None = None
    tactile_prov: Provenance = Provenance.UNKNOWN
    barrier: str | None = None
    barrier_prov: Provenance = Provenance.UNKNOWN
    wheelchair: str | None = None
    wheelchair_prov: Provenance = Provenance.UNKNOWN


@dataclass(slots=True)
class EdgeFeatures:
    length_m: float
    highway: str | None = None
    footway: str | None = None
    street_name: str | None = None

    surface: str | None = None
    surface_prov: Provenance = Provenance.UNKNOWN
    smoothness: str | None = None
    smoothness_prov: Provenance = Provenance.UNKNOWN
    roughness_class: str | None = None
    roughness_prov: Provenance = Provenance.UNKNOWN
    roughness_note: str = ""

    width_m: float | None = None
    width_prov: Provenance = Provenance.UNKNOWN
    width_note: str = ""

    grade_pct: float | None = None
    grade_prov: Provenance = Provenance.UNKNOWN
    incline_sign: int | None = None
    incline_magnitude_pct: float | None = None
    incline_raw: str | None = None

    steps_known: bool = False
    is_steps: bool = False
    step_count: int | None = None
    steps_prov: Provenance = Provenance.UNKNOWN

    wheelchair: str | None = None
    wheelchair_prov: Provenance = Provenance.UNKNOWN

    access_ok: bool = True
    access_reason: str = ""
    access_prov: Provenance = Provenance.UNKNOWN

    lit: bool | None = None
    lit_prov: Provenance = Provenance.UNKNOWN

    crossing: str | None = None
    crossing_prov: Provenance = Provenance.UNKNOWN
    is_crossing: bool = False
    kerb: str | None = None
    kerb_prov: Provenance = Provenance.UNKNOWN
    tactile_paving: str | None = None
    tactile_prov: Provenance = Provenance.UNKNOWN

    barrier: str | None = None
    barrier_prov: Provenance = Provenance.UNKNOWN

    reversed_raw: str | None = None
    coords: tuple[tuple[float, float], ...] = ()
    osm: dict[str, str] = field(default_factory=dict)
    audit: dict[str, str] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    # Populated when a field audit overrides an OSM value, so both can be shown.
    osm_grade_pct: float | None = None
    osm_width_m: float | None = None
    osm_kerb: str | None = None


@dataclass(slots=True)
class GraphMeta:
    area_id: str
    area_name: str
    center_lat: float
    center_lon: float
    radius_m: float
    source: str
    fetched_at: str
    demo_mode: bool = False
    demo_reason: str = ""
    elevation_source: str = ""
    elevation_date: str = ""
    graph_schema: int = 1


def edge_uid(u: object, v: object, key: object) -> str:
    """Stable identifier used by audits and the API."""
    return f"{u}:{v}:{key}"
