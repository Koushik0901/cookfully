from typing import Any

from cookfully.application.reference_data import INSTALL_JOB_DEADLINE
from cookfully.jobs.app import celery_app
from cookfully.jobs.outbox_process import INSTALL_GRACE, publish


class _Captured:
    def __init__(self) -> None:
        self.args: tuple[Any, ...] | None = None
        self.kwargs: dict[str, Any] = {}
        self.options: dict[str, Any] = {}
        self.name: str | None = None


def _install_envelope() -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "jobId": "00000000-0000-0000-0000-000000000001",
        "kind": "reference_data_install",
        "aggregateType": "job",
        "aggregateId": "00000000-0000-0000-0000-000000000001",
        "inputHash": "sha256:abc",
        "traceId": "t",
        "requestedAt": "2026-08-15T00:00:00Z",
    }


def test_install_envelope_carries_extended_message_time_limits(
    monkeypatch: Any,
) -> None:
    captured = _Captured()

    def fake_send_task(
        name: str,
        args: tuple[Any, ...] | None = None,
        kwargs: dict[str, Any] | None = None,
        **options: Any,
    ) -> None:
        captured.name = name
        captured.args = args or ()
        captured.kwargs = kwargs or {}
        captured.options = options

    monkeypatch.setattr(celery_app, "send_task", fake_send_task)
    publish(_install_envelope())
    assert captured.name == "cookfully.process_job"
    assert captured.kwargs == {"envelope": _install_envelope()}
    assert captured.options["soft_time_limit"] == int(INSTALL_JOB_DEADLINE.total_seconds())
    assert captured.options["time_limit"] == int(INSTALL_JOB_DEADLINE.total_seconds()) + int(
        INSTALL_GRACE.total_seconds()
    )


def test_other_kinds_keep_default_time_limits(monkeypatch: Any) -> None:
    captured = _Captured()
    envelope = _install_envelope()
    envelope["kind"] = "recipe_import"

    def fake_send(name: str, **options: Any) -> None:
        captured.name = name
        captured.options = options

    monkeypatch.setattr(celery_app, "send_task", fake_send)
    publish(envelope)
    assert captured.options.get("soft_time_limit") is None
    assert captured.options.get("time_limit") is None
