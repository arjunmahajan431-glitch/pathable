"""Small geometry helpers used by the field-audit importer and evaluation.

Distances use a local equirectangular projection, which is accurate enough at
the scale of a neighborhood and avoids a heavy GIS dependency for a point-to-
polyline calculation. Routing distances always come from OSMnx/OSM geometry.
"""

from __future__ import annotations

import math
from itertools import pairwise

import networkx as nx

from pathable.graph.model import EdgeFeatures, edge_uid

R = 6_371_008.8


def _xy(lat0: float, lon0: float, lat: float, lon: float) -> tuple[float, float]:
    x = math.radians(lon - lon0) * math.cos(math.radians(lat0)) * R
    y = math.radians(lat - lat0) * R
    return x, y


def _point_segment_distance(
    px: float, py: float, ax: float, ay: float, bx: float, by: float
) -> tuple[float, float, float]:
    dx, dy = bx - ax, by - ay
    denom = dx * dx + dy * dy
    if denom == 0:
        return math.hypot(px - ax, py - ay), ax, ay
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / denom))
    nx_, ny_ = ax + t * dx, ay + t * dy
    return math.hypot(px - nx_, py - ny_), nx_, ny_


def distance_to_polyline_m(
    lat: float, lon: float, coords: tuple[tuple[float, float], ...] | list[tuple[float, float]]
) -> float:
    """Shortest distance from a point to a lon/lat polyline, in meters."""
    if not coords:
        return float("inf")
    projected = [_xy(lat, lon, y, x) for x, y in coords]
    if len(projected) == 1:
        return math.hypot(*projected[0])
    best = float("inf")
    for (ax, ay), (bx, by) in pairwise(projected):
        d, _, _ = _point_segment_distance(0.0, 0.0, ax, ay, bx, by)
        best = min(best, d)
    return best


def nearest_edge(
    graph: nx.MultiDiGraph, lat: float, lon: float
) -> tuple[str, float, tuple[float, float]]:
    """Return (edge_uid, snap distance in meters, nearest point lon/lat)."""
    best_uid = ""
    best_distance = float("inf")
    best_point = (lon, lat)
    for u, v, key, data in graph.edges(keys=True, data=True):
        features: EdgeFeatures = data["features"]
        coords = list(features.coords)
        if not coords:
            uf = graph.nodes[u]["features"]
            vf = graph.nodes[v]["features"]
            coords = [(uf.lon, uf.lat), (vf.lon, vf.lat)]
        projected = [_xy(lat, lon, y, x) for x, y in coords]
        for (ax, ay), (bx, by) in pairwise(projected):
            segment_distance, nx_, ny_ = _point_segment_distance(0.0, 0.0, ax, ay, bx, by)
            if segment_distance < best_distance - 1e-9:
                best_distance = segment_distance
                best_uid = edge_uid(u, v, key)
                # Recover lon/lat from the local projection at the nearest point.
                lon_out = lon + math.degrees(nx_ / (R * math.cos(math.radians(lat))))
                lat_out = lat + math.degrees(ny_ / R)
                best_point = (lon_out, lat_out)
        if len(projected) == 1:
            ax, ay = projected[0]
            segment_distance = math.hypot(ax, ay)
            if segment_distance < best_distance - 1e-9:
                best_distance = segment_distance
                best_uid = edge_uid(u, v, key)
                best_point = (coords[0][0], coords[0][1])
    return best_uid, best_distance, best_point


def audit_point_for_edge(graph: nx.MultiDiGraph, uid: str) -> tuple[float, float] | None:
    """Find the midpoint of an edge by uid (used by evaluation)."""
    for u, v, key, data in graph.edges(keys=True, data=True):
        if edge_uid(u, v, key) == uid:
            features: EdgeFeatures = data["features"]
            coords = features.coords or (
                (graph.nodes[u]["features"].lon, graph.nodes[u]["features"].lat),
                (graph.nodes[v]["features"].lon, graph.nodes[v]["features"].lat),
            )
            mid = coords[len(coords) // 2]
            return float(mid[1]), float(mid[0])
    return None


def feature_from_uid(graph: nx.MultiDiGraph, uid: str) -> EdgeFeatures | None:
    for u, v, key, data in graph.edges(keys=True, data=True):
        if edge_uid(u, v, key) == uid:
            features: EdgeFeatures = data["features"]
            return features
    return None
