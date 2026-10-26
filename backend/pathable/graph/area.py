"""City boundary helpers.

A radius alone is a poor description of a city: a circle either misses
neighborhoods or includes neighboring towns. When an area supplies a boundary
GeoJSON file, the app uses that polygon for graph downloads, report checks, and
route start/end validation. The radius remains as a generous bounding circle and
as a fallback for areas that do not have a boundary.
"""

from __future__ import annotations

import json
import math
from functools import lru_cache
from pathlib import Path
from typing import Any, cast

from shapely.geometry import Point, mapping, shape
from shapely.geometry.base import BaseGeometry

from pathable.config import AreaConfig


@lru_cache(maxsize=32)
def _load_geometry(path: str) -> BaseGeometry:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("type") == "FeatureCollection":
        features = payload.get("features") or []
        if not features:
            raise ValueError(f"boundary file has no features: {path}")
        payload = features[0]["geometry"]
    elif payload.get("type") == "Feature":
        payload = payload["geometry"]
    geometry = shape(payload)
    if geometry.is_empty:
        raise ValueError(f"boundary geometry is empty: {path}")
    if not geometry.is_valid:
        geometry = geometry.buffer(0)
    return geometry


def boundary_for(area: AreaConfig) -> BaseGeometry | None:
    path = area.boundary_path
    if path is None:
        return None
    if not path.exists():
        raise FileNotFoundError(f"Area boundary file is missing: {path}")
    return _load_geometry(str(path))


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6_371_008.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = p2 - p1
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(a))


def area_contains(area: AreaConfig, lat: float, lon: float) -> bool:
    boundary = boundary_for(area)
    if boundary is not None:
        # A tiny tolerance keeps points exactly on the line inside the city.
        return bool(boundary.buffer(1e-7).covers(Point(lon, lat)))
    return haversine_m(area.center.lat, area.center.lon, lat, lon) <= area.radius_m + 0.5


def area_bbox(area: AreaConfig) -> tuple[float, float, float, float]:
    """Return (min_lon, min_lat, max_lon, max_lat) for address search and maps."""
    boundary = boundary_for(area)
    if boundary is not None:
        min_lon, min_lat, max_lon, max_lat = boundary.bounds
        return min_lon, min_lat, max_lon, max_lat
    lat_span = area.radius_m / 111_320.0
    lon_span = lat_span / max(0.2, abs(math.cos(math.radians(area.center.lat))))
    return (
        area.center.lon - lon_span,
        area.center.lat - lat_span,
        area.center.lon + lon_span,
        area.center.lat + lat_span,
    )


def area_boundary_geojson(area: AreaConfig) -> dict[str, Any] | None:
    boundary = boundary_for(area)
    if boundary is None:
        return None
    return cast(dict[str, Any], mapping(boundary))
