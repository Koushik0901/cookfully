from typer import Typer

from vigor_vine.cli.nutrition_report import app as nutrition_report_app
from vigor_vine.cli.reference_data import app as reference_data_app

app = Typer(
    name="vigor-vine",
    help="Operate the Vigor & Vine self-hosted nutrition planner.",
    no_args_is_help=True,
)
app.add_typer(reference_data_app)
app.add_typer(nutrition_report_app)


@app.callback()
def main() -> None:
    """Run Vigor & Vine operator commands."""


@app.command()
def version() -> None:
    """Print the installed application version."""
    from vigor_vine import __version__

    print(__version__)
