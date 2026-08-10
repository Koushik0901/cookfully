from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer

from vigor_vine.infrastructure.config import get_settings
from vigor_vine.infrastructure.erasure_ledger import ErasureLedger

app = typer.Typer(name="erasure-ledger", help="Verify the independent erasure-ledger chain.")


@app.command("verify")
def verify_command(
    ledger: Annotated[
        Path | None,
        typer.Option(help="Ledger root; defaults to VV_ERASURE_LEDGER_ROOT."),
    ] = None,
) -> None:
    selected = ErasureLedger(ledger or get_settings().erasure_ledger_root)
    records = selected.verify()
    cursor, head_hash = selected.head()
    typer.echo(
        json.dumps(
            {
                "valid": True,
                "cursor": cursor,
                "headHash": head_hash,
                "records": len(records),
            },
            indent=2,
        )
    )
