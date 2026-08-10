from typer import Typer

app = Typer(
    name="vigor-vine",
    help="Operate the Vigor & Vine self-hosted nutrition planner.",
    no_args_is_help=True,
)


@app.callback()
def main() -> None:
    """Run Vigor & Vine operator commands."""


@app.command()
def version() -> None:
    """Print the installed application version."""
    from vigor_vine import __version__

    print(__version__)
