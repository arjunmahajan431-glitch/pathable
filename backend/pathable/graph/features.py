"""Normalize raw OSM tags into :class:`EdgeFeatures`.

Normalization rules for list-valued tags (OSMnx simplification can merge ways
and turn a tag into a list):

* If every value is identical, use it.
* ``highway``: if any merged value is ``steps``, the edge is treated as steps.
  This is the conservative choice.
* ``surface`` / ``smoothness``: map every value to a roughness class and use
  the roughest class. This is also the conservative choice.
* ``width``: parse every value and keep the narrowest.
* ``incline``: if values disagree about direction, the grade sign is UNKNOWN
  (a DEM may fill it later); if numerical values disagree, grade is UNKNOWN.
* Other categorical tags: if distinct values conflict, the value is UNKNOWN.
  We do not pick the first list element and pretend it is authoritative.

OSM's ``incline`` tag is relative to the way direction. OSMnx writes
``reversed=True`` on the edge that runs against the way direction, so the sign
is flipped for those edges. If ``reversed`` is itself ambiguous (mixed list),
the sign becomes UNKNOWN.
"""

from __future__ import annotations

import math
import re
from collections.abc import Iterable
from typing import Any

from pathable.graph.model import ROUGHNESS_CLASSES, EdgeFeatures, NodeFeatures
from pathable.models import Provenance

# --- roughness mapping -------------------------------------------------------
# These tables map OSM values to the four roughness classes used by the cost
# model. They are design choices, documented in docs/COST_MODEL.md.
SURFACE_CLASS: dict[str, str] = {
    "asphalt": "smooth",
    "concrete": "smooth",
    "concrete:plates": "smooth",
    "concrete:lanes": "smooth",
    "paved": "smooth",
    "paving_stones": "moderate",
    "sett": "moderate",
    "brick": "moderate",
    "bricks": "moderate",
    "tiles": "moderate",
    "wood": "moderate",
    "compacted": "moderate",
    "stone": "moderate",
    "cobblestone": "rough",
    "gravel": "rough",
    "fine_gravel": "rough",
    "unpaved": "rough",
    "ground": "rough",
    "dirt": "rough",
    "earth": "rough",
    "grass": "rough",
    "grass_paver": "rough",
    "pebblestone": "rough",
    "sand": "very_rough",
    "mud": "very_rough",
    "rock": "very_rough",
    "snow": "very_rough",
    "ice": "very_rough",
}

SMOOTHNESS_CLASS: dict[str, str] = {
    "excellent": "smooth",
    "good": "smooth",
    "intermediate": "moderate",
    "bad": "rough",
    "very_bad": "very_rough",
    "horrible": "very_rough",
    "impassable": "very_rough",
}

_FEET_INCH_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)'\s*(?:(\d+(?:\.\d+)?)\")?\s*$")
_LENGTH_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*(m|meter|metre|cm|ft|feet|in|inch|inches)?\s*$")
_INCLINE_PCT_RE = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*%\s*$")
_INCLINE_DEG_RE = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*°\s*$")


def as_values(raw: Any) -> list[str]:
    """Flatten an OSM tag (scalar, list or tuple) into a list of strings."""
    if raw is None:
        return []
    if isinstance(raw, (list, tuple, set)):
        out: list[str] = []
        for item in raw:
            out.extend(as_values(item))
        return out
    text = str(raw).strip()
    return [text] if text else []


def single_value(raw: Any) -> tuple[str | None, bool]:
    """Return (value, conflict). Conflict means the merged tags disagree."""
    values = sorted({v for v in as_values(raw)})
    if not values:
        return None, False
    if len(values) == 1:
        return values[0], False
    return None, True


def display_value(raw: Any) -> str | None:
    values = sorted({v for v in as_values(raw)})
    if not values:
        return None
    return values[0] if len(values) == 1 else "|".join(values)


