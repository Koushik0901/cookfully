"""Defensive response headers for every API response."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi import Request, Response

_STATIC_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cross-Origin-Resource-Policy": "same-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=(), usb=()",
}
_HSTS = "max-age=31536000"


async def security_headers_middleware(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    response = await call_next(request)
    for name, value in _STATIC_HEADERS.items():
        response.headers.setdefault(name, value)
    # Account, settings and recipe JSON must never sit in a shared or browser cache.
    if response.headers.get("content-type", "").startswith("application/json"):
        response.headers.setdefault("Cache-Control", "no-store")
    if request.url.scheme == "https":
        response.headers.setdefault("Strict-Transport-Security", _HSTS)
    return response
