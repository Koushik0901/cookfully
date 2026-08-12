from typer import Typer

from cookfully.cli.backup import app as backup_app
from cookfully.cli.erasure_ledger import app as erasure_ledger_app
from cookfully.cli.export import app as export_app
from cookfully.cli.nutrition_report import app as nutrition_report_app
from cookfully.cli.owner import app as owner_app
from cookfully.cli.reference_data import app as reference_data_app
from cookfully.cli.usability_study import app as usability_study_app

app = Typer(
    name="cookfully",
    help="Operate the Cookfully self-hosted nutrition planner.",
    no_args_is_help=True,
)
app.add_typer(reference_data_app)
app.add_typer(nutrition_report_app)
app.add_typer(backup_app)
app.add_typer(export_app)
app.add_typer(owner_app)
app.add_typer(erasure_ledger_app)
app.add_typer(usability_study_app)


@app.callback()
def main() -> None:
    """Run Cookfully operator commands."""


@app.command()
def version() -> None:
    """Print the installed application version."""
    from cookfully import __version__

    print(__version__)
