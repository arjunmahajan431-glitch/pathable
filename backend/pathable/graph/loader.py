"""Load, cache and normalize the pedestrian graph.

Live data comes from OpenStreetMap through OSMnx/Overpass. If that fails (or
demo mode is requested) we load a committed, clearly labeled OSM extract. We
never synthesize "real-looking" attributes: missing tags stay UNKNOWN.
"""

from __future__ import annotations

import gzip
import json
import logging
import math
import pickle
import shutil
import tempfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from itertools import pairwise
from pathlib import Path
from typing import Any

import networkx as nx
import osmnx as ox
from shapely.geometry import LineString, Point

from pathable.config import AppConfig, AreaConfig
from pathable.graph.area import boundary_for
from pathable.graph.features import (
    apply_audit,
    apply_elevation,
    build_edge_features,
    normalize_node,
)
from pathable.graph.model import GraphMeta, NodeFeatures, edge_uid

logger = logging.getLogger(__name__)

EARTH_RADIUS_M = 6_371_008.8

# Bump when normalized features or tag parsing change. The pickle cache is a
# local speed-up only; a mismatch simply rebuilds it from GraphML.
NORMALIZED_CACHE_VERSION = 1

# OSMnx discards tags not listed here. Everything the router or the field-audit
# comparison needs must be requested explicitly.
EXTRA_WAY_TAGS = [
    "surface",
    "smoothness",
    "width",
    "est_width",
    "incline",
    "steps",
    "step_count",
    "wheelchair",
    "foot",
    "lit",
    "crossing",
    "crossing:markings",
    "crossing:signals",
    "kerb",
    "tactile_paving",
    "barrier",
    "sidewalk",
    "name",
    "description",
]
EXTRA_NODE_TAGS = [
    "kerb",
    "tactile_paving",
    "barrier",
    "wheelchair",
    "crossing",
    "highway",
    "foot",
    "name",
]


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in meters."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = p2 - p1
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


@dataclass
class GraphBundle:
    graph: nx.MultiDiGraph
    meta: GraphMeta
    warnings: list[str] = field(default_factory=list)
    path: Path | None = None


def configure_osmnx(config: AppConfig) -> None:
    """Install our tag list and polite network settings before any OSMnx call."""
    for tag in EXTRA_WAY_TAGS:
        if tag not in ox.settings.useful_tags_way:
            ox.settings.useful_tags_way.append(tag)
    for tag in EXTRA_NODE_TAGS:
        if tag not in ox.settings.useful_tags_node:
            ox.settings.useful_tags_node.append(tag)
    ox.settings.log_console = False
    ox.settings.use_cache = True
    ox.settings.cache_folder = str(config.cache_dir / "osmnx")
    # A whole-city walk network is much larger than a neighborhood extract.
    # The public Overpass instance needs more than three minutes for some
    # cities, so the HTTP timeout is deliberately generous.
    ox.settings.requests_timeout = 600


def _log_fetch(cache_dir: Path, message: str) -> None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).isoformat(timespec="seconds")
    with (cache_dir / "fetch.log").open("a", encoding="utf-8") as fh:
        fh.write(f"{stamp} {message}\n")


def _area_stem(area: AreaConfig) -> str:
    # Boundary areas get a stable city suffix, so changing the bounding radius
    # does not orphan an already downloaded citywide graph.
    return f"{area.id}-city" if area.boundary else f"{area.id}-{round(area.radius_m)}"


def _cache_paths(config: AppConfig, area: AreaConfig) -> tuple[Path, Path]:
    stem = f"graph-{_area_stem(area)}"
    return config.cache_dir / f"{stem}.graphml", config.cache_dir / f"{stem}.meta.json"


def _elevation_cache_path(config: AppConfig, area: AreaConfig) -> Path:
    return config.cache_dir / f"elevation-{_area_stem(area)}.json"


def _normalized_cache_path(config: AppConfig, area: AreaConfig) -> Path:
    return config.cache_dir / f"graph-{_area_stem(area)}.normalized.pkl"


def _demo_normalized_cache_path(config: AppConfig, area: AreaConfig) -> Path:
    return config.cache_dir / f"graph-{_area_stem(area)}.demo.normalized.pkl"


def _file_stamp(path: Path) -> int:
    try:
        return path.stat().st_mtime_ns
    except OSError:
        return 0


def _cache_stamp(graphml_path: Path, elevation_path: Path) -> dict[str, int]:
    return {
        "version": NORMALIZED_CACHE_VERSION,
        "graph": _file_stamp(graphml_path),
        "elevation": _file_stamp(elevation_path),
    }


