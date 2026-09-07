"""单元测试：联网搜索工具 tools/common/web_search.py

覆盖：
- _strip_tags：HTML 标签去除与实体反转义
- web_search 工具的网络调用（mock urllib）
"""
from unittest.mock import MagicMock, patch

from tools.common.web_search import _strip_tags, web_search


class TestStripTags:
    """_strip_tags：去除 HTML 标签并反转义实体"""

    def test_plain_text(self):
        assert _strip_tags("hello world") == "hello world"

    def test_removes_simple_tags(self):
        assert _strip_tags("<b>bold</b>") == "bold"

    def test_removes_nested_tags(self):
        assert _strip_tags("<a><b>text</b></a>") == "text"

    def test_unescapes_entities(self):
        assert _strip_tags("a &amp; b &lt; c") == "a & b < c"

    def test_removes_tags_with_attributes(self):
        html = '<a href="http://x.com" class="link">标题</a>'
        assert _strip_tags(html) == "标题"

    def test_strips_whitespace(self):
        assert _strip_tags("  <p>  空格  </p>  ") == "空格"

    def test_empty_string(self):
        assert _strip_tags("") == ""

    def test_html_with_entities_and_tags(self):
        html = "<h2>标题 &amp; 内容</h2>"
        assert _strip_tags(html) == "标题 & 内容"


class TestWebSearchTool:
    """web_search：langchain 工具"""

    def test_tool_name(self):
        assert web_search.name == "web_search"

    def test_has_description(self):
        assert web_search.description
        assert "搜索" in web_search.description

    def test_invoke_success(self):
        """mock Bing 返回 HTML，验证结果解析"""
        fake_html = """
        <html><body>
        <li class="b_algo">
            <h2><a href="http://example.com/1">结果一</a></h2>
            <p class="b_lineclamp">摘要内容一</p>
        </li>
        <li class="b_algo">
            <h2><a href="http://example.com/2">结果二</a></h2>
            <p class="b_lineclamp">摘要内容二</p>
        </li>
        </body></html>
        """.encode("utf-8")

        mock_resp = MagicMock()
        mock_resp.read.return_value = fake_html
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = web_search.invoke({"query": "测试关键词"})

        assert "测试关键词" in result
        assert "结果一" in result
        assert "http://example.com/1" in result
        assert "摘要内容一" in result

    def test_invoke_no_results(self):
        """搜索无结果时返回提示"""
        fake_html = b"<html><body>no results here</body></html>"

        mock_resp = MagicMock()
        mock_resp.read.return_value = fake_html
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = web_search.invoke({"query": "不存在的关键词"})

        assert "未" in result  # 未搜索到 / 未得到有效结果

    def test_invoke_network_error_returns_message(self):
        """网络异常时返回友好错误信息"""
        with patch("urllib.request.urlopen", side_effect=Exception("connection refused")):
            result = web_search.invoke({"query": "测试"})
        assert "联网搜索失败" in result
