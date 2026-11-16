import json
import re
from pathlib import Path

from typer.testing import CliRunner

from cookfully.cli.main import app

_ANSI = re.compile(r"\x1b\[[0-9;]*m")


def _plain(text: str) -> str:
    """Typer forces colour under GitHub Actions, which splits flags such as ``--ledger``."""

    return _ANSI.sub("", text)


def test_backup_export_and_ledger_operator_commands_are_registered(tmp_path: Path) -> None:
    runner = CliRunner()

    root = runner.invoke(app, ["--help"])
    assert root.exit_code == 0
    assert "backup" in root.stdout
    assert "export" in root.stdout
    assert "erasure-ledger" in root.stdout
    assert "usability-study" in root.stdout

    backup = runner.invoke(app, ["backup", "--help"])
    assert backup.exit_code == 0
    assert all(command in backup.stdout for command in ("create", "verify", "restore", "compare"))

    export = runner.invoke(app, ["export", "--help"])
    assert export.exit_code == 0
    assert "create" in export.stdout and "verify" in export.stdout

    ledger = runner.invoke(app, ["erasure-ledger", "verify", "--help"])
    assert ledger.exit_code == 0
    assert "--ledger" in _plain(ledger.stdout)
    verified = runner.invoke(
        app, ["erasure-ledger", "verify", "--ledger", str(tmp_path / "ledger")]
    )
    assert verified.exit_code == 0
    assert json.loads(verified.stdout) == {
        "valid": True,
        "cursor": 0,
        "headHash": "0" * 64,
        "records": 0,
    }
