from __future__ import annotations

import pytest

from pathable.engine.profiles import UnknownProfileError, resolve_profile


def test_conflicting_uphill_slopes_explain_the_fix() -> None:
    with pytest.raises(UnknownProfileError) as excinfo:
        resolve_profile({"soft_grade_up_pct": 10.0, "hard_grade_up_pct": 8.33})

    message = str(excinfo.value)
    assert "uphill slope settings conflict" in message
    assert "10%" in message
    assert "8.33%" in message
    assert "errors.pydantic.dev" not in message


def test_conflicting_downhill_slopes_explain_the_fix() -> None:
    with pytest.raises(UnknownProfileError) as excinfo:
        resolve_profile({"soft_grade_down_pct": 14.0, "hard_grade_down_pct": 12.0})

    message = str(excinfo.value)
    assert "downhill slope settings conflict" in message
    assert "14%" in message
    assert "12%" in message


def test_valid_custom_profile_is_accepted() -> None:
    profile = resolve_profile(
        {"name": "custom", "soft_grade_up_pct": 6.0, "hard_grade_up_pct": 9.0}
    )

    assert profile.soft_grade_up_pct == 6.0
    assert profile.hard_grade_up_pct == 9.0
