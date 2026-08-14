from __future__ import annotations

import ipaddress
import socket
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from urllib.parse import SplitResult, urljoin, urlsplit, urlunsplit

import httpx

from cookfully.domain.common import DomainError

DnsResolver = Callable[[str], Awaitable[set[str]]]


@dataclass(frozen=True, slots=True)
class FetchedResource:
    content: bytes
    final_url: str
    content_type: str


async def system_resolver(hostname: str) -> set[str]:
    loop = __import__("asyncio").get_running_loop()
    records = await loop.run_in_executor(
        None,
        lambda: socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM),
    )
    return {str(record[4][0]) for record in records}


class SafeFetcher:
    def __init__(
        self,
        *,
        resolver: DnsResolver = system_resolver,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout_seconds: float = 10,
        max_bytes: int = 2 * 1024 * 1024,
        max_redirects: int = 5,
    ) -> None:
        self._resolver = resolver
        self._transport = transport
        self._timeout = httpx.Timeout(timeout_seconds)
        self._max_bytes = max_bytes
        self._max_redirects = max_redirects

    async def fetch(
        self,
        url: str,
        *,
        allowed_content_types: frozenset[str] = frozenset({"text/html", "application/xhtml+xml"}),
        max_bytes: int | None = None,
    ) -> FetchedResource:
        size_limit = max_bytes if max_bytes is not None else self._max_bytes
        if size_limit <= 0:
            raise ValueError("max_bytes must be positive")
        current = url
        async with httpx.AsyncClient(
            transport=self._transport,
            timeout=self._timeout,
            follow_redirects=False,
            trust_env=False,
            headers={"User-Agent": "CookfullyRecipeImporter/0.1"},
        ) as client:
            for redirect_count in range(self._max_redirects + 1):
                parsed, addresses = await self._validate_url(current)
                request_url = self._pinned_url(parsed, addresses[0])
                async with client.stream(
                    "GET",
                    request_url,
                    headers={"Host": parsed.netloc},
                    extensions={"sni_hostname": parsed.hostname},
                ) as response:
                    if response.status_code in {301, 302, 303, 307, 308}:
                        location = response.headers.get("location")
                        if not location or redirect_count == self._max_redirects:
                            raise DomainError(
                                "redirect_blocked", "Recipe address redirected unsafely.", 422
                            )
                        current = urljoin(current, location)
                        continue
                    if response.status_code != 200:
                        raise DomainError(
                            "source_unavailable",
                            f"Recipe source returned HTTP {response.status_code}.",
                            422,
                        )
                    content_type = response.headers.get("content-type", "").split(";", 1)[0].lower()
                    if content_type not in allowed_content_types:
                        raise DomainError(
                            "content_type_blocked", "Source content type is not allowed.", 422
                        )
                    declared = response.headers.get("content-length")
                    if declared:
                        try:
                            declared_size = int(declared)
                        except ValueError as exc:
                            raise DomainError(
                                "source_metadata_invalid",
                                "Source returned an invalid content length.",
                                422,
                            ) from exc
                        if declared_size < 0 or declared_size > size_limit:
                            raise DomainError(
                                "source_too_large", "Source exceeds the import size limit.", 422
                            )
                    content = bytearray()
                    async for chunk in response.aiter_bytes():
                        content.extend(chunk)
                        if len(content) > size_limit:
                            raise DomainError(
                                "source_too_large", "Source exceeds the import size limit.", 422
                            )
                    return FetchedResource(bytes(content), current, content_type)
        raise DomainError("redirect_blocked", "Recipe address redirected too many times.", 422)

    async def _validate_url(self, url: str) -> tuple[SplitResult, tuple[str, ...]]:
        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise DomainError(
                "url_blocked", "Only public HTTP or HTTPS addresses are allowed.", 422
            )
        if parsed.username or parsed.password:
            raise DomainError(
                "url_blocked", "Addresses containing credentials are not allowed.", 422
            )
        addresses = await self._resolver(parsed.hostname)
        if not addresses:
            raise DomainError("dns_failed", "Recipe address could not be resolved.", 422)
        validated: list[str] = []
        for raw in addresses:
            address = ipaddress.ip_address(raw)
            if (
                address.is_private
                or address.is_loopback
                or address.is_link_local
                or address.is_multicast
                or address.is_reserved
                or address.is_unspecified
            ):
                raise DomainError(
                    "private_address_blocked", "Private network addresses are blocked.", 422
                )
            validated.append(address.compressed)
        return parsed, tuple(sorted(validated))

    @staticmethod
    def _pinned_url(parsed: SplitResult, address: str) -> str:
        rendered = f"[{address}]" if ":" in address else address
        if parsed.port is not None:
            rendered = f"{rendered}:{parsed.port}"
        return urlunsplit((parsed.scheme, rendered, parsed.path, parsed.query, ""))
