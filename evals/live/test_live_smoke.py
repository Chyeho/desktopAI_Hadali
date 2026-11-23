'''E3 实时冒烟：真实模型 + 真实工具，只断言结构不断言措辞

启用条件（同时满足）：
    RUN_LIVE_EVALS=1
    .env 中存在非空 API_KEY

运行：
    RUN_LIVE_EVALS=1 uv run pytest evals/live -m live -q
'''
import os
import uuid

import pytest

from backend.agent.expression_driver import VALID_EMOTIONS
from backend.core.facade import create_agent_from_env
from evals.keywords import TIME_MARKER_RE
from utils.env_utils import load_env
from utils.path_tool import get_abs_path

pytestmark = pytest.mark.live

LIVE_CASES = [
    {
        "id": "live_chat_01",
        "category": "live",
        "description": "闲聊：回复非空、无情绪标签/时间标记泄漏、情绪合法",
        "input": "今天有点累，陪我聊两句吧",
    },
    {
        "id": "live_time_02",
        "category": "live",
        "description": "时间：回复非空且不残留 [YYYY-MM-DD HH:MM] 标记",
        "input": "现在几点了？",
    },
    {
        "id": "live_tool_03",
        "category": "live",
        "description": "工具：真实模型自行决定是否调用天气工具，仅断言结构",
        "input": "北京今天天气怎么样？",
    },
]


@pytest.fixture(scope="module")
def live_agent():
    '''真实模型 Agent；未启用或无 API Key 时跳过整组用例'''
    if os.getenv("RUN_LIVE_EVALS") != "1":
        pytest.skip("未设置 RUN_LIVE_EVALS=1，跳过实时冒烟")

    env_path = get_abs_path(".env")
    if not os.path.exists(env_path):
        pytest.skip("未找到 .env，跳过实时冒烟")
    if not load_env(env_path, missing_ok=True).get("API_KEY"):
        pytest.skip("未配置 API_KEY，跳过实时冒烟")

    # history_file=None：冒烟不写 chat_history/
    return create_agent_from_env(env_path=env_path)


@pytest.mark.parametrize("case", LIVE_CASES, ids=[case["id"] for case in LIVE_CASES])
def test_live_smoke(case, live_agent):
    result = live_agent.chat(case["input"], session_id=f"live-{uuid.uuid4().hex}")
    reply = result["reply"]

    assert reply.strip(), f"回复为空：case={case['id']}"
    assert not TIME_MARKER_RE.search(reply), f"回复残留时间标记：{reply!r}"
    assert "[emotion" not in reply, f"回复残留情绪标签：{reply!r}"
    assert result["emotion"] in VALID_EMOTIONS, f"非法情绪：{result['emotion']!r}"
