from __future__ import annotations

import json
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated
from uuid import UUID

import typer

from vigor_vine.application.owner_erasure import OwnerErasureService
from vigor_vine.infrastructure.config import get_settings
from vigor_vine.infrastructure.database import create_database_engine, create_session_factory
from vigor_vine.infrastructure.erasure_ledger import ErasureLedger

app = typer.Typer(name="owner", help="Perform offline owner lifecycle operations.")


@app.command()
def erase(
    owner_id: Annotated[UUID, typer.Option(help="Exact owner UUID to erase.")],
    confirm: Annotated[str, typer.Option(help='Must equal "ERASE OWNER <uuid>" exactly.')],
    erasure_ledger: Annotated[
        Path | None,
        typer.Option(help="Independent erasure-ledger root; defaults to VV_ERASURE_LEDGER_ROOT."),
    ] = None,
) -> None:
    """Erase the owner while API, worker, outbox, and retention are stopped."""

    settings = get_settings()
    engine = create_database_engine(settings)
    ledger = ErasureLedger(erasure_ledger or settings.erasure_ledger_root)
    try:
        result = OwnerErasureService(
            create_session_factory(engine),
            engine,
            ledger,
            media_root=settings.media_root,
            export_root=settings.export_root,
            source_instance_id=settings.instance_id,
        ).erase(
            owner_id,
            confirm,
            latest_backup_expiry=datetime.now(UTC) + timedelta(days=settings.backup_retention_days),
        )
        typer.echo(json.dumps(asdict(result), default=str, indent=2, sort_keys=True))
    finally:
        engine.dispose()
