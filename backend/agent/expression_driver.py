'''情感标签校验（core 层）

core 只负责校验大模型输出的情感标签是否合法；
"情感 → live2d 动作组" 的映射与实际播放属于表现层，位于 client/emotion_map.py。
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


def validate_emotion(emotion: str) -> str:
    '''校验情感标签，非法标签回退为 neutral'''
    if emotion not in VALID_EMOTIONS:
        logger.warning(f"[expression_driver]收到未知情感标签：{emotion}，回退为 neutral")
        return "neutral"
    return emotion