def parse_width_m(raw: Any) -> tuple[float | None, str]:
    """Parse common OSM width formats into meters. Returns (value, note)."""
    parsed: list[float] = []
    notes: list[str] = []
    for text in as_values(raw):
        value: float | None = None
        feet_inch = _FEET_INCH_RE.match(text)
        if feet_inch:
            feet = float(feet_inch.group(1))
            inches = float(feet_inch.group(2) or 0)
            value = feet * 0.3048 + inches * 0.0254
        else:
            length = _LENGTH_RE.match(text)
            if length:
                magnitude = float(length.group(1))
                unit = (length.group(2) or "m").lower()
                if unit == "cm":
                    value = magnitude / 100.0
                elif unit in {"ft", "feet"}:
                    value = magnitude * 0.3048
                elif unit in {"in", "inch", "inches"}:
                    value = magnitude * 0.0254
                else:
                    value = magnitude
        if value is None:
            notes.append(f"unparsed width {text!r}")
        else:
            parsed.append(value)
    if not parsed:
        return None, "; ".join(notes)
    if len(set(round(v, 4) for v in parsed)) > 1:
        notes.append("merged width values disagree; narrowest kept")
    return min(parsed), "; ".join(notes)


def parse_incline(
    raw: Any, reversed_raw: Any
) -> tuple[float | None, int | None, float | None, str]:
    """Parse incline and direction.

    Returns (signed_grade_pct_or_None, sign_or_None, magnitude_pct_or_None, note).
    A sign alone is kept because it is useful information even when steepness
    is not mapped; the cost model still treats the grade as UNKNOWN.
    """
    candidates: list[tuple[int | None, float | None]] = []
    notes: list[str] = []
    for text in as_values(raw):
        lowered = text.strip().lower()
        if lowered in {"up", "uphill", "ascend", "incline_up"}:
            candidates.append((1, None))
        elif lowered in {"down", "downhill", "descend", "incline_down"}:
            candidates.append((-1, None))
        elif lowered in {"level", "flat"}:
            candidates.append((0, 0.0))
        else:
            pct = _INCLINE_PCT_RE.match(lowered)
            deg = _INCLINE_DEG_RE.match(lowered)
            if pct:
                signed = float(pct.group(1))
                magnitude_value = abs(signed)
                candidates.append(
                    (0 if magnitude_value == 0 else (1 if signed > 0 else -1), magnitude_value)
                )
            elif deg:
                magnitude_value = abs(math.tan(math.radians(float(deg.group(1)))) * 100.0)
                sign_value = 1 if float(deg.group(1)) > 0 else -1
                candidates.append((0 if magnitude_value == 0 else sign_value, magnitude_value))
            elif re.fullmatch(r"-?\d+(?:\.\d+)?", lowered):
                signed = float(lowered)
                magnitude_value = abs(signed)
                candidates.append(
                    (0 if magnitude_value == 0 else (1 if signed > 0 else -1), magnitude_value)
                )
            else:
                notes.append(f"unrecognized incline {text!r}")

    if not candidates:
        return None, None, None, "; ".join(notes)

    signs = {sign for sign, _ in candidates if sign is not None}
    magnitudes = {round(mag, 4) for _, mag in candidates if mag is not None}
    sign_conflict = len(signs) > 1
    magnitude_conflict = len(magnitudes) > 1
    consensus_sign: int | None = next(iter(signs)) if len(signs) == 1 else None
    consensus_magnitude: float | None = next(iter(magnitudes)) if len(magnitudes) == 1 else None
    if sign_conflict:
        notes.append("merged incline values disagree on direction")
    elif magnitude_conflict:
        notes.append("merged incline values disagree on steepness")
        consensus_magnitude = None

    reversed_values = {v.lower() for v in as_values(reversed_raw)}
    if reversed_values == {"true"}:
        flip: bool | None = True
    elif not reversed_values or reversed_values == {"false"}:
        flip = False
    else:
        flip = None
        notes.append("ambiguous reversed flag; incline direction unknown")

    if flip is None:
        consensus_sign = None
    elif flip and consensus_sign is not None:
        consensus_sign = -consensus_sign

    if consensus_sign is not None and consensus_magnitude is not None:
        return (
            consensus_sign * consensus_magnitude,
            consensus_sign,
            consensus_magnitude,
            "; ".join(notes),
        )
    if consensus_sign is not None:
        notes.append("direction mapped but steepness not mapped")
    return None, consensus_sign, consensus_magnitude, "; ".join(notes)


