'''情感识别驱动：根据大模型回复中的情感标签，驱动 live2d 形象做出对应表情

当前 live2d 表情资源尚未制作，本模块先以空桩形式落地（仅记录日志）；
待表情资源就绪后，在 drive_expression 内按 emotion 调用 live2d 模型的
表情/动作接口即可（见函数内 TODO）。
'''
from utils.logger_handler import logger

# 支持的情感标签集合（与系统提示词中约定保持一致）
VALID_EMOTIONS = {
    "happy",      # 开心
    "sad",        # 难过
    "angry",      # 生气
    "surprised",  # 惊讶
    "neutral",    # 平静
    "shy",        # 害羞
    "worried",    # 担心
    "excited",    # 兴奋
    "thinking",   # 思考
}


def drive_expression(emotion: str, live2d_model=None) -> None:
    '''根据情感标签驱动 live2d 形象表情

    参数：
        emotion     : 大模型输出的情感标签
        live2d_model: live2d 模型对象（来自 Live2DWidget.model）；
                      为空（如纯命令行测试）时仅记录日志
    '''
    if emotion not in VALID_EMOTIONS:
        logger.warning(f"[expression_driver]收到未知情感标签：{emotion}，回退为 neutral")
        emotion = "neutral"

    logger.info(f"[expression_driver]触发表情：{emotion}")

    if live2d_model is None:
        return

    # TODO: live2d 表情资源就绪后，在此按 emotion 调用 live2d 模型接口，例如：
    #   try:
    #       live2d_model.SetExpression(emotion)          # 切换表情
    #       live2d_model.StartMotion("TapBody", ...)     # 或播放对应动作
    #   except Exception as e:
    #       logger.warning(f"[expression_driver]表情驱动失败：{e}")
