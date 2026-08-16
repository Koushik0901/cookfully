"""Import preview storage: persist, scope to owner, and honour expiry."""

from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session, sessionmaker

from cookfully.application.auth import AuthService
from cookfully.infrastructure.models.import_preview import ImportPreviewRecord


def test_import_preview_record_persists_and_scopes_to_owner(
    session_factory: sessionmaker[Session],
) -> None:
    owner = AuthService(session_factory).bootstrap_owner(
        "preview@example.com", "correct horse battery staple", "Owner"
    )
    now = datetime(2026, 8, 16, tzinfo=UTC)
    with session_factory() as session:
        session.add(
            ImportPreviewRecord(
                owner_id=owner.id,
                parse_id="p-1",
                payload={"title": "Shawarma bowl"},
                created_at=now,
                expires_at=now + timedelta(minutes=15),
            )
        )
        session.commit()

    with session_factory() as session:
        record = (
            session.query(ImportPreviewRecord).filter_by(owner_id=owner.id, parse_id="p-1").one()
        )
        assert record.payload["title"] == "Shawarma bowl"
        assert record.expires_at == now + timedelta(minutes=15)