def classify_roughness(surface_raw: Any, smoothness_raw: Any) -> tuple[str | None, Provenance, str]:
    """Map surface/smoothness tags to one roughness class (worst wins)."""
    notes: list[str] = []
    classes: list[str] = []
    for text in as_values(surface_raw):
        cls = SURFACE_CLASS.get(text.lower())
        if cls is None:
            notes.append(f"unrecognized surface {text!r}")
        else:
            classes.append(cls)
    for text in as_values(smoothness_raw):
        cls = SMOOTHNESS_CLASS.get(text.lower())
        if cls is None:
            notes.append(f"unrecognized smoothness {text!r}")
        else:
            classes.append(cls)
    if not classes:
        return None, Provenance.UNKNOWN, "; ".join(notes)
    worst = max(classes, key=ROUGHNESS_CLASSES.index)
    if len(set(classes)) > 1:
        notes.append(f"roughness classes differ; worst ({worst}) used")
    return worst, Provenance.OSM_MAPPED, "; ".join(notes)


def _known_or_unknown(
    raw: Any, recognized: set[str], provenance: Provenance
) -> tuple[str | None, Provenance]:
    value, conflict = single_value(raw)
    if value is None:
        return None, Provenance.UNKNOWN
    if conflict or value.lower() not in recognized:
        return None, Provenance.UNKNOWN
    return value.lower(), provenance


def normalize_node(raw: dict[str, Any]) -> NodeFeatures:
    """Normalize node lat/lon and the few accessibility tags we use."""
    kerb, _ = single_value(raw.get("kerb"))
    tactile, _ = single_value(raw.get("tactile_paving"))
    barrier, _ = single_value(raw.get("barrier"))
    wheelchair, _ = single_value(raw.get("wheelchair"))

    kerb_value = kerb.lower() if kerb else None
    if kerb_value not in {"lowered", "flush", "raised", "yes", "no"}:
        kerb_value = kerb_value if kerb_value else None

    return NodeFeatures(
        lat=float(raw["y"]),
        lon=float(raw["x"]),
        kerb=kerb_value,
        kerb_prov=Provenance.OSM_MAPPED if kerb_value else Provenance.UNKNOWN,
        tactile_paving=tactile.lower() if tactile else None,
        tactile_prov=Provenance.OSM_MAPPED if tactile else Provenance.UNKNOWN,
        barrier=barrier.lower() if barrier else None,
        barrier_prov=Provenance.OSM_MAPPED if barrier else Provenance.UNKNOWN,
        wheelchair=wheelchair.lower() if wheelchair else None,
        wheelchair_prov=Provenance.OSM_MAPPED if wheelchair else Provenance.UNKNOWN,
    )


def _access(raw: dict[str, Any]) -> tuple[bool, str, Provenance]:
    """Resolve pedestrian access, letting ``foot`` override ``access``."""
    restricted = {"no", "private", "customers", "agricultural", "forestry", "military"}
    allowed = {"yes", "designated", "permissive", "destination", "official", "public"}
    for key in ("foot", "access"):
        value, conflict = single_value(raw.get(key))
        if value is None:
            continue
        lowered = value.lower()
        if lowered in restricted:
            return False, f"{key}={lowered} maps no public pedestrian access", Provenance.OSM_MAPPED
        if lowered in allowed:
            return True, f"{key}={lowered}", Provenance.OSM_MAPPED
        if conflict:
            return False, f"{key} has conflicting values; treated as restricted", Provenance.UNKNOWN
    # The graph was requested with network_type="walk", so inclusion in the
    # network is itself evidence of pedestrian use, even when access tags are
    # absent. This is documented in docs/DECISIONS.md.
    return (
        True,
        "included in the pedestrian network; no prohibiting access tag",
        Provenance.OSM_MAPPED,
    )


