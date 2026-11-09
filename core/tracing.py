'''回合指标：每轮对话结束后追加一行 JSON 到 logs/turns.jsonl

记录原则：不落用户对话全文，只保留长度与截断摘要；不记录任何密钥。
'''
import json
import os
import time

from agent.chat_agent import TurnResult
from utils.logger_handler import logger
from utils.path_tool import get_abs_path

TURNS_FILE = get_abs_path("logs/turns.jsonl")
# 用户输入摘要的最大字符数（超出以 … 结尾）
SUMMARY_MAX_LEN = 30


class TurnTracer:
    '''一轮对话的指标记录器：成功 / 失败各写一行 JSONL'''

    def __init__(self, turn_id: str, session_id: str, mode: str = "",
                 user_text: str = "", turns_file: str = None):
        self.turn_id = turn_id
        self.session_id = session_id
        self.mode = mode
        self.user_text = user_text or ""
        self.turns_file = turns_file or TURNS_FILE
        self.started_at = time.perf_counter()

    def finish_success(self, result: TurnResult) -> dict:
        '''记录成功回合，返回写入的字典（便于测试断言）'''
        record = self._base()
        record.update({
            "ok": True,
            "emotion": result.get("emotion", ""),
            "reply_len": len(result.get("reply", "")),
            "steps": result.get("steps", 0),
            "tool_calls": [
                {
                    "name": tc.get("name", ""),
                    "ok": tc.get("ok", False),
                    "duration_ms": tc.get("duration_ms", 0.0),
                }
                for tc in result.get("tool_calls", [])
            ],
        })
        self._append(record)
        return record

    def finish_error(self, code: str, message: str) -> dict:
        '''记录失败回合'''
        record = self._base()
        record.update({
            "ok": False,
            "error_code": code,
            "error_message": (message or "")[:200],
        })
        self._append(record)
        return record

    def _base(self) -> dict:
        return {
            "ts": int(time.time() * 1000),
            "turn_id": self.turn_id,
            "session_id": self.session_id,
            "mode": self.mode,
            "text_len": len(self.user_text),
            "text_summary": self._summary(),
            "latency_ms": round((time.perf_counter() - self.started_at) * 1000, 2),
        }

    def _summary(self) -> str:
        text = self.user_text.strip().replace("\n", " ")
        return text[:SUMMARY_MAX_LEN] + ("…" if len(text) > SUMMARY_MAX_LEN else "")

    def _append(self, record: dict) -> None:
        '''追加写入；指标写入失败不影响主流程'''
        try:
            os.makedirs(os.path.dirname(self.turns_file), exist_ok=True)
            with open(self.turns_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.warning(f"[TurnTracer]指标写入失败：{e}")
