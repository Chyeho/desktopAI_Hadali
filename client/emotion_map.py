'''情感驱动（client 表现层）：根据情感标签驱动 live2d 形象播放对应动作

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

本模块只依赖 Live2DWidget 的信号，不 import Qt，也不 import agent；
情感标签的合法性校验由 core 层（agent/expression_driver.py）负责。
'''
from utils.logger_handler import logger

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
    logger.info(f"[emotion_map]触发表情：{emotion}")

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
        logger.warning(f"[emotion_map]表情驱动失败：{e}")
