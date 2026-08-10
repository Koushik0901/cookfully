from typer.testing import CliRunner

from vigor_vine.cli.main import app


def test_backup_and_export_operator_commands_are_registered() -> None:
    runner = CliRunner()

    root = runner.invoke(app, ["--help"])
    assert root.exit_code == 0
    assert "backup" in root.stdout
    assert "export" in root.stdout

    backup = runner.invoke(app, ["backup", "--help"])
    assert backup.exit_code == 0
    assert all(command in backup.stdout for command in ("create", "verify", "restore", "compare"))

    export = runner.invoke(app, ["export", "--help"])
    assert export.exit_code == 0
    assert "create" in export.stdout and "verify" in export.stdout
