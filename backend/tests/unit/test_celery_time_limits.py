from typing import Any

from cookfully.application.reference_data import INSTALL_JOB_DEADLINE
from cookfully.jobs.app import INSTALL_GRACE, adjust_reference_data_time_limit


class _FakeRequest:
    def __init__(self) -> None:
        self.args: tuple[Any, ...] = ()
        self.kwargs: dict[str, Any] = {}
        self.soft_time_limit: int | None = 55
        self.time_limit: int | None = 60


class _FakeTask:
    def __init__(self, name: str, envelope: dict[str, Any] | None = None) -> None:
        self.name = name
        self.request = _FakeRequest()
        if envelope is not None:
            self.request.kwargs = {"envelope": envelope}


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


def test_install_envelope_gets_extended_limits() -> None:
    task = _FakeTask("cookfully.process_job", _install_envelope())
    adjust_reference_data_time_limit(task_id="1", task=task)
    assert task.request.soft_time_limit == int(INSTALL_JOB_DEADLINE.total_seconds())
    assert task.request.time_limit == int(INSTALL_JOB_DEADLINE.total_seconds()) + int(
        INSTALL_GRACE.total_seconds()
    )


def test_other_kinds_keep_default_limits() -> None:
    envelope = _install_envelope()
    envelope["kind"] = "recipe_import"
    task = _FakeTask("cookfully.process_job", envelope)
    adjust_reference_data_time_limit(task_id="1", task=task)
    assert task.request.soft_time_limit == 55
    assert task.request.time_limit == 60


def test_other_task_names_untouched() -> None:
    task = _FakeTask("cookfully.health")
    adjust_reference_data_time_limit(task_id="1", task=task)
    assert task.request.soft_time_limit == 55
    assert task.request.time_limit == 60


def test_missing_envelope_untouched() -> None:
    task = _FakeTask("cookfully.process_job")
    adjust_reference_data_time_limit(task_id="1", task=task)
    assert task.request.soft_time_limit == 55
    assert task.request.time_limit == 60
