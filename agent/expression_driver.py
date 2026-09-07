'''情感识别驱动：根据大模型回复中的情感标签，驱动 live2d 形象播放对应表情动画

表情资源为 hiyori 模型自带的动作组，映射如下（无对应动作的情感保持常态）：
    thinking  → Idle        了解并思考
    relaxed   → Flick       悠闲/摇头晃脑
    shy       → FlickDown   害羞
    surprised → Tap          惊讶
    angry     → Tap@Body    生气
    sad       → Flick@Body  难过
    happy / neutral / worried / excited：无对应动作，保持常态（自动呼吸/眨眼）

每个动作播放结束后，Live2DWidget 会自动把参数平滑过渡回常态（smoothstep 缓动），
避免动作一结束就跳变回中性参数，过渡更自然。

跨线程：driver 可能在 AIWorker 子线程被调用，通过 widget 的 request_play_motion
信号（QueuedConnection）把动作播放请求转发到主线程执行，避免子线程操作 OpenGL。
'''
from utils.logger_handler import logger

# 支持的情感标签集合（与系统提示词中约定保持一致）
VALID_EMOTIONS = {
    "happy",      # 开心（暂无对应动作，保持常态）
    "sad",        # 难过（Flick@Body）
    "angry",      # 生气（Tap@Body）
    "surprised",  # 惊讶（Tap）
    "neutral",    # 平静（保持常态）
    "shy",        # 害羞（FlickDown）
    "worried",    # 担心（暂无对应动作，占位）
    "excited",    # 兴奋（暂无对应动作，占位）
    "thinking",   # 思考（Idle）
    "relaxed",    # 放松（Flick）
}

# 情感标签 → hiyori 动作组映射（未列出者表示无对应动作，保持常态）
EMOTION_MOTION_MAP = {
    "thinking": "Idle",
    "relaxed": "Flick",
    "shy": "FlickDown",
    "surprised": "Tap",
    "angry": "Tap@Body",
    "sad": "Flick@Body",
}


def drive_expression(emotion: str, live2d_widget=None) -> None:
    '''根据情感标签驱动 live2d 形象表情动画

    参数：
        emotion        : 大模型输出的情感标签
        live2d_widget  : Live2DWidget 实例（提供 request_play_motion 信号，
                         跨线程安全地请求主线程播放动作）；为空（如纯命令行测试）时仅记录日志
    '''
    if emotion not in VALID_EMOTIONS:
        logger.warning(f"[expression_driver]收到未知情感标签：{emotion}，回退为 neutral")
        emotion = "neutral"

    logger.info(f"[expression_driver]触发表情：{emotion}")

    if live2d_widget is None:
        return

    group = EMOTION_MOTION_MAP.get(emotion)
    if group is None:
        # 无对应动作：保持常态（自动呼吸/眨眼），无需播放
        return

    try:
        # 通过信号跨线程请求主线程播放动作（避免子线程操作 OpenGL）
        live2d_widget.request_play_motion.emit(group)
    except Exception as e:
        logger.warning(f"[expression_driver]表情驱动失败：{e}")
