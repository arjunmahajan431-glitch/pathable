"""Length-weighted data coverage for a route.

Coverage answers one narrow question: for each attribute the active profile
uses, what fraction of the route's length has a known value? A value estimated
from a DEM counts as known (it has provenance) but is labeled separately in the
UI. Coverage says nothing about safety or accessibility; docs/COVERAGE.md
states this explicitly.
"""

from __future__ import annotations

from collections.abc import Iterable

from pathable.graph.model import EdgeFeatures
from pathable.models import Profile, Provenance
from pathable.schemas import AttributeCoverage, CoverageOut

ATTRIBUTE_LABELS = {
    "steps": "Steps",
    "surface": "Surface type",
    "smoothness": "Smoothness",
    "width": "Clear width",
    "grade": "Slope",
    "kerb": "Crossing kerb",
    "lit": "Lighting",
}

COVERAGE_NOTE = (
    "Coverage counts how much of the route has a mapped value, not how good the route is. "
    "A known value can still describe a barrier, and an unknown value is neither safe nor "
    "blocked. DEM-estimated grades count as known and are labeled DEM_ESTIMATED."
)


def _provenance(features: EdgeFeatures, attribute: str) -> Provenance:
    if attribute == "steps":
        return features.steps_prov
    if attribute == "surface":
        return features.surface_prov
    if attribute == "smoothness":
        return features.smoothness_prov
    if attribute == "width":
        return features.width_prov
    if attribute == "grade":
        return features.grade_prov
    if attribute == "kerb":
        return features.kerb_prov
    if attribute == "lit":
        return features.lit_prov
    raise KeyError(attribute)


def compute_coverage(edges: Iterable[EdgeFeatures], profile: Profile) -> CoverageOut:
    """Compute per-attribute coverage and their unweighted mean."""
    edge_list = list(edges)
    relevant = ["steps", "surface", "smoothness", "width", "grade"]
    if profile.avoid_unlit:
        relevant.append("lit")
    has_crossings = any(e.is_crossing for e in edge_list)
    if has_crossings:
        relevant.append("kerb")

    attributes: dict[str, AttributeCoverage] = {}
    coverages: list[float] = []
    for attribute in relevant:
        total = 0.0
        known = 0.0
        for edge in edge_list:
            if attribute == "kerb" and not edge.is_crossing:
                continue
            total += edge.length_m
            if _provenance(edge, attribute) is not Provenance.UNKNOWN:
                known += edge.length_m
        raw_coverage = known / total if total > 0 else None
        note = ""
        if attribute == "kerb":
            note = "Only crossing segments are in this denominator."
        if raw_coverage is not None:
            coverages.append(raw_coverage)
        attributes[attribute] = AttributeCoverage(
            label=ATTRIBUTE_LABELS[attribute],
            known_length_m=round(known, 2),
            total_length_m=round(total, 2),
            coverage=round(raw_coverage, 6) if raw_coverage is not None else None,
            note=note,
        )

    overall = round(sum(coverages) / len(coverages), 6) if coverages else None
    return CoverageOut(attributes=attributes, overall=overall, note=COVERAGE_NOTE)
