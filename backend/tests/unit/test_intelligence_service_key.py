import pytest
from fastapi import HTTPException

from cookfully.intelligence import service


def test_missing_server_key_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(service, "SERVICE_KEY", "")
    with pytest.raises(HTTPException) as caught:
        service.require_service_key("anything")
    assert caught.value.status_code == 503


def test_wrong_or_absent_key_is_rejected_and_right_key_accepted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(service, "SERVICE_KEY", "s3cret-key")
    for bad in (None, "", "s3cret-kez"):
        with pytest.raises(HTTPException) as caught:
            service.require_service_key(bad)
        assert caught.value.status_code == 401
    service.require_service_key("s3cret-key")
