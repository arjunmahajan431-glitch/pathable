"""Packaged starting profiles and the parameter metadata the UI renders.

These are starting points, not medical advice or a promise of accessibility.
Every number is traceable in docs/STANDARDS.md, which distinguishes design
guidance from project assumptions.
"""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from pathable.models import Profile

WHEELCHAIR = Profile(
    name="wheelchair",
    label="Wheelchair",
    description=(
        "Stairs are excluded. Slope, roughness, width and crossing kerbs are priced "
        "strongly. Unknown data is priced by the risk setting rather than assumed safe."
    ),
    steps="block",
    respect_wheelchair_tag=True,
    soft_grade_up_pct=5.0,
    hard_grade_up_pct=8.33,
    soft_grade_down_pct=8.0,
    hard_grade_down_pct=12.0,
    grade_factor_up=0.25,
    grade_factor_down=0.15,
    hard_grade_action="block",
    # PROWAG R302.2 public-right-of-way reference; see docs/STANDARDS.md.
    min_width_m=1.22,
    surface_multipliers={"smooth": 1.0, "moderate": 1.35, "rough": 2.2, "very_rough": 4.0},
    kerb_raised_penalty_m=150.0,
    kerb_unknown_penalty_m=100.0,
    crossing_uncontrolled_penalty_m=20.0,
    crossing_unknown_penalty_m=10.0,
    unknown_surface_factor=0.06,
    unknown_smoothness_factor=0.06,
    unknown_width_factor=0.08,
    unknown_grade_factor=0.15,
    unknown_steps_factor=0.20,
    walking_speed_mps=0.8,
)

LIMITED_MOBILITY = Profile(
    name="limited_mobility",
    label="Limited mobility / cane / walker",
    description=(
        "Stairs are heavily penalized but not blocked by default (toggle them off if "
        "you cannot use them). Gentler slope thresholds than the wheelchair profile."
    ),
    steps="penalize",
    steps_penalty_m=600.0,
    soft_grade_up_pct=6.0,
    hard_grade_up_pct=12.0,
    soft_grade_down_pct=8.0,
    hard_grade_down_pct=15.0,
    grade_factor_up=0.18,
    grade_factor_down=0.12,
    hard_grade_action="penalize",
    hard_grade_penalty_m=300.0,
    min_width_m=1.22,
    surface_multipliers={"smooth": 1.0, "moderate": 1.2, "rough": 1.7, "very_rough": 2.5},
    kerb_raised_penalty_m=80.0,
    kerb_unknown_penalty_m=50.0,
    crossing_uncontrolled_penalty_m=35.0,
    crossing_unknown_penalty_m=15.0,
    avoid_unlit=True,
    walking_speed_mps=1.1,
)

PROFILE_REGISTRY: dict[str, Profile] = {
    WHEELCHAIR.name: WHEELCHAIR,
    LIMITED_MOBILITY.name: LIMITED_MOBILITY,
}


class UnknownProfileError(ValueError):
    pass


def _slope_conflict(value: dict[str, Any]) -> str | None:
    """Return a plain-language message when the soft limit exceeds the hard limit."""
    for direction, soft_key, hard_key in (
        ("uphill", "soft_grade_up_pct", "hard_grade_up_pct"),
        ("downhill", "soft_grade_down_pct", "hard_grade_down_pct"),
    ):
        soft = value.get(soft_key)
        hard = value.get(hard_key)
        if (
            isinstance(soft, (int, float))
            and not isinstance(soft, bool)
            and isinstance(hard, (int, float))
            and not isinstance(hard, bool)
            and soft > hard
        ):
            return (
                f"The {direction} slope settings conflict: extra effort starts at "
                f"{soft:g}%, but the steepest allowed slope is {hard:g}%. Lower the "
                "starting point or raise the steepest allowed slope."
            )
    return None


def resolve_profile(value: str | dict[str, Any] | Profile) -> Profile:
    """Resolve a profile name, a full custom parameter object, or a Profile."""
    if isinstance(value, Profile):
        return value
    if isinstance(value, str):
        try:
            return PROFILE_REGISTRY[value]
        except KeyError as exc:
            known = ", ".join(sorted(PROFILE_REGISTRY))
            raise UnknownProfileError(f"unknown profile {value!r}; choose one of: {known}") from exc
    if isinstance(value, dict):
        conflict = _slope_conflict(value)
        if conflict is not None:
            raise UnknownProfileError(conflict)
        try:
            return Profile.model_validate(value)
        except ValidationError as exc:
            first = exc.errors()[0]
            location = ".".join(str(part) for part in first.get("loc", ()))
            detail = str(first.get("msg", "invalid value")).removeprefix("Value error, ")
            if location:
                detail = f"{location}: {detail}"
            raise UnknownProfileError(f"invalid profile parameters: {detail}") from exc
    raise UnknownProfileError("profile must be a name or an object of parameters")


