"""Tests for tag parsing logic."""
from __future__ import annotations

import math

import pytest

from localbooru.tags import TagRecord, parse_prompt


def _record_map(records: list[TagRecord]) -> dict[str, TagRecord]:
    return {rec.norm: rec for rec in records}


def test_parse_prompt_basic_tag() -> None:
    records = parse_prompt("cute", "prompt")
    by_norm = _record_map(records)
    assert "cute" in by_norm
    rec = by_norm["cute"]
    assert rec.tag == "cute"
    assert rec.kind == "prompt"
    assert rec.emphasis == "normal"
    assert math.isclose(rec.weight, 1.0)


@pytest.mark.parametrize(
    "token,expected_weight",
    [("{cute}", 1.1), ("{{cute}}", 1.1**2), ("[[cute]]", 0.9**2)],
)
def test_parse_prompt_brace_intensity(token: str, expected_weight: float) -> None:
    records = parse_prompt(token, "prompt")
    rec = _record_map(records)["cute"]
    assert rec.tag == "cute"
    assert rec.emphasis in {"strong", "weak"}
    assert math.isclose(rec.weight, expected_weight, rel_tol=1e-6)


def test_parse_prompt_grouped_tags_share_intensity() -> None:
    records = parse_prompt("{{cute, blonde hair, blue eyes}}", "prompt")
    by_norm = _record_map(records)
    assert set(by_norm) == {"cute", "blonde_hair", "blue_eyes"}
    for rec in by_norm.values():
        assert rec.emphasis == "strong"
        assert math.isclose(rec.weight, 1.1**2, rel_tol=1e-6)


def test_parse_prompt_weighted_number_and_missing_number() -> None:
    records = parse_prompt("1.5::dramatic lighting::, ::cinematic::", "prompt")
    by_norm = _record_map(records)
    dramatic = by_norm["dramatic_lighting"]
    assert dramatic.emphasis == "weighted"
    assert math.isclose(dramatic.weight, 1.5, rel_tol=1e-6)

    cinematic = by_norm["cinematic"]
    assert cinematic.emphasis == "weighted"
    assert math.isclose(cinematic.weight, 1.0, rel_tol=1e-6)


def test_parse_prompt_mixed_wrappers_expand_inner_tokens() -> None:
    records = parse_prompt("[{1.2::intense gaze::, {{soft lighting}}}]", "prompt")
    by_norm = _record_map(records)

    intense = by_norm["intense_gaze"]
    assert intense.emphasis == "weighted"
    assert intense.weight == pytest.approx(1.2 * 1.1 * 0.9)

    soft = by_norm["soft_lighting"]
    assert soft.emphasis == "strong"
    assert soft.weight == pytest.approx((1.1**3) * 0.9)


def test_parse_prompt_whitespace_wrappers_and_groups() -> None:
    text = "  {{  cute   ,   blue eyes   }} , [[ serene  ]] , { { floating hair } }  "
    records = parse_prompt(text, "prompt")
    by_norm = _record_map(records)

    assert set(by_norm) == {"cute", "blue_eyes", "serene", "floating_hair"}

    assert by_norm["cute"].weight == pytest.approx(1.1**2)
    assert by_norm["blue_eyes"].weight == pytest.approx(1.1**2)
    assert by_norm["serene"].weight == pytest.approx(0.9**2)
    assert by_norm["floating_hair"].weight == pytest.approx(1.1**2)


def test_parse_prompt_weighted_tokens_with_spaces() -> None:
    text = " :: cinematic  :: ,  +1.5 :: dramatic pose :: , -0.5:: moody lighting :: "
    records = parse_prompt(text, "prompt")
    by_norm = _record_map(records)

    assert by_norm["cinematic"].emphasis == "weighted"
    assert by_norm["cinematic"].weight == pytest.approx(1.0)

    assert by_norm["dramatic_pose"].weight == pytest.approx(1.5)
    assert by_norm["moody_lighting"].weight == pytest.approx(-0.5)


def test_parse_prompt_unmatched_curly_group_applies_weight() -> None:
    records = parse_prompt("{cute, fun", "prompt")
    by_norm = _record_map(records)
    assert set(by_norm) == {"cute", "fun"}
    for rec in by_norm.values():
        assert rec.emphasis == "strong"
        assert rec.weight == pytest.approx(1.1)


def test_parse_prompt_unmatched_square_brace_softens() -> None:
    records = parse_prompt("[ relaxed atmosphere", "prompt")
    rec = _record_map(records)["relaxed_atmosphere"]
    assert rec.emphasis == "weak"
    assert rec.weight == pytest.approx(0.9)


def test_parse_prompt_weighted_with_unmatched_braces() -> None:
    records = parse_prompt("{{1.4::dramatic flair::", "prompt")
    rec = _record_map(records)["dramatic_flair"]
    assert rec.emphasis == "weighted"
    assert rec.weight == pytest.approx((1.1**2) * 1.4)


def test_parse_prompt_weighted_with_unmatched_square_braces() -> None:
    records = parse_prompt("[[::ethereal glow::", "prompt")
    rec = _record_map(records)["ethereal_glow"]
    assert rec.emphasis == "weighted"
    assert rec.weight == pytest.approx(0.9**2)


def test_parse_prompt_trailing_closing_braces_removed() -> None:
    records = parse_prompt("dramatic focus}}", "prompt")
    rec = _record_map(records)["dramatic_focus"]
    assert rec.emphasis == "normal"
    assert rec.weight == pytest.approx(1.0)


def test_parse_prompt_weighted_missing_closing_delimiter() -> None:
    records = parse_prompt(":: cinematic vibes", "prompt")
    rec = _record_map(records)["cinematic_vibes"]
    assert rec.emphasis == "weighted"
    assert rec.weight == pytest.approx(1.0)


def test_parse_prompt_weighted_numeric_missing_closing() -> None:
    records = parse_prompt("1.8::dramatic pose", "prompt")
    rec = _record_map(records)["dramatic_pose"]
    assert rec.emphasis == "weighted"
    assert rec.weight == pytest.approx(1.8)


def test_parse_prompt_nested_braces_with_open_weight() -> None:
    records = parse_prompt("{{1.2::soft glow", "prompt")
    rec = _record_map(records)["soft_glow"]
    assert rec.emphasis == "weighted"
    assert rec.weight == pytest.approx((1.1**2) * 1.2)
