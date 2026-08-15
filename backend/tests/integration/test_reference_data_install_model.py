from __future__ import annotations

from cookfully.domain.common import uuid7
from cookfully.infrastructure.models.identity import OwnerAccount
from cookfully.infrastructure.models.reference_data_installs import ReferenceDataInstall


def test_install_request_model_round_trips(
    session_factory,
) -> None:
    install_id = uuid7()
    with session_factory.begin() as session:
        owner = OwnerAccount(
            email="install-owner@example.com",
            display_name="Install Owner",
            password_hash="not-used",
            timezone="UTC",
            week_starts_on=1,
        )
        session.add(owner)
        session.flush()
        session.add(
            ReferenceDataInstall(
                id=install_id,
                owner_id=owner.id,
                input_hash="sha256:abc",
                datasets=["foundation_sr_legacy", "branded"],
                status="queued",
            )
        )
    with session_factory() as session:
        stored = session.get(ReferenceDataInstall, install_id)
        assert stored is not None
        assert stored.datasets == ["foundation_sr_legacy", "branded"]
        assert stored.status == "queued"
