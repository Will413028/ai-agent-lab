from urllib.parse import parse_qs, urlencode, urlsplit

from bs4 import BeautifulSoup

from .artifacts import ToolFailure
from .network import PublicWeb


def plain_html(content: str) -> str:
    soup = BeautifulSoup(content, "html.parser")
    for item in soup(["script", "style", "noscript", "iframe", "form"]):
        item.decompose()
    return "\n".join(line.strip() for line in soup.get_text("\n").splitlines() if line.strip())


def parse_search(content: str) -> list[dict[str, str]]:
    soup = BeautifulSoup(content, "html.parser")
    if soup.select_one("#challenge-form, .anomaly-modal"):
        raise ToolFailure("dependency_failure", "搜尋來源要求人工驗證，請稍後再試。")
    results = []
    for anchor in soup.select("a.result__a"):
        url = str(anchor.get("href", ""))
        if url.startswith("//"):
            url = "https:" + url
        query = parse_qs(urlsplit(url).query)
        if "uddg" in query:
            url = query["uddg"][0]
        parsed = urlsplit(url)
        if parsed.scheme not in ("http", "https") or parsed.username is not None:
            continue
        parent = anchor.find_parent(class_="result")
        snippet = parent.select_one(".result__snippet") if parent else None
        results.append(
            {
                "title": anchor.get_text(" ", strip=True)[:300],
                "url": url[:2048],
                "snippet": snippet.get_text(" ", strip=True)[:1000] if snippet else "",
            }
        )
        if len(results) == 5:
            break
    if not results and not soup.select_one(".no-results, .result--no-result"):
        raise ToolFailure("dependency_failure", "搜尋來源格式已變更，無法解析。")
    return results


class DuckDuckGoSearch:
    def __init__(self, web: PublicWeb):
        self.web = web

    async def search(self, query: str):
        response = await self.web.fetch(
            "https://html.duckduckgo.com/html/?" + urlencode({"q": query}), 2 * 1024 * 1024
        )
        return parse_search(response.body.decode("utf-8", errors="replace"))


class FixtureWeb:
    async def fetch(self, url: str, limit: int = 8 * 1024 * 1024):
        from .network import WebResponse

        if url != "https://example.com/learning":
            raise ToolFailure("dependency_failure", "離線示範僅提供固定範例網站。")
        return WebResponse(
            b"<html><title>Agent learning</title>"
            b"<p>Understand tool calls and verify sources.</p></html>",
            "text/html",
            url,
        )


class FixtureSearch:
    async def search(self, query: str):
        return [
            {
                "title": "Agent 學習範例（離線資料）",
                "url": "https://example.com/learning",
                "snippet": "工具呼叫須保留 call ID，最後以可下載產物呈現。",
            }
        ]
