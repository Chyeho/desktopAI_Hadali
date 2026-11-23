"""单元测试：core/facade.py 单引擎门面

覆盖：
- create_agent：固定构造 CompanionGraphAgent，并使用图生成参数
- create_agent_from_env：从 .env 读取 API_KEY / BASE_URL / MODEL
- chat：未初始化 agent 时报错
"""
import pytest
from langchain_core.messages import AIMessage

from backend.agent.graph.runner import CompanionGraphAgent
from backend.core import facade


class _FakeLLM:
    """最小模型桩：主图初始化时需 bind_tools"""

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


class TestCreateAgent:
    """构造陪伴主图 agent"""

    def test_returns_companion_agent(self, tmp_path):
        agent = facade.create_agent(
            api_key="sk-test",
            factory_cls=_FakeFactory,
            history_file=str(tmp_path / "history.json"),
        )
        assert isinstance(agent, CompanionGraphAgent)
        assert agent.mode_config["name"] == "emotion"

    def test_uses_graph_model_params(self, tmp_path):
        facade.create_agent(
            api_key="sk-test",
            factory_cls=_FakeFactory,
            history_file=str(tmp_path / "history.json"),
        )
        factory = _FakeFactory.instances[-1]
        assert factory.gen_params is not None
        assert factory.gen_params.get("temperature") is not None


class TestCreateAgentFromEnv:
    """从 .env 读取连接参数"""

    def test_reads_connection_params(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text(
            "API_KEY=sk-env\n"
            "BASE_URL=http://localhost\n"
            "MODEL=custom\n",
            encoding="utf-8",
        )
        agent = facade.create_agent_from_env(
            env_path=str(env_file),
            factory_cls=_FakeFactory,
            history_file=str(tmp_path / "history.json"),
        )
        assert isinstance(agent, CompanionGraphAgent)
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


class TestChat:
    """chat：未初始化 agent 保护"""

    def test_none_agent_raises(self):
        with pytest.raises(RuntimeError, match="尚未初始化"):
            facade.chat(None, "你好")