def build_edge_features(
    raw: dict[str, Any],
    length_m: float,
    u_node: NodeFeatures,
    v_node: NodeFeatures,
    coords: Iterable[tuple[float, float]],
) -> EdgeFeatures:
    """Convert one raw OSMnx edge into the router-facing feature object."""
    notes: list[str] = []
    highway, highway_conflict = single_value(raw.get("highway"))
    if highway_conflict:
        notes.append("merged highway values disagree")
    highway_values = {v.lower() for v in as_values(raw.get("highway"))}
    steps_known = bool(highway_values)
    is_steps = "steps" in highway_values or single_value(raw.get("steps"))[0] == "yes"
    step_count_raw, _ = single_value(raw.get("step_count"))
    step_count = None
    if step_count_raw and re.fullmatch(r"\d+", step_count_raw):
        step_count = int(step_count_raw)

    footway, _ = single_value(raw.get("footway"))
    crossing = display_value(raw.get("crossing"))
    crossing_values = {v.lower() for v in as_values(raw.get("crossing"))}
    is_crossing = (footway or "").lower() == "crossing" or bool(crossing_values)
    if is_crossing and not crossing_values:
        notes.append("crossing mapped without a crossing type")

    surface_display = display_value(raw.get("surface"))
    smoothness_display = display_value(raw.get("smoothness"))
    roughness, roughness_prov, roughness_note = classify_roughness(
        raw.get("surface"), raw.get("smoothness")
    )
    if roughness_note:
        notes.append(roughness_note)

    surface_prov = (
        Provenance.OSM_MAPPED
        if any(v.lower() in SURFACE_CLASS for v in as_values(raw.get("surface")))
        else Provenance.UNKNOWN
    )
    smoothness_prov = (
        Provenance.OSM_MAPPED
        if any(v.lower() in SMOOTHNESS_CLASS for v in as_values(raw.get("smoothness")))
        else Provenance.UNKNOWN
    )

    width_m, width_note = parse_width_m(raw.get("width"))
    if width_note:
        notes.append(width_note)

    grade, incline_sign, incline_magnitude, incline_note = parse_incline(
        raw.get("incline"), raw.get("reversed")
    )
    if incline_note:
        notes.append(incline_note)

    lit_value, _ = single_value(raw.get("lit"))
    lit = {"yes": True, "no": False}.get((lit_value or "").lower())

    wheelchair, _ = single_value(raw.get("wheelchair"))
    wheelchair_value = wheelchair.lower() if wheelchair else None

    access_ok, access_reason, access_prov = _access(raw)

    barrier = v_node.barrier
    barrier_prov = v_node.barrier_prov
    if barrier == "kerb":
        # A kerb-marking node is not an obstruction; kerbs are handled at
        # crossings. Do not charge it as a bollard/gate.
        barrier, barrier_prov = None, Provenance.UNKNOWN

    return EdgeFeatures(
        length_m=round(float(length_m), 3),
        highway="steps" if is_steps else highway,
        footway=footway.lower() if footway else None,
        street_name=single_value(raw.get("name"))[0],
        surface=surface_display,
        surface_prov=surface_prov,
        smoothness=smoothness_display,
        smoothness_prov=smoothness_prov,
        roughness_class=roughness,
        roughness_prov=roughness_prov,
        roughness_note=roughness_note,
        width_m=round(width_m, 3) if width_m is not None else None,
        width_prov=Provenance.OSM_MAPPED if width_m is not None else Provenance.UNKNOWN,
        width_note=width_note,
        grade_pct=round(grade, 3) if grade is not None else None,
        grade_prov=Provenance.OSM_MAPPED if grade is not None else Provenance.UNKNOWN,
        incline_sign=incline_sign,
        incline_magnitude_pct=incline_magnitude,
        incline_raw=display_value(raw.get("incline")),
        steps_known=steps_known,
        is_steps=is_steps,
        step_count=step_count,
        steps_prov=Provenance.OSM_MAPPED if steps_known else Provenance.UNKNOWN,
        wheelchair=wheelchair_value,
        wheelchair_prov=Provenance.OSM_MAPPED if wheelchair_value else Provenance.UNKNOWN,
        access_ok=access_ok,
        access_reason=access_reason,
        access_prov=access_prov,
        lit=lit,
        lit_prov=Provenance.OSM_MAPPED if lit is not None else Provenance.UNKNOWN,
        crossing=crossing.lower() if crossing else None,
        crossing_prov=Provenance.OSM_MAPPED if crossing else Provenance.UNKNOWN,
        is_crossing=is_crossing,
        kerb=v_node.kerb,
        kerb_prov=v_node.kerb_prov,
        tactile_paving=v_node.tactile_paving,
        tactile_prov=v_node.tactile_prov,
        barrier=barrier,
        barrier_prov=barrier_prov,
        reversed_raw=display_value(raw.get("reversed")),
        coords=tuple(coords),
        osm={
            "highway": highway or "",
            "surface": surface_display or "",
            "smoothness": smoothness_display or "",
            "width": display_value(raw.get("width")) or "",
            "incline": display_value(raw.get("incline")) or "",
            "kerb": v_node.kerb or "",
            "tactile_paving": v_node.tactile_paving or "",
            "crossing": crossing or "",
        },
        notes=notes,
    )


