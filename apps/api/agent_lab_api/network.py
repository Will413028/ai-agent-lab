import asyncio
import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit

import aiohttp
from aiohttp.abc import AbstractResolver

from .artifacts import MAX_ARTIFACT_BYTES, ToolFailure

USER_AGENT = "AI-Agent-Lab/0.3 (personal local learning)"


def public_ip(address: str) -> bool:
    try:
        parsed = ipaddress.ip_address(address)
    except ValueError:
        return False
    if isinstance(parsed, ipaddress.IPv6Address) and parsed.ipv4_mapped:
        return public_ip(str(parsed.ipv4_mapped))
    if isinstance(parsed, ipaddress.IPv6Address) and (
        parsed.sixtofour
        or parsed.teredo
        or parsed in ipaddress.ip_network("64:ff9b::/96")
        or parsed in ipaddress.ip_network("64:ff9b:1::/48")
    ):
        return False
    return parsed.is_global and not parsed.is_multicast


async def public_addresses(url: str) -> tuple[str, int, list[str]]:
    try:
        parsed = urlsplit(url)
        host, port = parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80)
    except ValueError as failure:
        raise ToolFailure("invalid_url", "URL 格式不正確。") from failure
    if (
        parsed.scheme not in ("http", "https")
        or not host
        or parsed.username is not None
        or parsed.password is not None
        or port not in (80, 443)
        or len(url) > 2048
        or "\\" in url
        or any(ord(c) < 33 for c in url)
    ):
        raise ToolFailure("invalid_url", "僅接受無帳密的公開 HTTP／HTTPS URL。")
    try:
        answers = await asyncio.get_running_loop().getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except OSError as failure:
        raise ToolFailure("dependency_failure", "無法解析遠端網站。") from failure
    addresses = sorted({answer[4][0] for answer in answers})
    if not addresses or not all(public_ip(address) for address in addresses):
        raise ToolFailure("network_blocked", "不允許存取本機或私人網路。")
    return host, port, addresses


class PinnedResolver(AbstractResolver):
    def __init__(self, host: str, addresses: list[str]):
        self.host, self.addresses = host, addresses

    async def resolve(self, host: str, port: int = 0, family: int = socket.AF_INET):
        if host != self.host:
            raise ToolFailure("network_blocked", "連線目的地與驗證結果不一致。")
        return [
            {
                "hostname": host,
                "host": address,
                "port": port,
                "family": socket.AF_INET6 if ":" in address else socket.AF_INET,
                "proto": 0,
                "flags": socket.AI_NUMERICHOST,
            }
            for address in self.addresses
        ]

    async def close(self):
        pass


@dataclass(frozen=True)
class WebResponse:
    body: bytes
    media_type: str
    url: str


class PublicWeb:
    async def fetch(self, url: str, limit: int = MAX_ARTIFACT_BYTES) -> WebResponse:
        try:
            async with asyncio.timeout(25):
                return await self._fetch(url, limit)
        except TimeoutError as failure:
            raise ToolFailure("tool_timeout", "遠端網站逾時。") from failure
        except (aiohttp.ClientError, OSError) as failure:
            raise ToolFailure("dependency_failure", "無法讀取遠端網站。") from failure

    async def _fetch(self, url: str, limit: int) -> WebResponse:
        retries = 0
        for _ in range(5):
            host, _, addresses = await public_addresses(url)
            # DNS is resolved once, checked, and pinned for the actual TLS connection.
            connector = aiohttp.TCPConnector(
                resolver=PinnedResolver(host, addresses), use_dns_cache=False
            )
            async with aiohttp.ClientSession(
                connector=connector,
                trust_env=False,
                timeout=aiohttp.ClientTimeout(total=15),
                headers={"User-Agent": USER_AGENT},
            ) as client:
                async with client.get(url, allow_redirects=False) as response:
                    if response.status in (301, 302, 303, 307, 308):
                        location = response.headers.get("Location")
                        if not location:
                            raise ToolFailure("dependency_failure", "遠端轉址無效。")
                        url = urljoin(url, location)
                        continue
                    if response.status == 429 or 500 <= response.status < 600:
                        if retries == 0:
                            delay = response.headers.get("Retry-After", "1")
                            if not delay.isdigit() or int(delay) > 3:
                                raise ToolFailure("dependency_failure", "遠端網站暫時無法使用。")
                            retries += 1
                            await asyncio.sleep(int(delay))
                            continue
                    if response.status != 200:
                        raise ToolFailure("dependency_failure", "遠端網站回傳錯誤。")
                    data = bytearray()
                    async for part in response.content.iter_chunked(32768):
                        data.extend(part)
                        if len(data) > limit:
                            raise ToolFailure("size_limit", "遠端內容超過大小上限。")
                    return WebResponse(bytes(data), response.content_type, url)
        raise ToolFailure("dependency_failure", "遠端轉址或重試次數超過上限。")
