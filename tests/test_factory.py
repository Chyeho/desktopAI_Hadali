"""单元测试：模型工厂 modelFactory/factory.py

覆盖：
- ChatModelFactory：生产 ChatOpenAI（mock langchain_openai）
- EmbeddingModelFactory：预留桩抛 NotImplementedError
"""
from unittest.mock import MagicMock, patch

import pytest

from backend.model_factory.factory import BaseModelFactory, ChatModelFactory, EmbeddingModelFactory


class TestBaseModelFactory:
    """BaseModelFactory：抽象基类"""

    def test_cannot_instantiate_abc(self):
        with pytest.raises(TypeError):
            BaseModelFactory()

    def test_generator_is_abstract(self):
        assert hasattr(BaseModelFactory, "generator")


class TestChatModelFactory:
    """ChatModelFactory：大语言模型工厂"""

    def test_init_stores_params(self):
        factory = ChatModelFactory(api_key="sk-x", base_url="http://api", model="m")
        assert factory.api_key == "sk-x"
        assert factory.base_url == "http://api"
        assert factory.model == "m"

    def test_generator_returns_chatopenai(self):
        """mock ChatOpenAI，验证工厂生产逻辑"""
        with patch("backend.model_factory.factory.ChatOpenAI") as mock_chatopenai:
            mock_instance = MagicMock()
            mock_chatopenai.return_value = mock_instance

            factory = ChatModelFactory(api_key="sk-x", base_url="http://api", model="gpt-4")
            llm = factory.generator(temperature=0.7, max_tokens=100)

            mock_chatopenai.assert_called_once_with(
                model="gpt-4",
                api_key="sk-x",
                base_url="http://api",
                temperature=0.7,
                max_tokens=100,
            )
            assert llm is mock_instance

    def test_generator_no_extra_params(self):
        """不传生成参数时只传连接参数"""
        with patch("backend.model_factory.factory.ChatOpenAI") as mock_chatopenai:
            factory = ChatModelFactory(api_key="sk-x", base_url="http://api", model="m")
            factory.generator()
            mock_chatopenai.assert_called_once_with(
                model="m", api_key="sk-x", base_url="http://api",
            )

    def test_generator_passes_arbitrary_params(self):
        with patch("backend.model_factory.factory.ChatOpenAI") as mock_chatopenai:
            factory = ChatModelFactory(api_key="sk-x", base_url="http://api", model="m")
            factory.generator(top_p=0.9, presence_penalty=0.5)
            _, kwargs = mock_chatopenai.call_args
            assert kwargs["top_p"] == 0.9
            assert kwargs["presence_penalty"] == 0.5

    def test_is_subclass_of_base(self):
        assert issubclass(ChatModelFactory, BaseModelFactory)


class TestEmbeddingModelFactory:
    """EmbeddingModelFactory：预留桩"""

    def test_generator_raises_not_implemented(self):
        factory = EmbeddingModelFactory()
        with pytest.raises(NotImplementedError, match="文本嵌入模型"):
            factory.generator()

    def test_is_subclass_of_base(self):
        assert issubclass(EmbeddingModelFactory, BaseModelFactory)
