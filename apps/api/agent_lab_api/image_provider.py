import json
from urllib.parse import urlencode, urlsplit

from .artifacts import ToolFailure
from .image_models import ImageResult, ImageSearchResult
from .network import PublicWeb
from .web_tools import plain_html


def public_https(value: str, host: str) -> str:
    parsed = urlsplit(value)
    if parsed.scheme != "https" or parsed.hostname != host or parsed.username is not None:
        raise ToolFailure("dependency_failure", "圖片來源 URL 格式不正確。")
    return value


def commons_images(data: dict) -> ImageSearchResult:
    if "error" in data or not isinstance(data.get("query"), dict):
        # A real no-results response has query with pages missing or empty.
        if data.get("batchcomplete") is not None and "error" not in data:
            return ImageSearchResult(provider="Wikimedia Commons", images=[])
        raise ToolFailure("dependency_failure", "圖片搜尋來源回傳錯誤。")
    pages = data["query"].get("pages", {})
    if not isinstance(pages, dict):
        raise ToolFailure("dependency_failure", "圖片搜尋格式不正確。")
    images = []
    for page in sorted(pages.values(), key=lambda p: p.get("index", 999)):
        info = page.get("imageinfo", [{}])[0]
        metadata = info.get("extmetadata", {})
        # Only display supported image files with explicit attribution and license metadata.
        if info.get("mime") not in ("image/jpeg", "image/png", "image/webp", "image/gif"):
            continue

        def meta(key, values=metadata):
            value = str(values.get(key, {}).get("value", ""))
            return (plain_html(value) if "<" in value else value.strip())[:1000]

        artist, license_name, license_url = (
            meta("Artist"),
            meta("LicenseShortName"),
            meta("LicenseUrl"),
        )
        if not artist or not license_name or not license_url:
            continue
        if not license_url.startswith("https://"):
            continue
        images.append(
            ImageResult(
                title=str(page.get("title", ""))[:300],
                url=public_https(info.get("thumburl", info.get("url", "")), "upload.wikimedia.org"),
                source_url=public_https(info.get("descriptionurl", ""), "commons.wikimedia.org"),
                artist=artist,
                license=license_name,
                license_url=license_url,
            )
        )
        if len(images) == 5:
            break
    return ImageSearchResult(provider="Wikimedia Commons", images=images)


class CommonsImages:
    async def search(self, query: str) -> ImageSearchResult:
        params = {
            "action": "query",
            "generator": "search",
            "gsrsearch": query,
            "gsrnamespace": "6",
            "gsrlimit": "10",
            "prop": "imageinfo",
            "iiprop": "url|extmetadata|mime",
            "iiurlwidth": "640",
            "format": "json",
        }
        response = await PublicWeb().fetch(
            "https://commons.wikimedia.org/w/api.php?" + urlencode(params), 2 * 1024 * 1024
        )
        try:
            return commons_images(json.loads(response.body))
        except (ValueError, TypeError, KeyError) as failure:
            raise ToolFailure("dependency_failure", "圖片搜尋格式不正確。") from failure


class FixtureImages:
    async def search(self, query: str) -> ImageSearchResult:
        return ImageSearchResult(
            provider="離線示範",
            images=[
                ImageResult(
                    title="學習圖片範例",
                    url="/fixture-images/coffee.svg",
                    source_url="/fixture-images/coffee.svg",
                    artist="AI Agent Lab（示範插圖）",
                    license="CC0",
                    license_url="https://creativecommons.org/publicdomain/zero/1.0/",
                )
            ],
        )
