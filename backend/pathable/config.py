"""Application configuration.

The YAML file in ``config/areas.yaml`` is the single source of truth for the
mapping areas and for service limits. Environment variables override only the
things that differ between machines (demo mode, cache location, admin secret).
Secrets are deliberately *not* part of this model: the admin token is read from
``PATHABLE_ADMIN_TOKEN`` at request time.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config" / "areas.yaml"


class Center(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


class AreaConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,63}$")
    name: str
    center: Center
    # The radius is a generous bounding circle used for address search and as
    # a fallback area check. When a city boundary is supplied, the boundary is
    # the real limit and the radius only needs to cover the whole city.
    radius_m: float = Field(gt=0, le=12_000)
    is_placeholder: bool = False
    note: str = ""
    # Optional city boundary GeoJSON. It lets the app cover a whole city
    # without pretending that a circle is the city limit.
    boundary: str | None = None
    # Optional per-area committed sample, so switching areas never shows a
    # graph from a different city. Live graphs still use data/cache.
    sample_graph: str | None = None
    sample_elevation: str | None = None

    @property
    def boundary_path(self) -> Path | None:
        if not self.boundary:
            return None
        path = Path(self.boundary)
        return path if path.is_absolute() else PROJECT_ROOT / path


class DataConfig(BaseModel):
    cache_dir: str = "data/cache"
    sample_graph: str
    sample_elevation: str
    sample_graph_date: str
    sample_graph_source: str
    sample_elevation_source: str


class RoutingConfig(BaseModel):
    max_snap_m: float = Field(default=300.0, gt=0, le=1000)
    snap_warning_m: float = Field(default=50.0, ge=0)
    max_alternatives: int = Field(default=3, ge=1, le=5)


class ReportsConfig(BaseModel):
    influence_radius_m: float = Field(default=40.0, gt=0, le=500)
    expiry_days: int = Field(default=180, ge=1, le=3650)
    rate_limit_per_hour: int = Field(default=5, ge=1, le=100)
    max_bbox_span_deg: float = Field(default=0.05, gt=0, le=1)
    max_description_chars: int = Field(default=500, ge=1, le=2000)
    database: str = "data/cache/pathable.db"


class GeocodingConfig(BaseModel):
    enabled: bool = True
    user_agent: str
    min_interval_s: float = Field(default=1.0, ge=1.0)
    cache_size: int = Field(default=200, ge=1)
    timeout_s: float = Field(default=15.0, gt=0, le=60)
    endpoint: str


class ElevationConfig(BaseModel):
    provider: Literal["opentopodata_srtm30m"] = "opentopodata_srtm30m"
    endpoint: str
    batch_size: int = Field(default=100, ge=1, le=100)
    min_interval_s: float = Field(default=1.0, ge=1.0)
    timeout_s: float = Field(default=30.0, gt=0, le=120)
    user_agent: str


class ServerConfig(BaseModel):
    allowed_origins: list[str] = Field(default_factory=list)


class AppConfig(BaseModel):
    """Validated view of ``config/areas.yaml``."""

    model_config = ConfigDict(extra="forbid")

    active_area: str
    max_radius_m: float = Field(default=12_000, gt=0, le=12_000)
    areas: list[AreaConfig] = Field(min_length=1)
    data: DataConfig
    routing: RoutingConfig = RoutingConfig()
    reports: ReportsConfig = ReportsConfig()
    geocoding: GeocodingConfig
    elevation: ElevationConfig
    server: ServerConfig = ServerConfig()

    @model_validator(mode="after")
    def _check_active_area(self) -> AppConfig:
        matches = [a for a in self.areas if a.id == self.active_area]
        if not matches:
            raise ValueError(f"active_area {self.active_area!r} is not in areas[]")
        area = matches[0]
        if area.radius_m > self.max_radius_m:
            raise ValueError(
                f"area {area.id!r} radius {area.radius_m} exceeds max_radius_m {self.max_radius_m}"
            )
        return self

    @property
    def area(self) -> AreaConfig:
        return next(a for a in self.areas if a.id == self.active_area)

    def path(self, relative: str) -> Path:
        """Resolve a config path relative to the project root."""
        p = Path(relative)
        return p if p.is_absolute() else PROJECT_ROOT / p

    @property
    def cache_dir(self) -> Path:
        return self.path(self.data.cache_dir)

    @property
    def database_path(self) -> Path:
        override = os.environ.get("PATHABLE_DATABASE", "").strip()
        if override:
            return Path(override)
        return self.path(self.reports.database)

    @property
    def sample_graph_path(self) -> Path:
        return self.path(self.data.sample_graph)

    @property
    def sample_elevation_path(self) -> Path:
        return self.path(self.data.sample_elevation)

    @property
    def demo_forced(self) -> bool:
        return os.environ.get("PATHABLE_DEMO", "").strip().lower() in {"1", "true", "yes"}

    @property
    def cors_origins(self) -> list[str]:
        raw = os.environ.get("PATHABLE_ALLOWED_ORIGINS", "").strip()
        if raw:
            return [origin.strip() for origin in raw.split(",") if origin.strip()]
        return self.server.allowed_origins


def load_config(path: str | os.PathLike[str] | None = None) -> AppConfig:
    """Load and validate the YAML config. Raises a readable error on bad input."""
    config_path = Path(path or os.environ.get("PATHABLE_CONFIG") or DEFAULT_CONFIG_PATH)
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    with config_path.open(encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    if not isinstance(raw, dict):
        raise ValueError(f"Config file {config_path} must contain a YAML mapping")
    return AppConfig.model_validate(raw)