# SRTM 30 m data is quantized to whole meters and has substantial vertical
# error. We refuse to invent a grade for very short edges or where the
# implied grade is implausible for an urban pedestrian path. Those edges stay
# UNKNOWN and are priced as risk instead.
MIN_DEM_EDGE_LENGTH_M = 20.0
MAX_ABS_DEM_GRADE_PCT = 20.0


def apply_elevation(
    features: EdgeFeatures, start_elev_m: float | None, end_elev_m: float | None
) -> None:
    """Fill an unknown grade from DEM node elevations, when reliable enough.

    Mapped grades are never overwritten by DEM values. Estimated grades are
    marked DEM_ESTIMATED and are treated with lower confidence by the cost
    model (they cannot hard-block). Short edges and implausible values stay
    UNKNOWN; we do not clamp them into looking like measurements.
    """
    if features.grade_pct is not None:
        return
    if start_elev_m is None or end_elev_m is None or features.length_m <= 0:
        return
    if features.length_m < MIN_DEM_EDGE_LENGTH_M:
        features.notes.append(
            "DEM grade not used: edge is shorter than the ~30 m elevation resolution"
        )
        return
    grade = (end_elev_m - start_elev_m) / features.length_m * 100.0
    if abs(grade) > MAX_ABS_DEM_GRADE_PCT:
        features.notes.append(
            f"DEM grade not used: implied {grade:.0f}% slope is implausible at this resolution"
        )
        return
    features.grade_pct = round(grade, 3)
    features.grade_prov = Provenance.DEM_ESTIMATED
    features.notes.append("grade estimated from 30 m elevation data, not measured on the sidewalk")


def apply_audit(features: EdgeFeatures, audit: dict[str, Any]) -> None:
    """Overlay a field-audit record (highest provenance tier).

    Both values are retained on the feature (``osm_*``) so the evaluation
    harness can compare OSM with what was measured in the field.
    """
    features.audit = {str(k): str(v) for k, v in audit.items() if v not in (None, "")}
    if "osm_grade_pct" not in features.audit:
        features.osm_grade_pct = features.grade_pct
    if "osm_width_m" not in features.audit:
        features.osm_width_m = features.width_m
    if "osm_kerb" not in features.audit:
        features.osm_kerb = features.kerb

    curb = str(audit.get("curb_ramp") or "").strip().lower()
    if curb in {"yes", "lowered", "flush", "good"}:
        features.kerb = "lowered"
        features.kerb_prov = Provenance.FIELD_AUDIT
    elif curb in {"no", "raised", "missing"}:
        features.kerb = "raised"
        features.kerb_prov = Provenance.FIELD_AUDIT
    elif curb in {"damaged", "broken"}:
        features.kerb = "damaged"
        features.kerb_prov = Provenance.FIELD_AUDIT

    slope = audit.get("measured_slope_pct")
    if slope not in (None, ""):
        try:
            features.grade_pct = float(slope)
            features.grade_prov = Provenance.FIELD_AUDIT
        except (TypeError, ValueError):
            features.notes.append(f"ignored unparseable audit slope {slope!r}")

    width = audit.get("clear_width_m")
    if width not in (None, ""):
        try:
            features.width_m = float(width)
            features.width_prov = Provenance.FIELD_AUDIT
        except (TypeError, ValueError):
            features.notes.append(f"ignored unparseable audit width {width!r}")

    obstacle = str(audit.get("obstacle") or "").strip()
    if obstacle:
        features.barrier = obstacle
        features.barrier_prov = Provenance.FIELD_AUDIT
