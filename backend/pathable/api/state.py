"""In-process application state.

The graph is loaded once and kept in memory. The SQLite store is opened per
operation, which keeps it safe across FastAPI's worker threads.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import cast

import networkx as nx
from fastapi import Request

from pathable.config import AppConfig, AreaConfig
from pathable.geocode import NominatimClient
from pathable.graph.area import area_bbox, area_boundary_geojson
from pathable.graph.loader import load_area_graph
from pathable.graph.model import GraphMeta
from pathable.models import Point
from pathable.reports.store import ReportStore
from pathable.schemas import AreaOut


@dataclass
class AppState:
    config: AppConfig
    store: ReportStore
    geocoder: NominatimClient
    graph: nx.MultiDiGraph | None
    meta: GraphMeta | None
    load_warnings: list[str]
    graph_error: str | None
    field_audits: int
    started_at: datetime
    active_area_id: str = ""

    def __post_init__(self) -> None:
        if not self.active_area_id:
            self.active_area_id = self.config.active_area

    @property
    def area(self) -> AreaConfig:
        return next(area for area in self.config.areas if area.id == self.active_area_id)

    def area_by_id(self, area_id: str) -> AreaConfig | None:
        return next((area for area in self.config.areas if area.id == area_id), None)

    def area_out(self, area: AreaConfig | None = None) -> AreaOut:
        item = area or self.area
        boundary = area_boundary_geojson(item)
        bbox = list(area_bbox(item)) if boundary is not None else None
        return AreaOut(
            id=item.id,
            name=item.name,
            center=Point(lat=item.center.lat, lon=item.center.lon),
            radius_m=item.radius_m,
            is_placeholder=item.is_placeholder,
            note=item.note,
            boundary=boundary,
            bbox=bbox,
        )

    def areas_out(self) -> list[AreaOut]:
        return [self.area_out(area) for area in self.config.areas]

    def switch_area(self, area_id: str) -> AreaOut:
        """Load a different configured area into memory.

        The demo runs one active area at a time. Loading is blocking, which is
        fine for this single-user planning app; the frontend shows a status
        message while it happens.
        """
        target = self.area_by_id(area_id)
        if target is None:
            raise KeyError(area_id)
        bundle = load_area_graph(self.config, area=target, audits=self.store.audits())
        self.active_area_id = target.id
        self.graph = bundle.graph
        self.meta = bundle.meta
        self.load_warnings = bundle.warnings
        self.graph_error = None
        self.field_audits = len(self.store.audits())
        return self.area_out(target)

    def route_load_warnings(self) -> list[str]:
        """Drop the legacy demo warning; the pipeline derives it from meta."""
        return [w for w in self.load_warnings if not w.startswith("DEMO MODE")]


def get_state(request: Request) -> AppState:
    state = getattr(request.app.state, "pathable", None)
    if state is None:
        raise RuntimeError("application state was not initialized")
    return cast(AppState, state)


def now_utc() -> datetime:
    return datetime.now(UTC)
