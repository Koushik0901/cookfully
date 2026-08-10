import json
from pathlib import Path

from typer.testing import CliRunner

from vigor_vine.cli.main import app


def test_backup_export_and_ledger_operator_commands_are_registered(tmp_path: Path) -> None:
    runner = CliRunner()

    root = runner.invoke(app, ["--help"])
    assert root.exit_code == 0
    assert "backup" in root.stdout
    assert "export" in root.stdout
    assert "erasure-ledger" in root.stdout

    backup = runner.invoke(app, ["backup", "--help"])
    assert backup.exit_code == 0
    assert all(command in backup.stdout for command in ("create", "verify", "restore", "compare"))

    export = runner.invoke(app, ["export", "--help"])
    assert export.exit_code == 0
    assert "create" in export.stdout and "verify" in export.stdout

    ledger = runner.invoke(app, ["erasure-ledger", "verify", "--help"])
    assert ledger.exit_code == 0
    assert "--ledger" in ledger.stdout
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
