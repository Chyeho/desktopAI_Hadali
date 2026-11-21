'''情绪标签解析与流式过滤

图引擎的输出约定：
    [emotion:happy]
    今天也想陪用户聊聊天呀。

- 标签只出现在开头，解析后从正文剥离；
- 非法/缺失回退 neutral（沿用 agent/expression_driver.py 的标签集合）；
- 流式场景下标签可能跨 token，EmotionStreamFilter 负责缓冲并剥离。
'''
import re

from agent.expression_driver import validate_emotion

# 开头情绪标签：[emotion:happy] / [emotion=happy]，允许前后空白
EMOTION_TAG_RE = re.compile(r"^\s*\[emotion\s*[:=]\s*([A-Za-z_]+)\s*\]\s*")
# 流式缓冲上限：超过仍未闭合的 '[' 视为普通文本，避免卡住输出
MAX_TAG_BUFFER = 64


def parse_emotion_tag(content: str) -> tuple[str, str]:
    '''解析开头情绪标签，返回 (emotion, 正文)'''
    if not content:
        return "neutral", ""
    match = EMOTION_TAG_RE.match(content)
    if not match:
        return "neutral", content
    return validate_emotion(match.group(1).lower()), content[match.end():]


class EmotionStreamFilter:
    '''流式情绪标签过滤器

    用法：
        filter_ = EmotionStreamFilter()
        for token in tokens:
            text = filter_.feed(token)
            if text:
                yield text
        tail = filter_.flush()

    只处理回复开头的标签；一旦确认不是标签，后续 token 原样透传。
    '''

    def __init__(self) -> None:
        self._buffer = ""
        self._started = False
        # 标签刚被剥离时，紧随其后的换行/空格不应展示给用户
        self._after_tag = False

    def feed(self, token: str) -> str:
        '''喂入一个 token，返回可立即展示的干净文本（可能为空串）'''
        if not token:
            return ""
        if self._started:
            if self._after_tag:
                token = token.lstrip(" \t\r\n")
                if not token:
                    return ""
                self._after_tag = False
            return token

        self._buffer += token
        stripped = self._buffer.lstrip()
        if not stripped:
            return ""

        if stripped.startswith("["):
            # 可能是尚未闭合的情绪标签，先缓冲
            if "]" not in stripped and len(self._buffer) < MAX_TAG_BUFFER:
                return ""
            match = EMOTION_TAG_RE.match(self._buffer)
            if match:
                self._started = True
                self._after_tag = True
                rest = self._buffer[match.end():]
                self._buffer = ""
                return rest
            # 以 '[' 开头但不是情绪标签 → 普通文本
            self._started = True
            text = self._buffer
            self._buffer = ""
            return text

        # 不是标签，直接透传
        self._started = True
        text = self._buffer
        self._buffer = ""
        return text

    def flush(self) -> str:
        '''结束流式输出，返回缓冲区剩余文本'''
        if self._started or not self._buffer:
            self._buffer = ""
            return ""
        text = self._buffer
        self._buffer = ""
        self._started = True
        return text
