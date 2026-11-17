from __future__ import annotations

import base64
import logging
from io import BytesIO
from types import SimpleNamespace
from typing import Any

import pytest
from PIL import Image

from cookfully.infrastructure import recipe_importer
from cookfully.infrastructure.recipe_importer import RecipeImporter


class _UndecodableImage:
    @property
    def image(self) -> Image.Image:
        raise ValueError("unsupported colour space")


def _usable(size: int) -> SimpleNamespace:
    return SimpleNamespace(image=Image.new("RGB", (size, size), (62, 116, 74)))


def test_undecodable_and_tiny_pdf_images_are_skipped(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    page = SimpleNamespace(images=[_UndecodableImage(), _usable(32), _usable(128)])
    reader: Any = SimpleNamespace(pages=[page])
    monkeypatch.setattr(recipe_importer, "PdfReader", lambda *args, **kwargs: reader)

    with caplog.at_level(logging.DEBUG, logger=recipe_importer.logger.name):
        urls = RecipeImporter._pdf_image_candidates(b"%PDF-fake")

    assert len(urls) == 1, "only the decodable, large-enough image is offered as a cover"
    prefix = "data:image/jpeg;base64,"
    assert urls[0].startswith(prefix)
    decoded = Image.open(BytesIO(base64.b64decode(urls[0].removeprefix(prefix))))
    assert decoded.size == (128, 128)
    assert any("undecodable PDF image" in record.getMessage() for record in caplog.records)