def _load_normalized_cache(
    cache_path: Path,
    graphml_path: Path,
    elevation_path: Path,
    meta: GraphMeta,
) -> nx.MultiDiGraph | None:
    """Load the pickled normalized graph if it matches its source files.

    Normalizing a citywide graph takes about 12 seconds because every OSM tag
    is parsed into typed features. The pickle is a local, regenerable cache:
    it is only trusted when the GraphML, elevation file and cache version all
    match. Audited graphs are never cached, so field corrections cannot go stale.
    """
    if not cache_path.exists():
        return None
    try:
        with cache_path.open("rb") as fh:
            payload = pickle.load(fh)
        if not isinstance(payload, dict):
            return None
        if payload.get("stamp") != _cache_stamp(graphml_path, elevation_path):
            return None
        graph = payload.get("graph")
        if not isinstance(graph, nx.MultiDiGraph):
            return None
        graph.graph["meta"] = meta
        return graph
    except (OSError, pickle.PickleError, EOFError, AttributeError, ValueError) as exc:
        logger.warning("Ignoring unreadable normalized graph cache %s: %s", cache_path, exc)
        return None


def _write_normalized_cache(
    cache_path: Path,
    graphml_path: Path,
    elevation_path: Path,
    graph: nx.MultiDiGraph,
) -> None:
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = cache_path.with_suffix(".pkl.tmp")
        with temporary.open("wb") as fh:
            pickle.dump(
                {"stamp": _cache_stamp(graphml_path, elevation_path), "graph": graph},
                fh,
                protocol=pickle.HIGHEST_PROTOCOL,
            )
        temporary.replace(cache_path)
    except OSError as exc:
        logger.warning("Could not write normalized graph cache %s: %s", cache_path, exc)


def download_graph(config: AppConfig, area: AreaConfig) -> Path:
    """Download the walk network for an area, save GraphML plus metadata.

    When the area has a boundary, the polygon is the download shape. That is
    what makes a whole-city mapping area possible without pulling in an
    arbitrary circle of neighboring towns. Boundary nodes get a small buffer so
    crossings and edge geometry are not cut off at the city line.
    """
    configure_osmnx(config)
    config.cache_dir.mkdir(parents=True, exist_ok=True)
    boundary = boundary_for(area)
    if boundary is not None:
        logger.info("Downloading OSM walk graph for %s (city boundary)", area.id)
        buffered = boundary.buffer(0.0005)
        raw = ox.graph_from_polygon(
            boundary,
            network_type="walk",
            simplify=True,
            retain_all=True,
            truncate_by_edge=True,
        )
        keep = {
            node
            for node, data in raw.nodes(data=True)
            if buffered.covers(Point(data["x"], data["y"]))
        }
    else:
        logger.info("Downloading OSM walk graph for %s (%s m radius)", area.id, area.radius_m)
        # OSMnx's "network" distance type needs scikit-learn for nearest-node
        # search; downloading a bounding box and filtering by haversine keeps the
        # dependency set smaller and gives an exact circle.
        raw = ox.graph_from_point(
            (area.center.lat, area.center.lon),
            dist=area.radius_m,
            dist_type="bbox",
            network_type="walk",
            simplify=True,
            retain_all=True,
        )
        keep = {
            node
            for node, data in raw.nodes(data=True)
            if haversine_m(area.center.lat, area.center.lon, data["y"], data["x"]) <= area.radius_m
        }
    if not keep:
        raise RuntimeError("Overpass returned no pedestrian nodes inside the mapping area")
    raw = raw.subgraph(keep).copy()
    graphml_path, meta_path = _cache_paths(config, area)
    ox.save_graphml(raw, graphml_path)
    meta = {
        "area_id": area.id,
        "area_name": area.name,
        "center": {"lat": area.center.lat, "lon": area.center.lon},
        "radius_m": area.radius_m,
        "boundary": area.boundary,
        "source": "OpenStreetMap via Overpass API (walk network, simplified)",
        "fetched_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "nodes": raw.number_of_nodes(),
        "edges": raw.number_of_edges(),
    }
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    _log_fetch(
        config.cache_dir,
        f"OSM graph downloaded area={area.id} "
        f"extent={'boundary' if boundary is not None else f'{area.radius_m:.0f} m radius'} "
        f"nodes={raw.number_of_nodes()} edges={raw.number_of_edges()}",
    )
    logger.info(
        "Saved graph to %s (%s nodes, %s edges)", graphml_path, len(raw), raw.number_of_edges()
    )
    return graphml_path


def _materialize_graphml(path: Path) -> Path:
    """OSMnx cannot read gzip directly; decompress committed samples to temp."""
    if path.suffix != ".gz":
        return path
    with (
        gzip.open(path, "rb") as src,
        tempfile.NamedTemporaryFile(suffix=".graphml", delete=False) as dst,
    ):
        shutil.copyfileobj(src, dst)
        return Path(dst.name)


