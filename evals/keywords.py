'''评测关键词与正则集中定义，用例只引用常量'''
import re

# 游戏子图拒绝词：命中任一即视为给出了“暂不能玩”的人格化提示
GAME_REFUSAL_KEYWORDS = (
    "还在学",
    "学习中",
    "开发中",
    "暂时",
    "还不能",
    "等我",
    "以后",
)

# 工具失败时的人格化解释词
FAILURE_EXPLANATION_KEYWORDS = (
    "没找到",
    "没有找到",
    "没能",
    "好像",
    "不太",
    "要不再",
    "稍后",
    "暂时",
    "抱歉",
)

# 最终回复中不允许出现的裸露技术字样
FORBIDDEN_TECH_TERMS = (
    "Traceback",
    "FileNotFoundError",
    "Exception",
    "status_code",
    "Error:",
)

# state 层：用户消息时间前缀
TIME_STATE_RE = re.compile(r"^\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}\]")

# 回复尾部时间后缀
TIME_TAIL_RE = re.compile(r"\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}\]\s*$")

# UI 层：任意位置的时间标记（流式 token 与干净 reply 都不应出现）
TIME_MARKER_RE = re.compile(r"\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}\]")
