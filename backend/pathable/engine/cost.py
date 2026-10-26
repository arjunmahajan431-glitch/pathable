"""Explainable generalized edge cost.

UNITS
-----
Every edge cost is in **meter-equivalents (m-eq)**. One m-eq is the effort of
moving one meter along an ideal path: flat, smooth, fully mapped, no barriers.
A 100 m-eq fixed penalty means "this feels as bad as walking an extra 100 m".

The formula for one directed edge is::

    cost = length_m * multiplier_1 * ... * multiplier_n + penalties

All multipliers are >= 1 and all penalties are >= 0, so cost >= length_m.
That invariant keeps the haversine A* heuristic admissible (see search.py).
Hard blocks are explicit flags, never infinities. A blocked edge still gets a
breakdown so the UI can explain *why* it fails the user's profile.

Order of application (also the order shown in the UI) is fixed:
access/steps/wheelchair blocks, steps, wheelchair tag, grade, roughness,
width, crossing/kerb, lighting, community reports.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from pathable.graph.model import EdgeFeatures
from pathable.models import CostBreakdown, CostTerm, HardBlock, Profile, Provenance, Risk

# Barriers that a wheelchair user cannot normally pass. This is an ASSUMPTION
# based on common OSM semantics; each is surfaced with its own reason.
IMPASSABLE_BARRIERS = {"stile", "turnstile", "kissing_gate", "block", "log", "debris"}
# Passable but potentially difficult barriers. ASSUMPTION, user-adjustable
# through the profile's barrier_penalty_m.
PASSABLE_BARRIERS = {
    "bollard",
    "gate",
    "lift_gate",
    "cycle_barrier",
    "chain",
    "swing_gate",
    "entrance",
    "cattle_grid",
}
RAISED_KERBS = {"raised", "yes", "damaged"}
LOWERED_KERBS = {"lowered", "flush", "no"}
UNCONTROLLED_CROSSINGS = {"uncontrolled", "unmarked", "no", "unknown"}
CONTROLLED_CROSSINGS = {"traffic_signals", "marked", "zebra", "pelican", "toucan", "pegasus"}


class _Running:
    """Apply multipliers and penalties in a recorded, additive order."""

    def __init__(self, length_m: float, *, record_terms: bool = True) -> None:
        self.length = length_m
        self.value = length_m
        self.record_terms = record_terms
        self.terms: list[CostTerm] = []

    def multiplier(self, name: str, value: float, reason: str, prov: Provenance) -> None:
        if value <= 1.0000001:
            return
        before = self.value
        self.value = before * value
        if not self.record_terms:
            return
        self.terms.append(
            CostTerm(
                name=name,
                kind="multiplier",
                value=round(value, 6),
                m_eq=round(self.value - before, 6),
                reason=reason,
                provenance=prov,
            )
        )

    def penalty(self, name: str, value: float, reason: str, prov: Provenance) -> None:
        if value <= 0:
            return
        self.value += value
        if not self.record_terms:
            return
        self.terms.append(
            CostTerm(
                name=name,
                kind="penalty",
                value=round(value, 6),
                m_eq=round(value, 6),
                reason=reason,
                provenance=prov,
            )
        )


def _grade_term(
    running: _Running,
    features: EdgeFeatures,
    profile: Profile,
    scale: float,
) -> HardBlock | None:
    grade = features.grade_pct
    prov = features.grade_prov
    if grade is None or prov is Provenance.UNKNOWN:
        running.multiplier(
            "unknown_grade",
            1.0 + profile.unknown_grade_factor * scale,
            (
                "Slope is not mapped and could not be estimated from elevation data; "
                f"priced as risk ({profile.unknown_grade_factor:.2f} × {scale:.2f} risk scale)."
            ),
            Provenance.UNKNOWN,
        )
        return None

    uphill = grade >= 0
    magnitude = abs(grade)
    soft = profile.soft_grade_up_pct if uphill else profile.soft_grade_down_pct
    hard = profile.hard_grade_up_pct if uphill else profile.hard_grade_down_pct
    factor = profile.grade_factor_up if uphill else profile.grade_factor_down
    direction = "uphill" if uphill else "downhill"
    dem = prov is Provenance.DEM_ESTIMATED

    if magnitude <= soft:
        return None

    if magnitude <= hard:
        multiplier = 1.0 + factor * (magnitude - soft)
        running.multiplier(
            "grade",
            multiplier,
            (
                f"{magnitude:.1f}% {direction} grade is above the "
                f"{soft:.1f}% soft threshold; penalty grows with steepness"
                + (" (estimated from coarse elevation data)" if dem else "")
            ),
            prov,
        )
        return None

    # Above the hard threshold. DEM-estimated grades never hard-block: 30 m
    # elevation data is not a measurement of the sidewalk. They get the
    # capped multiplier plus a reduced fixed penalty instead.
    capped = 1.0 + factor * (hard - soft)
    running.multiplier(
        "grade",
        capped,
        (
            f"{magnitude:.1f}% {direction} grade is above the profile's "
            f"{hard:.1f}% hard threshold; slope multiplier capped at the threshold"
        ),
        prov,
    )
    if profile.hard_grade_action == "block" and not dem:
        return HardBlock(
            reason=(
                f"{magnitude:.1f}% {direction} grade exceeds the profile's {hard:.1f}% hard limit"
            ),
            attribute="grade",
            provenance=prov,
        )
    penalty = profile.hard_grade_penalty_m * (profile.dem_confidence if dem else 1.0)
    running.penalty(
        "hard_grade",
        penalty,
        (
            f"{magnitude:.1f}% {direction} grade exceeds the profile's "
            f"{hard:.1f}% hard threshold; fixed penalty instead of a hard block"
            + (" because the grade is DEM-estimated" if dem else " (profile allows it)")
        ),
        prov,
    )
    return None


@dataclass(frozen=True)
class EdgeWeight:
    """Numeric result used by A*. No per-term objects, so search stays fast."""

    total_m_eq: float
    hard_block: HardBlock | None


def _compute_edge_cost(
    features: EdgeFeatures,
    profile: Profile,
    risk: Risk,
    *,
    community_penalty_m_eq: float = 0.0,
    community_report_ids: Sequence[int] | None = None,
    record_terms: bool = True,
) -> tuple[float, list[CostTerm], HardBlock | None]:
    """Shared cost engine. ``record_terms=False`` skips explanation objects."""
    length = max(0.0, features.length_m)
    running = _Running(length, record_terms=record_terms)
    scale = profile.risk_scale(risk)
    block: HardBlock | None = None

    # --- access and explicit barriers -------------------------------------
    if not features.access_ok:
        block = HardBlock(
            reason=features.access_reason or "pedestrian access is restricted",
            attribute="access",
            provenance=features.access_prov,
        )
    if features.barrier:
        if features.barrier in IMPASSABLE_BARRIERS:
            block = block or HardBlock(
                reason=f"mapped barrier={features.barrier} blocks wheeled passage",
                attribute="barrier",
                provenance=features.barrier_prov,
            )
        elif features.barrier in PASSABLE_BARRIERS or features.barrier_prov.is_known:
            running.penalty(
                "barrier",
                profile.barrier_penalty_m,
                f"mapped barrier={features.barrier} at the end of this segment",
                features.barrier_prov,
            )

    # --- steps -------------------------------------------------------------
    if features.is_steps:
        if profile.steps == "block":
            block = block or HardBlock(
                reason="mapped steps (highway=steps)",
                attribute="steps",
                provenance=features.steps_prov,
            )
        else:
            per_step = (features.step_count or 0) * profile.steps_per_step_penalty_m
            running.penalty(
                "steps",
                profile.steps_penalty_m + per_step,
                (
                    "mapped steps; profile penalizes but does not block them"
                    + (f" ({features.step_count} steps)" if features.step_count else "")
                ),
                features.steps_prov,
            )
    elif not features.steps_known:
        running.multiplier(
            "unknown_steps",
            1.0 + profile.unknown_steps_factor * scale,
            "It is not mapped whether this segment has steps; priced as a risk.",
            Provenance.UNKNOWN,
        )

    # --- OSM wheelchair tag ------------------------------------------------
    if profile.respect_wheelchair_tag and features.wheelchair == "no":
        block = block or HardBlock(
            reason="OSM wheelchair=no",
            attribute="wheelchair",
            provenance=features.wheelchair_prov,
        )
    elif features.wheelchair == "limited":
        running.penalty(
            "wheelchair_limited",
            profile.wheelchair_limited_penalty_m,
            "OSM wheelchair=limited",
            features.wheelchair_prov,
        )

    # --- grade -------------------------------------------------------------
    grade_block = _grade_term(running, features, profile, scale)
    block = block or grade_block

    # --- surface / smoothness ---------------------------------------------
    if features.roughness_class:
        multiplier = profile.surface_multipliers[features.roughness_class]
        running.multiplier(
            "surface",
            multiplier,
            (
                f"surface roughness class: {features.roughness_class}"
                + (f" ({features.roughness_note})" if features.roughness_note else "")
            ),
            features.roughness_prov,
        )
    if features.surface_prov is Provenance.UNKNOWN:
        running.multiplier(
            "unknown_surface",
            1.0 + profile.unknown_surface_factor * scale,
            "Surface type is not mapped; priced as a risk.",
            Provenance.UNKNOWN,
        )
    if features.smoothness_prov is Provenance.UNKNOWN:
        running.multiplier(
            "unknown_smoothness",
            1.0 + profile.unknown_smoothness_factor * scale,
            "Smoothness is not mapped; priced as a risk.",
            Provenance.UNKNOWN,
        )

    # --- width -------------------------------------------------------------
    if features.width_m is None:
        running.multiplier(
            "unknown_width",
            1.0 + profile.unknown_width_factor * scale,
            "Clear width is not mapped; priced as a risk.",
            Provenance.UNKNOWN,
        )
    elif features.width_m < profile.min_width_m:
        shortfall = (profile.min_width_m - features.width_m) / profile.min_width_m
        running.multiplier(
            "width",
            1.0 + profile.width_penalty_factor * shortfall,
            (
                f"mapped width {features.width_m:.2f} m is below the profile's "
                f"{profile.min_width_m:.2f} m minimum"
            ),
            features.width_prov,
        )

    # --- crossings and kerbs ----------------------------------------------
    if features.is_crossing:
        kerb = features.kerb
        if kerb in LOWERED_KERBS:
            pass
        elif kerb in RAISED_KERBS:
            running.penalty(
                "kerb",
                profile.kerb_raised_penalty_m,
                (
                    f"crossing ends at a {kerb} kerb"
                    if kerb != "damaged"
                    else "crossing ends at a damaged curb ramp (field audit)"
                ),
                features.kerb_prov,
            )
        else:
            running.penalty(
                "unknown_kerb",
                profile.kerb_unknown_penalty_m * scale,
                (
                    "crossing kerb condition is not mapped; priced as risk "
                    f"({profile.kerb_unknown_penalty_m:.0f} m-eq × {scale:.2f} risk scale)."
                ),
                Provenance.UNKNOWN,
            )

        crossing = features.crossing
        if crossing in UNCONTROLLED_CROSSINGS:
            running.penalty(
                "crossing_uncontrolled",
                profile.crossing_uncontrolled_penalty_m,
                f"crossing type is {crossing} (no signal control mapped)",
                features.crossing_prov,
            )
        elif crossing not in CONTROLLED_CROSSINGS:
            running.penalty(
                "unknown_crossing",
                profile.crossing_unknown_penalty_m * scale,
                "crossing control type is not mapped; priced as risk.",
                Provenance.UNKNOWN,
            )

    # --- lighting preference ------------------------------------------------
    if profile.avoid_unlit:
        if features.lit is False:
            running.penalty(
                "unlit",
                profile.lit_off_penalty_m,
                "OSM maps this segment as unlit",
                features.lit_prov,
            )
        elif features.lit is None:
            running.multiplier(
                "unknown_lit",
                1.0 + profile.unknown_lit_factor * scale,
                "Lighting is not mapped; priced as a risk.",
                Provenance.UNKNOWN,
            )

    # --- community reports --------------------------------------------------
    if community_penalty_m_eq > 0:
        ids = ", ".join(f"#{i}" for i in (community_report_ids or [])) or "nearby"
        running.penalty(
            "community_report",
            community_penalty_m_eq,
            (
                f"community reports {ids} near this segment (unverified reports "
                "count half; resolved/rejected reports do not count)"
            ),
            Provenance.COMMUNITY_REPORT,
        )

    return round(running.value, 6), running.terms, block


def compute_edge_cost(
    features: EdgeFeatures,
    profile: Profile,
    risk: Risk,
    *,
    community_penalty_m_eq: float = 0.0,
    community_report_ids: Sequence[int] | None = None,
) -> CostBreakdown:
    """Return the full, explainable cost of one directed edge."""
    total, terms, block = _compute_edge_cost(
        features,
        profile,
        risk,
        community_penalty_m_eq=community_penalty_m_eq,
        community_report_ids=community_report_ids,
    )
    return CostBreakdown(
        length_m=round(max(0.0, features.length_m), 3),
        base_m_eq=round(max(0.0, features.length_m), 3),
        terms=terms,
        total_m_eq=total,
        hard_block=block,
        profile=profile.name,
        risk=risk,
    )


def compute_edge_weight(
    features: EdgeFeatures,
    profile: Profile,
    risk: Risk,
    *,
    community_penalty_m_eq: float = 0.0,
) -> EdgeWeight:
    """Return only the number A* needs, skipping explanation objects.

    The search explores thousands of edges that never appear in the result.
    Building a full ``CostBreakdown`` for each one dominates request time on a
    citywide graph. This path runs the same arithmetic, so the chosen route is
    identical, and the final route still gets full explanations.
    """
    total, _, block = _compute_edge_cost(
        features,
        profile,
        risk,
        community_penalty_m_eq=community_penalty_m_eq,
        record_terms=False,
    )
    return EdgeWeight(total_m_eq=total, hard_block=block)