def load_elevations(path: Path) -> tuple[dict[str, float], str, str]:
    """Load a cached node-elevation file: {elevations, source, date}."""
    if not path.exists():
        return {}, "", ""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Could not read elevation cache %s: %s", path, exc)
        return {}, "", ""
    raw = payload.get("elevations", {})
    elevations = {str(k): float(v) for k, v in raw.items() if v is not None}
    return elevations, str(payload.get("source", "")), str(payload.get("date", ""))


def _edge_coords(
    raw: dict[str, Any], u_data: dict[str, Any], v_data: dict[str, Any]
) -> list[tuple[float, float]]:
    geometry = raw.get("geometry")
    if isinstance(geometry, LineString):
        return [(float(x), float(y)) for x, y in geometry.coords]
    return [
        (float(u_data["x"]), float(u_data["y"])),
        (float(v_data["x"]), float(v_data["y"])),
    ]


def normalize_graph(
    raw: nx.MultiDiGraph,
    meta: GraphMeta,
    elevations: dict[str, float] | None = None,
    audits: list[dict[str, Any]] | None = None,
) -> nx.MultiDiGraph:
    """Build the router-facing MultiDiGraph from a raw OSMnx graph."""
    elevations = elevations or {}
    audits_by_edge: dict[str, dict[str, Any]] = {}
    for audit in audits or []:
        uid = str(audit.get("edge_uid") or "")
        if uid:
            audits_by_edge[uid] = audit

    graph = nx.MultiDiGraph()
    graph.graph["meta"] = meta

    node_features: dict[Any, NodeFeatures] = {}
    for node, data in raw.nodes(data=True):
        features = normalize_node(data)
        node_features[node] = features
        graph.add_node(node, x=features.lon, y=features.lat, features=features)

    for u, v, key, raw_data in raw.edges(keys=True, data=True):
        if u not in node_features or v not in node_features:
            continue
        length = raw_data.get("length")
        u_data = raw.nodes[u]
        v_data = raw.nodes[v]
        coords = _edge_coords(raw_data, u_data, v_data)
        if length is None:
            length = sum(haversine_m(a[1], a[0], b[1], b[0]) for a, b in pairwise(coords))
        edge_features = build_edge_features(
            raw_data,
            float(length),
            node_features[u],
            node_features[v],
            coords,
        )
        if raw_data.get("osmid") is not None:
            edge_features.notes.append(f"osm way {raw_data.get('osmid')}")
        if elevations:
            apply_elevation(
                edge_features,
                elevations.get(str(u)),
                elevations.get(str(v)),
            )
        edge_audit = audits_by_edge.get(edge_uid(u, v, key))
        if edge_audit:
            apply_audit(edge_features, edge_audit)
        graph.add_edge(u, v, key=key, features=edge_features, length=edge_features.length_m)

    # NetworkX MultiGraph size queries walk every edge. The UI asks for these
    # counts on each route response, so cache them once at load.
    graph.graph["_pathable_node_count"] = graph.number_of_nodes()
    graph.graph["_pathable_edge_count"] = graph.number_of_edges()
    return graph


def graph_counts(graph: nx.MultiDiGraph) -> tuple[int, int]:
    """Cached node and edge counts.

    ``MultiDiGraph.number_of_edges()`` walks the edge view, which costs about a
    second on a citywide graph. API responses ask for the counts every time.
    """
    nodes = graph.graph.get("_pathable_node_count")
    edges = graph.graph.get("_pathable_edge_count")
    if not isinstance(nodes, int) or not isinstance(edges, int):
        nodes = graph.number_of_nodes()
        edges = graph.number_of_edges()
        graph.graph["_pathable_node_count"] = nodes
        graph.graph["_pathable_edge_count"] = edges
    return nodes, edges


def _sample_paths(config: AppConfig, area: AreaConfig) -> tuple[Path, Path]:
    graph = area.sample_graph or config.data.sample_graph
    elevation = area.sample_elevation or config.data.sample_elevation
    return config.path(graph), config.path(elevation)


def _sample_meta(config: AppConfig, reason: str, area: AreaConfig) -> GraphMeta:
    return GraphMeta(
        area_id=area.id,
        area_name=area.name,
        center_lat=area.center.lat,
        center_lon=area.center.lon,
        radius_m=area.radius_m,
        source=config.data.sample_graph_source,
        fetched_at=config.data.sample_graph_date,
        demo_mode=True,
        demo_reason=reason,
        # Filled in only if the committed elevation cache actually exists.
        elevation_source="",
        elevation_date="",
    )


