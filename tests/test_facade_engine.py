"""单元测试：core/facade.py 引擎切换

覆盖：
- resolve_engine：显式参数 > AGENT_ENGINE > 默认 graph，非法值抛 ValueError
- create_agent：graph 返回 CompanionGraphAgent，legacy 返回 ChatAgent
- create_agent_from_env：从 .env 读取 AGENT_ENGINE
"""
import pytest
from langchain_core.messages import AIMessage

from backend.agent.chat_agent import ChatAgent
from backend.agent.graph.runner import CompanionGraphAgent
from backend.core import facade


class _FakeLLM:
    """最小模型桩：ChatAgent 初始化时需 bind_tools"""

    def bind_tools(self, tools, **kwargs):
        return self

    def invoke(self, messages):
        return AIMessage(content="好")


class _FakeFactory:
    """模型工厂桩：记录连接参数与生成参数"""

    instances: list = []

    def __init__(self, api_key, base_url, model):
        self.api_key = api_key
        self.base_url = base_url
        self.model = model
        self.gen_params = None
        _FakeFactory.instances.append(self)

    def generator(self, **params):
        self.gen_params = params
        return _FakeLLM()


@pytest.fixture(autouse=True)
def _clear_factory_instances():
    _FakeFactory.instances.clear()
    yield
    _FakeFactory.instances.clear()


class TestResolveEngine:
    """引擎名解析"""

    def test_default_is_graph(self, monkeypatch):
        monkeypatch.delenv("AGENT_ENGINE", raising=False)
        assert facade.resolve_engine() == "graph"

    def test_env_override(self, monkeypatch):
        monkeypatch.setenv("AGENT_ENGINE", "legacy")
        assert facade.resolve_engine() == "legacy"

    def test_explicit_beats_env(self, monkeypatch):
        monkeypatch.setenv("AGENT_ENGINE", "legacy")
        assert facade.resolve_engine("graph") == "graph"

    def test_case_insensitive(self, monkeypatch):
        monkeypatch.delenv("AGENT_ENGINE", raising=False)
        assert facade.resolve_engine(" LEGACY ") == "legacy"

    def test_invalid_raises(self, monkeypatch):
        monkeypatch.delenv("AGENT_ENGINE", raising=False)
        with pytest.raises(ValueError, match="AGENT_ENGINE"):
            facade.resolve_engine("nope")


class TestCreateAgent:
    """按引擎构造 agent"""

    def test_graph_engine_returns_companion_agent(self, monkeypatch, tmp_path):
        monkeypatch.delenv("AGENT_ENGINE", raising=False)
        agent = facade.create_agent(
            api_key="sk-test",
            factory_cls=_FakeFactory,
            history_file=str(tmp_path / "history.json"),
            engine="graph",
        )
        assert isinstance(agent, CompanionGraphAgent)
        assert agent.mode_config["name"] == "emotion"
        # 沿用情感陪伴模式的生成参数
        assert _FakeFactory.instances[-1].gen_params is not None

    def test_legacy_engine_returns_chat_agent(self, monkeypatch, tmp_path):
        monkeypatch.delenv("AGENT_ENGINE", raising=False)
        agent = facade.create_agent(
            api_key="sk-test",
            factory_cls=_FakeFactory,
            history_file=str(tmp_path / "history.json"),
            engine="legacy",
        )
        assert isinstance(agent, ChatAgent)
        assert agent.mode_config["name"] == "emotion"

    def test_env_selects_legacy(self, monkeypatch, tmp_path):
        monkeypatch.setenv("AGENT_ENGINE", "legacy")
        agent = facade.create_agent(
            api_key="sk-test",
            factory_cls=_FakeFactory,
            history_file=str(tmp_path / "history.json"),
        )
        assert isinstance(agent, ChatAgent)


class TestCreateAgentFromEnv:
    """从 .env 读取连接参数与引擎"""

    def test_env_file_selects_engine(self, monkeypatch, tmp_path):
        monkeypatch.delenv("AGENT_ENGINE", raising=False)
        env_file = tmp_path / ".env"
        env_file.write_text(
            "API_KEY=sk-env\n"
            "BASE_URL=http://localhost\n"
            "MODEL=custom\n"
            "AGENT_ENGINE=legacy\n",
            encoding="utf-8",
        )
        agent = facade.create_agent_from_env(
            env_path=str(env_file),
            factory_cls=_FakeFactory,
            history_file=str(tmp_path / "history.json"),
        )
        assert isinstance(agent, ChatAgent)
        factory = _FakeFactory.instances[-1]
        assert (factory.api_key, factory.base_url, factory.model) == (
            "sk-env", "http://localhost", "custom"
        )

    def test_missing_api_key_raises(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("MODEL=custom\n", encoding="utf-8")
        with pytest.raises(ValueError, match="API_KEY"):
            facade.create_agent_from_env(
                env_path=str(env_file),
                factory_cls=_FakeFactory,
                history_file=str(tmp_path / "history.json"),
            )
