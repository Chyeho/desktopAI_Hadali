"""单元测试：情感标签校验（agent/expression_driver.py）与情感驱动（client/emotion_map.py）

覆盖情感标签校验、动作映射、drive_expression 的分支逻辑。
"""
from unittest.mock import MagicMock

from backend.agent.expression_driver import VALID_EMOTIONS
from client.emotion_map import EMOTION_MOTION_MAP, drive_expression


class TestValidEmotions:
    """VALID_EMOTIONS：支持的情感标签集合"""

    def test_contains_all_expected_emotions(self):
        expected = {
            "happy", "sad", "angry", "surprised", "neutral", "shy",
            "worried", "excited", "thinking", "relaxed",
        }
        assert expected <= VALID_EMOTIONS

    def test_has_ten_emotions(self):
        assert len(VALID_EMOTIONS) == 10


class TestEmotionMotionMap:
    """EMOTION_MOTION_MAP：情感标签 → 动作组映射"""

    def test_thinking_maps_to_idle(self):
        assert EMOTION_MOTION_MAP["thinking"] == "Idle"

    def test_relaxed_maps_to_flick(self):
        assert EMOTION_MOTION_MAP["relaxed"] == "Flick"

    def test_shy_maps_to_flickdown(self):
        assert EMOTION_MOTION_MAP["shy"] == "FlickDown"

    def test_surprised_maps_to_tap(self):
        assert EMOTION_MOTION_MAP["surprised"] == "Tap"

    def test_angry_maps_to_tap_body(self):
        assert EMOTION_MOTION_MAP["angry"] == "Tap@Body"

    def test_sad_maps_to_flick_body(self):
        assert EMOTION_MOTION_MAP["sad"] == "Flick@Body"

    def test_mapped_emotions_subset_of_valid(self):
        """所有映射中的 key 都应是合法情感标签"""
        for emotion in EMOTION_MOTION_MAP:
            assert emotion in VALID_EMOTIONS

    def test_unmapped_emotions_have_no_motion(self):
        """happy/neutral/worried/excited 无对应动作"""
        for emotion in ("happy", "neutral", "worried", "excited"):
            assert emotion not in EMOTION_MOTION_MAP


class TestDriveExpression:
    """drive_expression：根据情感标签驱动 live2d 表情"""

    def test_none_widget_does_not_raise(self):
        """无 live2d_widget 时仅记录日志，不应抛异常"""
        drive_expression("happy", live2d_widget=None)
        drive_expression("sad", live2d_widget=None)

    def test_unknown_emotion_falls_back_to_neutral(self):
        """未知情感标签回退为 neutral，不抛异常"""
        widget = MagicMock()
        drive_expression("unknown_emotion", live2d_widget=widget)
        # neutral 无对应动作 → 不应 emit
        widget.request_play_motion.emit.assert_not_called()

    def test_mapped_emotion_emits_signal(self):
        """有对应动作的情感应 emit 信号"""
        widget = MagicMock()
        drive_expression("shy", live2d_widget=widget)
        widget.request_play_motion.emit.assert_called_once_with("FlickDown")

    def test_unmapped_valid_emotion_no_emit(self):
        """合法但无对应动作的情感不应 emit（保持常态）"""
        widget = MagicMock()
        drive_expression("happy", live2d_widget=widget)
        widget.request_play_motion.emit.assert_not_called()

    def test_neutral_no_emit(self):
        widget = MagicMock()
        drive_expression("neutral", live2d_widget=widget)
        widget.request_play_motion.emit.assert_not_called()

    def test_all_mapped_emotions_emit_correct_group(self):
        cases = {
            "thinking": "Idle",
            "relaxed": "Flick",
            "shy": "FlickDown",
            "surprised": "Tap",
            "angry": "Tap@Body",
            "sad": "Flick@Body",
        }
        for emotion, expected_group in cases.items():
            widget = MagicMock()
            drive_expression(emotion, live2d_widget=widget)
            widget.request_play_motion.emit.assert_called_once_with(expected_group)
