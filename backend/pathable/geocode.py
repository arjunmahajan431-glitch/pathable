"""Backend proxy for Nominatim address search.

Why a proxy instead of calling Nominatim from the browser?

* The public Nominatim policy asks apps to identify themselves and to cache.
  A browser cannot set a meaningful User-Agent, but the server can.
* It lets us enforce the 1 request/second limit globally.
* It keeps the endpoint swappable without a frontend release.

The frontend deliberately searches only when the user presses a button. The
policy forbids autocomplete against the public instance, so there is no
search-as-you-type request here.
"""

from __future__ import annotations

import math
import threading
import time
from collections import OrderedDict
from typing import Any

import httpx

from pathable.config import AppConfig
from pathable.schemas import GeocodeResult

ATTRIBUTION = "Search results © OpenStreetMap contributors, ODbL."


class GeocodeError(RuntimeError):
    pass


class NominatimClient:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self._lock = threading.Lock()
        self._last_request = 0.0
        self._cache: OrderedDict[tuple[str, str], list[GeocodeResult]] = OrderedDict()

    def _cached(self, key: tuple[str, str]) -> list[GeocodeResult] | None:
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
                return self._cache[key]
        return None

    def _store(self, key: tuple[str, str], results: list[GeocodeResult]) -> None:
        with self._lock:
            self._cache[key] = results
            self._cache.move_to_end(key)
            while len(self._cache) > self.config.geocoding.cache_size:
                self._cache.popitem(last=False)

    def search(
        self, query: str, *, center_lat: float, center_lon: float, radius_m: float
    ) -> tuple[list[GeocodeResult], bool]:
        if not self.config.geocoding.enabled:
            raise GeocodeError("Address search is disabled in this deployment.")
        span_lat = radius_m / 111_320.0
        span_lon = span_lat / max(0.2, abs(math.cos(math.radians(center_lat))))
        viewbox = (
            f"{center_lon - span_lon:.6f},{center_lat + span_lat:.6f},"
            f"{center_lon + span_lon:.6f},{center_lat - span_lat:.6f}"
        )
        key = (query.strip().lower(), viewbox)
        cached = self._cached(key)
        if cached is not None:
            return cached, True

        params: dict[str, Any] = {
            "format": "jsonv2",
            "q": query,
            "limit": 5,
            "bounded": 1,
            "viewbox": viewbox,
            "addressdetails": 0,
            "accept-language": "en",
        }
        headers = {
            "User-Agent": self.config.geocoding.user_agent,
            "Accept": "application/json",
        }
        try:
            # Serialize calls and respect the public 1 request/second rule.
            with (
                httpx.Client(timeout=self.config.geocoding.timeout_s) as client,
                self._lock,
            ):
                wait = self.config.geocoding.min_interval_s - (
                    time.monotonic() - self._last_request
                )
                if wait > 0:
                    time.sleep(wait)
                response = client.get(
                    self.config.geocoding.endpoint, params=params, headers=headers
                )
                self._last_request = time.monotonic()
        except httpx.HTTPError as exc:
            raise GeocodeError(f"Address search service is unavailable: {exc}") from exc

        if response.status_code != 200:
            raise GeocodeError(
                f"Address search service returned HTTP {response.status_code}. "
                "Please try again later."
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise GeocodeError("Address search returned an unreadable response.") from exc
        if not isinstance(payload, list):
            raise GeocodeError("Address search returned an unexpected response shape.")
        results: list[GeocodeResult] = []
        for item in payload[:5]:
            try:
                results.append(
                    GeocodeResult(
                        display_name=str(item["display_name"])[:300],
                        lat=float(item["lat"]),
                        lon=float(item["lon"]),
                        category=str(item.get("category", ""))[:60],
                    )
                )
            except (KeyError, TypeError, ValueError):
                continue
        self._store(key, results)
        return results, False
