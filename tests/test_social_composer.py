import pytest

from sports_clipper.social_composer import atempo_chain, build_social_edit_plan


def test_atempo_chain_supports_point_four_speed() -> None:
    assert atempo_chain(0.4) == "atempo=0.500000,atempo=0.800000"


def test_atempo_chain_rejects_extreme_speed() -> None:
    with pytest.raises(ValueError):
        atempo_chain(0.1)


def test_auto_plan_fills_twenty_seconds_from_ten_second_clip() -> None:
    plan = build_social_edit_plan(10.0, target_duration=20.0, slowmo_speed=0.4)

    assert plan.normal_start == pytest.approx(0.0)
    assert plan.normal_duration == pytest.approx(10.0)
    assert plan.replay_start == pytest.approx(6.0)
    assert plan.replay_output_duration == pytest.approx(10.0)
    assert plan.hold_duration == pytest.approx(0.0)
    assert plan.composed_duration == pytest.approx(20.0)


def test_long_source_preserves_the_ending() -> None:
    plan = build_social_edit_plan(20.0, target_duration=20.0, slowmo_speed=0.4)

    assert plan.normal_start == pytest.approx(3.0)
    assert plan.normal_end == pytest.approx(20.0)
    assert plan.replay_start == pytest.approx(18.8)
    assert plan.replay_end == pytest.approx(20.0)
    assert plan.composed_duration == pytest.approx(20.0)


def test_explicit_short_replay_adds_hold_when_needed() -> None:
    plan = build_social_edit_plan(
        10.0,
        target_duration=20.0,
        slowmo_speed=0.5,
        replay_source_seconds=2.0,
    )

    assert plan.replay_output_duration == pytest.approx(4.0)
    assert plan.hold_duration == pytest.approx(6.0)
    assert plan.composed_duration == pytest.approx(20.0)