def public_profile(profile: Profile) -> dict[str, Any]:
    return profile.model_dump(mode="json")


# UI metadata. Ranges are guardrails, not claims about what is comfortable.
PARAMETER_SPECS: list[dict[str, Any]] = [
    {
        "key": "soft_grade_up_pct",
        "label": "Uphill slope starts costing extra at",
        "help": (
            "A 5% slope rises 5 cm for every 1 m forward. Below this setting, uphill "
            "adds no extra effort. It cannot be set higher than the steepest allowed "
            "uphill slope."
        ),
        "min": 0,
        "max": 20,
        "step": 0.5,
        "unit": "%",
        "kind": "number",
        "group": "Uphill and downhill",
    },
    {
        "key": "hard_grade_up_pct",
        "label": "Steepest uphill slope allowed",
        "help": (
            "8.3% is about 1 m of rise over 12 m forward. It is a common ramp design "
            "reference, not a universal sidewalk law. Routes above this are blocked or "
            "heavily penalized by your profile. It cannot be set lower than the point "
            "where extra uphill effort starts."
        ),
        "min": 1,
        "max": 25,
        "step": 0.5,
        "unit": "%",
        "kind": "number",
        "group": "Uphill and downhill",
    },
    {
        "key": "grade_factor_up",
        "label": "How quickly steep slopes add effort",
        "help": (
            "At 0.25, each 1% above the soft limit adds 25% to that segment's walking "
            "effort. At 0.5 it doubles. A higher number makes even gentle slopes matter."
        ),
        "min": 0,
        "max": 1,
        "step": 0.05,
        "unit": "× per %",
        "kind": "number",
        "group": "Uphill and downhill",
    },
    {
        "key": "surface_multipliers.very_rough",
        "label": "How much harder very rough ground feels",
        "help": (
            "A 4x setting means 100 m of very rough surface counts like 400 m of smooth "
            "pavement. This covers gravel, cobbles, sand, or mud."
        ),
        "min": 1,
        "max": 8,
        "step": 0.1,
        "unit": "×",
        "kind": "number",
        "group": "Surface quality",
    },
    {
        "key": "kerb_unknown_penalty_m",
        "label": "Extra effort for an unknown curb ramp",
        "help": (
            "Used when a crossing has no mapped curb or ramp. 100 m-eq feels like walking "
            "an extra 100 m on flat, smooth pavement."
        ),
        "min": 0,
        "max": 400,
        "step": 5,
        "unit": "m-eq",
        "kind": "number",
        "group": "Street crossings",
    },
    {
        "key": "crossing_uncontrolled_penalty_m",
        "label": "Extra effort for an uncontrolled crossing",
        "help": (
            "Used at crossings with no mapped signal or marked crosswalk. Higher values "
            "make the router prefer a safer crossing farther away."
        ),
        "min": 0,
        "max": 200,
        "step": 5,
        "unit": "m-eq",
        "kind": "number",
        "group": "Street crossings",
    },
    {
        "key": "min_width_m",
        "label": "Narrowest comfortable clear width",
        "help": (
            "1.22 m is roughly a wheelchair plus a little passing room. Segments mapped "
            "narrower than this cost more, but they are not blocked."
        ),
        "min": 0.6,
        "max": 2.0,
        "step": 0.05,
        "unit": "m",
        "kind": "number",
        "group": "Path width",
    },
    {
        "key": "unknown_grade_factor",
        "label": "Extra effort when slope is unknown",
        "help": (
            "Missing data is not treated as safe. This adds effort to segments with no "
            "slope value, and the risk setting multiplies it."
        ),
        "min": 0,
        "max": 1,
        "step": 0.05,
        "unit": "×",
        "kind": "number",
        "group": "Missing data",
    },
    {
        "key": "avoid_unlit",
        "label": "Prefer lit paths",
        "help": (
            "Adds effort to mapped unlit segments and to segments with unknown lighting. "
            "It never blocks a route."
        ),
        "min": None,
        "max": None,
        "step": None,
        "unit": "",
        "kind": "boolean",
        "group": "Lighting",
    },
    {
        "key": "walking_speed_mps",
        "label": "Walking speed for time estimates",
        "help": (
            "Only changes the time estimate. It does not change which route is chosen. "
            "0.8 m/s is a slow, cautious walking pace."
        ),
        "min": 0.3,
        "max": 2.0,
        "step": 0.05,
        "unit": "m/s",
        "kind": "number",
        "group": "Walking speed",
    },
]


def parameter_specs() -> list[dict[str, Any]]:
    return PARAMETER_SPECS


def apply_parameter(profile: Profile, key: str, value: Any) -> Profile:
    """Set a (possibly nested) parameter and re-validate the profile."""
    payload = profile.model_dump()
    if "." in key:
        head, tail = key.split(".", 1)
        nested = dict(payload.get(head) or {})
        nested[tail] = value
        payload[head] = nested
    else:
        payload[key] = value
    return Profile.model_validate(payload)
