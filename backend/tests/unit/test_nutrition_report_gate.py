from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from cookfully.cli import nutrition_report

PASSING = {"sc001Passed": True, "sc002Passed": True, "sc003Passed": True}


def _run(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, report: dict[str, object], *flags: str
) -> int:
    monkeypatch.setattr(nutrition_report, "build_report", lambda corpus_root: report)
    result = CliRunner().invoke(
        nutrition_report.app,
        ["--corpus-root", str(tmp_path), "--output", str(tmp_path / "out.json"), *flags],
    )
    return result.exit_code


def test_require_pass_accepts_a_report_where_every_criterion_passed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    report = {"primary": PASSING, "full": PASSING}
    assert _run(monkeypatch, tmp_path, report, "--require-pass") == 0


@pytest.mark.parametrize(
    "broken",
    [{**PASSING, "sc002Passed": False}, {"sc001Passed": True}, "not-a-mapping"],
    ids=["criterion-failed", "criterion-missing", "malformed-scope"],
)
def test_require_pass_rejects_failed_or_malformed_reports(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, broken: object
) -> None:
    report = {"primary": PASSING, "full": broken}
    assert _run(monkeypatch, tmp_path, report, "--require-pass") == 1


def test_without_require_pass_a_failing_report_is_still_written(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    report = {"primary": {"sc001Passed": False}, "full": {"sc001Passed": False}}
    assert _run(monkeypatch, tmp_path, report) == 0
    assert (tmp_path / "out.json").is_file()