def _load_sample(
    config: AppConfig, reason: str, audits: list[dict[str, Any]] | None, area: AreaConfig
) -> GraphBundle:
    sample, sample_elevation = _sample_paths(config, area)
    if not sample.exists():
        raise FileNotFoundError(
            f"No live graph cache and committed sample graph is missing: {sample}"
        )
    elevations, elev_source, elev_date = load_elevations(sample_elevation)
    meta = _sample_meta(config, reason, area)
    if elev_source:
        meta.elevation_source = elev_source
    if elev_date:
        meta.elevation_date = elev_date

    cache_path = _demo_normalized_cache_path(config, area)
    graph: nx.MultiDiGraph | None = None
    if not audits:
        graph = _load_normalized_cache(cache_path, sample, sample_elevation, meta)
    if graph is None:
        configure_osmnx(config)
        materialized = _materialize_graphml(sample)
        try:
            raw = ox.load_graphml(materialized)
        finally:
            if materialized != sample:
                materialized.unlink(missing_ok=True)
        graph = normalize_graph(raw, meta, elevations, audits)
        if not audits:
            _write_normalized_cache(cache_path, sample, sample_elevation, graph)
    _log_fetch(config.cache_dir, f"Loaded committed sample graph ({reason})")
    warnings = [
        "DEMO MODE: live OpenStreetMap download is unavailable or disabled. "
        f"Using a committed OSM extract from {config.data.sample_graph_date} "
        f"({config.data.sample_graph_source}). Routes may be stale.",
        "Coverage counts mapped length, not route quality. "
        "Unknown data is neither safe nor blocked.",
    ]
    return GraphBundle(graph=graph, meta=meta, warnings=warnings, path=sample)


def load_area_graph(
    config: AppConfig,
    *,
    area: AreaConfig | None = None,
    allow_download: bool = False,
    demo_mode: bool | None = None,
    audits: list[dict[str, Any]] | None = None,
) -> GraphBundle:
    """Load one area graph, falling back to that area's labeled sample.

    ``allow_download`` is False for normal API startup so a slow Overpass
    request cannot block the service; ``make data`` populates the cache.
    """
    target = area or config.area
    demo = config.demo_forced if demo_mode is None else demo_mode
    if demo:
        return _load_sample(config, "PATHABLE_DEMO requested", audits, target)

    override = __import__("os").environ.get("PATHABLE_GRAPH", "").strip()
    graphml_path, meta_path = _cache_paths(config, target)
    path = Path(override) if override and target.id == config.area.id else graphml_path
    if not path.exists():
        if allow_download:
            try:
                path = download_graph(config, target)
            except Exception as exc:
                logger.warning("OSM download failed: %s", exc)
                return _load_sample(config, f"OSM download failed: {exc}", audits, target)
        else:
            return _load_sample(
                config,
                "no cached OSM graph; run `make data` to download",
                audits,
                target,
            )

    fetched_at = datetime.fromtimestamp(path.stat().st_mtime, UTC).isoformat(timespec="seconds")
    source = "OpenStreetMap via Overpass API (walk network, simplified)"
    if meta_path.exists() and not override:
        try:
            meta_json = json.loads(meta_path.read_text(encoding="utf-8"))
            fetched_at = str(meta_json.get("fetched_at", fetched_at))
            source = str(meta_json.get("source", source))
        except (OSError, json.JSONDecodeError):
            pass
    elevation_path = _elevation_cache_path(config, target)
    elevations, elev_source, elev_date = load_elevations(elevation_path)
    meta = GraphMeta(
        area_id=target.id,
        area_name=target.name,
        center_lat=target.center.lat,
        center_lon=target.center.lon,
        radius_m=target.radius_m,
        source=source,
        fetched_at=fetched_at,
        demo_mode=False,
        elevation_source=elev_source,
        elevation_date=elev_date,
    )

    cache_path = _normalized_cache_path(config, target)
    graph: nx.MultiDiGraph | None = None
    if not override and not audits:
        graph = _load_normalized_cache(cache_path, path, elevation_path, meta)
    if graph is None:
        configure_osmnx(config)
        materialized = _materialize_graphml(path)
        try:
            raw = ox.load_graphml(materialized)
        finally:
            if materialized != path:
                materialized.unlink(missing_ok=True)
        graph = normalize_graph(raw, meta, elevations, audits)
        if not override and not audits:
            _write_normalized_cache(cache_path, path, elevation_path, graph)
        source_label = "cached OSM graph"
    else:
        source_label = "normalized graph cache"
    node_count, edge_count = graph_counts(graph)
    _log_fetch(
        config.cache_dir,
        f"Loaded {source_label} area={target.id} nodes={node_count} edges={edge_count}",
    )
    warnings: list[str] = []
    if not elevations:
        warnings.append(
            "No elevation cache found: unmapped grades are UNKNOWN and priced as a risk. "
            "Run `make elevation` to estimate grades from a free DEM."
        )
    if not audits:
        warnings.append("No field-audit data loaded; OSM values are the only source.")
    return GraphBundle(graph=graph, meta=meta, warnings=warnings, path=path)
