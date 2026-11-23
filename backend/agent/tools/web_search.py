'''公共工具：联网搜索（Bing 免费网页搜索，无需 API Key，标准库 urllib 实现）

说明：选用 Bing（cn.bing.com）而非 DuckDuckGo，因后者在国内网络经常超时；
Bing 国内可直接访问且返回静态 HTML，解析稳定。
'''
import html as html_lib
import re
import urllib.parse
import urllib.request

from langchain_core.tools import tool

from utils.logger_handler import logger

# Bing 网页搜索接口（返回静态 HTML，无需 JS）
_SEARCH_URL = "https://cn.bing.com/search?q={q}"
_TIMEOUT = 12   # 请求超时（秒）
_TOP_N = 5     # 返回结果条数


def _strip_tags(text: str) -> str:
    '''去除 HTML 标签并反转义实体，得到纯文本'''
    return html_lib.unescape(re.sub(r"<[^>]+>", "", text)).strip()


@tool
def web_search(query: str) -> str:
    """联网搜索最新信息。当用户询问实时新闻、最新事件、未知事实、需要查证的资料
    等模型自身知识无法回答的问题时调用此工具。
    参数 query 为搜索关键词。返回前若干条搜索结果的标题、链接与摘要。
    """
    try:
        url = _SEARCH_URL.format(q=urllib.parse.quote(query))
        req = urllib.request.Request(
            url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        )
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            page = resp.read().decode("utf-8", errors="ignore")

        # 提取结果标题与链接（b_algo 区块内 <h2><a href="...">标题</a>）
        title_matches = re.findall(
            r'<h2[^>]*>\s*<a[^>]*href="(http[^"]+)"[^>]*>(.*?)</a>', page, re.S
        )
        # 摘要：优先 b_lineclamp，回退 b_caption 内 <p>
        snippet_matches = re.findall(
            r'<p class="b_lineclamp[^"]*"[^>]*>(.*?)</p>', page, re.S
        )
        if not snippet_matches:
            snippet_matches = re.findall(
                r'<div class="b_caption"[^>]*>.*?<p[^>]*>(.*?)</p>', page, re.S
            )

        if not title_matches:
            logger.warning(f"[web_search]未搜索到结果，query={query}")
            return f"未搜索到与「{query}」相关的结果，可尝试更换关键词。"

        lines = [f"以下是关于「{query}」的联网搜索结果："]
        for i, ((href, title), snippet) in enumerate(
            zip(title_matches, snippet_matches), start=1
        ):
            if i > _TOP_N:
                break
            clean_title = _strip_tags(title)
            clean_snippet = _strip_tags(snippet)
            if not clean_title:
                continue
            lines.append(f"{i}. {clean_title}（{href}）\n   {clean_snippet}")

        if len(lines) == 1:
            return f"搜索「{query}」未得到有效结果。"

        logger.info(
            f"[web_search]搜索完成，query={query}，返回{min(len(title_matches), _TOP_N)}条结果"
        )
        return "\n".join(lines)
    except Exception as e:
        logger.error(f"[web_search]联网搜索失败，query={query}，原因：{str(e)}")
        return f"联网搜索失败：{str(e)}。请稍后重试。"
