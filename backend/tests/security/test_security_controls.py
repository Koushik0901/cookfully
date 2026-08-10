from __future__ import annotations

import zipfile
from datetime import timedelta
from pathlib import Path

import httpx
import pytest

from vigor_vine.application.exports import _safe_member
from vigor_vine.cli.backup import verify_backup
from vigor_vine.domain.common import DomainError, utc_now
from vigor_vine.infrastructure.media_store import MediaStore
from vigor_vine.infrastructure.models import Base
from vigor_vine.infrastructure.observability import redact
from vigor_vine.infrastructure.safe_fetch import SafeFetcher


@pytest.mark.asyncio
async def test_redirect_dns_rebinding_is_revalidated_and_blocked() -> None:
    resolutions = 0

    async def rebinding_resolver(_: str) -> set[str]:
        nonlocal resolutions
        resolutions += 1
        return {"93.184.216.34"} if resolutions == 1 else {"127.0.0.1"}

    def redirect(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "93.184.216.34"
        assert request.headers["host"] == "recipes.example"
        return httpx.Response(
            302,
            headers={"location": "https://recipes.example/private"},
            request=request,
        )

    with pytest.raises(DomainError) as error:
        await SafeFetcher(
            resolver=rebinding_resolver,
            transport=httpx.MockTransport(redirect),
        ).fetch("https://recipes.example/start")

    assert error.value.code == "private_address_blocked"
    assert resolutions == 2


def test_failed_import_diagnostic_is_opt_in_encrypted_and_expires_at_24_hours(
    tmp_path: Path,
) -> None:
    store = MediaStore(tmp_path / "media", "test-only-secret")
    private_html = b"<html>provider diagnostic with private recipe text</html>"

    with pytest.raises(DomainError) as disabled:
        store.put(private_html, "text/html", kind="failed_import_diagnostic")
    assert disabled.value.code == "diagnostics_disabled"

    before = utc_now()
    stored = store.put(
        private_html,
        "text/html",
        kind="failed_import_diagnostic",
        diagnostics_enabled=True,
    )
    after = utc_now()
    encrypted = store.resolve_key(stored.storage_key).read_bytes()

    assert stored.encrypted is True
    assert encrypted != private_html
    assert store.read(stored.storage_key, encrypted=True) == private_html
    assert stored.expires_at is not None
    assert before + timedelta(hours=24) <= stored.expires_at <= after + timedelta(hours=24)


def test_models_do_not_retain_raw_provider_or_prompt_payloads() -> None:
    prohibited = {
        "raw_provider_payload",
        "provider_payload",
        "provider_response",
        "prompt",
        "prompt_text",
        "raw_html",
        "html_body",
    }
    persisted_names = {
        column.name for table in Base.metadata.tables.values() for column in table.columns
    }

    assert persisted_names.isdisjoint(prohibited)


@pytest.mark.parametrize(
    "member",
    ("../owner.json", "/absolute.json", "media\\..\\secret", "safe/../../secret"),
)
def test_export_archive_traversal_is_rejected(member: str) -> None:
    with pytest.raises(DomainError) as error:
        _safe_member(member)
    assert error.value.code == "unsafe_archive"


def test_backup_archive_traversal_is_rejected_before_restore(tmp_path: Path) -> None:
    archive = tmp_path / "malicious.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("../outside.txt", "not allowed")
        bundle.writestr("manifest.json", "{}")

    with pytest.raises(DomainError) as error:
        verify_backup(archive)
    assert error.value.code == "unsafe_archive"
    assert not (tmp_path.parent / "outside.txt").exists()


def test_secret_redaction_is_recursive_and_does_not_mutate_safe_fields() -> None:
    value = {
        "email": "owner@example.com",
        "authorization": "Bearer vv_secret",
        "nested": [
            {"password": "correct horse battery staple", "count": 2},
            {"rawProviderPayload": "private response"},
        ],
    }

    assert redact(value) == {
        "email": "owner@example.com",
        "authorization": "[REDACTED]",
        "nested": [
            {"password": "[REDACTED]", "count": 2},
            {"rawProviderPayload": "[REDACTED]"},
        ],
    }
