"""单元测试：Live2D 行为纯函数（client/live2d_behavior.py）

覆盖坐标归一化/还原、平滑插值、随机动作组选择（避免连续重复）。
"""
import random

import pytest

from client.live2d_behavior import (
    RANDOM_INTERVAL_MAX,
    RANDOM_INTERVAL_MIN,
    STATE_EMOTION_PLAYING,
    STATE_EMOTION_RETURNING,
    STATE_IDLE,
    STATE_RANDOM_PLAYING,
    clamp,
    denormalize_cursor,
    next_state_on_motion_end,
    normalize_cursor,
    pick_random_group,
    random_interval_seconds,
    smooth_toward,
)


class TestNormalizeCursor:
    """normalize_cursor：部件坐标 → [-1, 1] 归一化坐标"""

    def test_center_maps_to_origin(self):
        assert normalize_cursor(200, 250, 400, 500) == pytest.approx((0.0, 0.0))

    def test_corners_map_to_limits(self):
        assert normalize_cursor(0, 0, 400, 500) == pytest.approx((-1.0, -1.0))
        assert normalize_cursor(400, 500, 400, 500) == pytest.approx((1.0, 1.0))

    def test_outside_cursor_is_clamped(self):
        nx, ny = normalize_cursor(-1000, 1000, 400, 500)
        assert (nx, ny) == pytest.approx((-1.0, 1.0))

    def test_zero_size_returns_center(self):
        assert normalize_cursor(10, 10, 0, 0) == (0.0, 0.0)
        assert normalize_cursor(10, 10, 400, -1) == (0.0, 0.0)


class TestDenormalizeCursor:
    """denormalize_cursor：[-1, 1] → 部件像素坐标"""

    def test_origin_maps_to_center(self):
        assert denormalize_cursor(0.0, 0.0, 400, 500) == pytest.approx((200.0, 250.0))

    def test_limits_map_to_corners(self):
        assert denormalize_cursor(-1.0, 1.0, 400, 500) == pytest.approx((0.0, 500.0))

    def test_roundtrip_with_normalize(self):
        nx, ny = normalize_cursor(120, 380, 400, 500)
        px, py = denormalize_cursor(nx, ny, 400, 500)
        assert (px, py) == pytest.approx((120.0, 380.0))

    def test_zero_size_returns_origin(self):
        assert denormalize_cursor(0.5, 0.5, 0, 0) == (0.0, 0.0)


class TestSmoothToward:
    """smooth_toward：指数平滑"""

    def test_factor_one_reaches_target(self):
        assert smooth_toward(0.0, 1.0, 1.0) == pytest.approx(1.0)

    def test_factor_zero_stays(self):
        assert smooth_toward(0.3, 1.0, 0.0) == pytest.approx(0.3)

    def test_converges_to_target(self):
        value = 0.0
        for _ in range(60):
            value = smooth_toward(value, 1.0, 0.2)
        assert value == pytest.approx(1.0, abs=1e-3)

    def test_factor_is_clamped(self):
        assert smooth_toward(0.0, 1.0, 5.0) == pytest.approx(1.0)
        assert smooth_toward(0.0, 1.0, -1.0) == pytest.approx(0.0)


class TestClamp:
    """clamp：区间限幅"""

    def test_within_range_unchanged(self):
        assert clamp(0.4) == pytest.approx(0.4)

    def test_out_of_range_clamped(self):
        assert clamp(3.0) == pytest.approx(1.0)
        assert clamp(-3.0) == pytest.approx(-1.0)
        assert clamp(5.0, 0.0, 2.0) == pytest.approx(2.0)


class TestPickRandomGroup:
    """pick_random_group：随机动作组选择"""

    def test_empty_groups_returns_none(self):
        assert pick_random_group([]) is None

    def test_exclude_avoids_previous_group(self):
        groups = ["Idle", "Flick", "Tap"]
        rng = random.Random(42)
        for _ in range(20):
            assert pick_random_group(groups, rng, exclude="Idle") != "Idle"

    def test_returns_excluded_when_only_candidate(self):
        assert pick_random_group(["Idle"], exclude="Idle") == "Idle"

    def test_selection_is_reproducible_with_seeded_rng(self):
        groups = ["Idle", "Flick", "FlickDown", "Tap"]
        a = pick_random_group(groups, random.Random(7), exclude="Idle")
        b = pick_random_group(groups, random.Random(7), exclude="Idle")
        assert a == b

    def test_exclude_accepts_unknown_group(self):
        groups = ["Idle", "Tap"]
        assert pick_random_group(groups, random.Random(1), exclude="Nonexistent") in groups


class TestRandomIntervalSeconds:
    """random_interval_seconds：随机动作间隔"""

    def test_default_range_is_8_to_15_seconds(self):
        assert (RANDOM_INTERVAL_MIN, RANDOM_INTERVAL_MAX) == (8.0, 15.0)

    def test_value_within_default_range(self):
        rng = random.Random(2026)
        for _ in range(50):
            interval = random_interval_seconds(rng)
            assert RANDOM_INTERVAL_MIN <= interval <= RANDOM_INTERVAL_MAX

    def test_custom_range_is_respected(self):
        rng = random.Random(3)
        for _ in range(20):
            assert 1.0 <= random_interval_seconds(rng, 1.0, 2.0) <= 2.0

    def test_reversed_range_is_swapped(self):
        rng = random.Random(5)
        assert 2.0 <= random_interval_seconds(rng, 3.0, 2.0) <= 3.0

    def test_reproducible_with_seeded_rng(self):
        assert random_interval_seconds(random.Random(9)) == random_interval_seconds(random.Random(9))


class TestNextStateOnMotionEnd:
    """next_state_on_motion_end：动作结束时的状态迁移"""

    def test_emotion_playing_goes_to_returning(self):
        assert next_state_on_motion_end(STATE_EMOTION_PLAYING) == STATE_EMOTION_RETURNING

    def test_random_playing_goes_to_idle(self):
        assert next_state_on_motion_end(STATE_RANDOM_PLAYING) == STATE_IDLE

    def test_idle_stays_idle(self):
        assert next_state_on_motion_end(STATE_IDLE) == STATE_IDLE

    def test_returning_stays_returning(self):
        assert next_state_on_motion_end(STATE_EMOTION_RETURNING) == STATE_EMOTION_RETURNING
