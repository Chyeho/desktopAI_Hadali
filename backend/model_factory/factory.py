'''工厂模式，用于生产模型（大语言模型、文本嵌入模型等）'''
from abc import ABC, abstractmethod
from typing import Any

from langchain_openai import ChatOpenAI

from utils.logger_handler import logger


class BaseModelFactory(ABC):
    """模型工厂基类：所有模型工厂都需实现 generator()"""

    @abstractmethod
    def generator(self, **kwargs) -> Any:
        """生产并返回一个模型实例"""
        raise NotImplementedError


class ChatModelFactory(BaseModelFactory):
    """大语言模型工厂：生产 langchain ChatOpenAI

    使用 OpenAI 协议，因此 DeepSeek、通义千问兼容端、本地 vLLM 等任意
    OpenAI 协议的模型都可通过 .env 的 API_KEY / BASE_URL / MODEL 切换。

    连接参数（api_key / base_url / model）在工厂实例化时固定；
    生成参数（temperature / max_tokens / top_p 等）由 generator 调用方
    按 agent 模式传入，实现同一连接下不同模式的差异化配置。
    """

    def __init__(self, api_key: str, base_url: str, model: str):
        self.api_key = api_key
        self.base_url = base_url
        self.model = model
        logger.info(f"[ChatModelFactory]初始化大模型工厂：model={model}，base_url={base_url}")

    def generator(self, **gen_params) -> ChatOpenAI:
        """生产一个 ChatOpenAI 实例

        常用 gen_params：temperature / max_tokens / top_p /
        presence_penalty / frequency_penalty（langchain ChatOpenAI 均显式支持）
        """
        llm = ChatOpenAI(
            model=self.model,
            api_key=self.api_key,
            base_url=self.base_url,
            **gen_params,
        )
        logger.debug(f"[ChatModelFactory]已生成大模型实例，生成参数：{gen_params}")
        return llm


class EmbeddingModelFactory(BaseModelFactory):
    """文本嵌入模型工厂（预留桩，暂不实现）

    后续接入 RAG 时实现 generator()，例如：
        from langchain_openai import OpenAIEmbeddings
        return OpenAIEmbeddings(model=..., api_key=..., base_url=...)
    """

    def generator(self, **kwargs) -> Any:
        logger.error("[EmbeddingModelFactory]文本嵌入模型尚未实现（待后续 RAG 接入）")
        raise NotImplementedError("文本嵌入模型暂未实现，待 RAG 功能接入后补充")
