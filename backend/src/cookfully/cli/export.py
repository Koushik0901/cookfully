from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer
from sqlalchemy import select

from cookfully.application.exports import PortableExportService, verify_portable_export
from cookfully.domain.common import utc_now
from cookfully.infrastructure.config import get_settings
from cookfully.infrastructure.database import create_database_engine, create_session_factory
from cookfully.infrastructure.media_store import MediaStore
from cookfully.infrastructure.models.identity import OwnerAccount

app = typer.Typer(name="export", help="Create and verify owner-portable data exports.")


@app.command("create")
def create_command(
    output: Annotated[Path, typer.Option(help="Directory that will receive the export archive.")],
    include_media: Annotated[bool, typer.Option(help="Include safe, non-diagnostic media.")] = True,
) -> None:
    """Create a versioned exact-decimal ZIP/NDJSON portable export."""

    settings = get_settings()
    engine = create_database_engine(settings)
    try:
        sessions = create_session_factory(engine)
        with sessions() as session:
            owner_id = session.scalar(select(OwnerAccount.id).limit(1))
        if owner_id is None:
            raise typer.BadParameter("No owner account exists; bootstrap the application first.")
        timestamp = utc_now()
        target = output / f"cookfully-export-{timestamp:%Y%m%dT%H%M%SZ}.zip"
        PortableExportService(
            sessions,
            MediaStore(settings.media_root, settings.secret_key.get_secret_value()),
        ).create_archive(owner_id, target, include_media=include_media, created_at=timestamp)
        typer.echo(json.dumps({"archive": str(target.resolve()), "verified": True}, indent=2))
    finally:
        engine.dispose()


@app.command("verify")
def verify_command(
    archive: Annotated[Path, typer.Argument(exists=True, dir_okay=False)],
) -> None:
    """Verify the portable manifest and every archive checksum."""

    typer.echo(json.dumps(verify_portable_export(archive), indent=2))
