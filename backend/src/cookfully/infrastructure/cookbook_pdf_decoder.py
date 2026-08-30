"""Cookbook decoding seam.

The importer supplies its established parsing implementation while this module
owns the input contract. Tests and future decoders can substitute this adapter
without changing URL or upload dispatch.
"""

from __future__ import annotations

from collections.abc import Callable

from cookfully.infrastructure.recipe_importer_types import ImportedCookbook


class CookbookPdfDecoder:
    """Decode cookbook bytes into the single import representation."""

    def __init__(self, decode: Callable[[bytes, str, str], ImportedCookbook]) -> None:
        self._decode = decode

    def decode(self, content: bytes, *, source_url: str, canonical_url: str) -> ImportedCookbook:
        return self._decode(content, source_url, canonical_url)
