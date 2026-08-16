# In-app USDA Reference Data Install — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a fresh user install the USDA FoodData Central datasets from inside the app — via an onboarding step or Settings — with the worker downloading, importing, and activating pinned releases in the background.

**Architecture:** A new `ReferenceDataInstallService` (application layer) records an install request, enqueues it through the existing job/outbox/Celery machinery, and a worker handler downloads pinned USDA zips (HTTPX streaming), reuses the existing `cookfully.cli.reference_data.import_release/activate_release/release_status` functions, reports percent progress, and cleans up temp files. New API routes `/reference-data/status` and `/reference-data/install` (idempotency-keyed, owner-scoped). The onboarding record gains a `referenceDataChoice` column. Frontend: a "Nutrition data" Settings tab and a second onboarding screen.

**Tech Stack:** Python 3.13, FastAPI, Pydantic 2, SQLAlchemy 2, Alembic, Celery 5.6, HTTPX, PostgreSQL 18; TypeScript 5, React 19.2, TanStack Query, Vitest, Playwright.

## Global Constraints

- Verify with: `uv run --directory backend ruff format --check .`, `uv run --directory backend ruff check .`, `uv run --directory backend mypy src`, `uv run --directory backend pytest`, `pnpm --dir frontend lint`, `pnpm --dir frontend typecheck`, `pnpm --dir frontend test --run`, `pnpm --dir frontend build`.
- The OpenAPI contract test compares the generated document's operation set exactly against `specs/001-nutrition-recipe-planner/contracts/openapi.yaml` (path, method, operationId). Any new endpoint requires matching entries in that file; FastAPI derives `operationId` from the route function name.
- The frontend type client is generated: `frontend/src/app/api/generated/schema.ts` (openapi-typescript). After backend schema changes, regenerate it and commit it.
- Background handlers must be idempotent and reject stale input hashes (AGENTS.md). One install at a time (409). Already-installed pinned releases are skipped (no-op).
- Job policy constraints that shape this design: heartbeat staleness is 60 s (`requeue_stalled`), terminal deadline defaults to 15 min. Install jobs extend the deadline to 6 h at request time and heartbeat every 30 s while working.
- Do not add code comments (repo style). Owner-scoped auth only; no new roles.
- Design deviation (approved during planning): progress is a single 0–100 percent (shared `progress_current`/`progress_total` fields); there is no stored phase column, so the UI shows "Installing… NN%" rather than phases.
- USDA download URLs are pinned code constants. If a HEAD request fails during Task 1 verification, correct the URL to the real file on `https://fdc.nal.usda.gov/fdc-datasets/` and keep the same release metadata convention.

---

### Task 1: Pinned release catalog and input hash (backend, pure)

**Files:**
- Create: `backend/src/cookfully/application/reference_data.py` (constants and helpers only — the service class arrives in Task 3)
- Test: `backend/tests/unit/test_reference_data_install.py`

**Interfaces:**
- Produces: `InstallUnit = Literal["foundation_sr_legacy", "branded"]`; `INSTALL_JOB_KIND = "reference_data_install"`; `PinnedRelease` dataclass with fields `dataset_type: str`, `release_id: str`, `released_on: date`, `source_url: str`; `PINNED_RELEASES: dict[str, tuple[PinnedRelease, ...]]` keyed by unit; `install_input_hash(units: tuple[InstallUnit, ...]) -> str` returning `"sha256:" + hexdigest` of the canonical JSON of sorted unit names.

- [ ] **Step 1: Write the failing tests**

```python
from __future__ import annotations

from cookfully.application.reference_data import (
    PINNED_RELEASES,
    PinnedRelease,
    install_input_hash,
)


def test_pinned_releases_cover_the_two_install_units() -> None:
    assert set(PINNED_RELEASES) == {"foundation_sr_legacy", "branded"}
    foundation = PINNED_RELEASES["foundation_sr_legacy"]
    assert [item.dataset_type for item in foundation] == ["foundation", "sr_legacy"]
    assert all(item.release_id.startswith(("foundation-", "sr-legacy-")) for item in foundation)
    assert PINNED_RELEASES["branded"][0].dataset_type == "branded_food"


def test_pinned_releases_use_the_fdc_bulk_download_pattern() -> None:
    for unit in PINNED_RELEASES.values():
        for release in unit:
            assert release.source_url.startswith("https://fdc.nal.usda.gov/fdc-datasets/")
            assert release.source_url.endswith(".zip")
            assert release.released_on is not None


def test_install_input_hash_is_deterministic_and_order_independent() -> None:
    first = install_input_hash(("foundation_sr_legacy", "branded"))
    second = install_input_hash(("branded", "foundation_sr_legacy"))
    assert first == second
    assert install_input_hash(("foundation_sr_legacy",)) != first
    assert first.startswith("sha256:")
    assert len(first) == len("sha256:") + 64
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --directory backend pytest tests/unit/test_reference_data_install.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'cookfully.application.reference_data'`

- [ ] **Step 3: Implement the catalog and hash**

Create `backend/src/cookfully/application/reference_data.py`:

```python
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Literal

InstallUnit = Literal["foundation_sr_legacy", "branded"]
INSTALL_JOB_KIND = "reference_data_install"
INSTALL_JOB_DEADLINE = timedelta(hours=6)
HEARTBEAT_INTERVAL = timedelta(seconds=30)


@dataclass(frozen=True, slots=True)
class PinnedRelease:
    dataset_type: str
    release_id: str
    released_on: date
    source_url: str


PINNED_RELEASES: dict[str, tuple[PinnedRelease, ...]] = {
    "foundation_sr_legacy": (
        PinnedRelease(
            "foundation",
            "foundation-2024-04",
            date(2024, 4, 18),
            "https://fdc.nal.usda.gov/fdc-datasets/"
            "FoodData_Central_foundation_food_json_2024-04-18.zip",
        ),
        PinnedRelease(
            "sr_legacy",
            "sr-legacy-2018-04",
            date(2018, 4, 1),
            "https://fdc.nal.usda.gov/fdc-datasets/"
            "FoodData_Central_sr_legacy_food_json_2018-04.zip",
        ),
    ),
    "branded": (
        PinnedRelease(
            "branded_food",
            "branded-2024-04",
            date(2024, 4, 18),
            "https://fdc.nal.usda.gov/fdc-datasets/"
            "FoodData_Central_branded_food_json_2024-04-18.zip",
        ),
    ),
}


def install_input_hash(units: tuple[InstallUnit, ...]) -> str:
    payload = json.dumps(sorted(units), separators=(",", ":"))
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --directory backend pytest tests/unit/test_reference_data_install.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Verify the pinned download URLs exist**

Run: `uv run --directory backend python -c "import httpx; from cookfully.application.reference_data import PINNED_RELEASES; [httpx.head(r.source_url, follow_redirects=True, timeout=30).raise_for_status() for unit in PINNED_RELEASES.values() for r in unit]; print('all URLs reachable')"`
Expected: prints `all URLs reachable`. If any URL returns 404, replace it with the real current file name on `https://fdc.nal.usda.gov/fdc-datasets/` and re-run. Do not run this step against tests.

- [ ] **Step 6: Commit**

```bash
git add backend/src/cookfully/application/reference_data.py backend/tests/unit/test_reference_data_install.py
git commit -m "feat: pinned USDA release catalog and install input hash"
```

---

### Task 2: Install request model and migration

**Files:**
- Create: `backend/src/cookfully/infrastructure/models/reference_data_installs.py`
- Create: `backend/migrations/versions/0015_reference_data_install.py`

**Interfaces:**
- Produces: SQLAlchemy model `ReferenceDataInstall` (tablename `reference_data_installs`): `id` (UUID PK, `uuid7` default), `owner_id` (UUID FK `owner_accounts.id` ondelete CASCADE, not null, indexed), `input_hash` (String(128), not null), `datasets` (JSONB list of unit strings, not null), `status` (String(24), not null), `job_id` (UUID, nullable), `finished_at` (DateTime(timezone=True), nullable), `created_at`/`updated_at` via `TimestampMixin`.
- Consumes: `cookfully.domain.common.uuid7`, `cookfully.infrastructure.models.base.TimestampMixin`.

- [ ] **Step 1: Write the failing migration test**

Create `backend/tests/integration/test_reference_data_install_model.py`:

```python
from __future__ import annotations

from sqlalchemy import select

from cookfully.domain.common import uuid7
from cookfully.infrastructure.models.reference_data_installs import ReferenceDataInstall


def test_install_request_model_round_trips(
    session_factory,
) -> None:
    install_id = uuid7()
    with session_factory.begin() as session:
        session.add(
            ReferenceDataInstall(
                id=install_id,
                owner_id=uuid7(),
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
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run --directory backend pytest tests/integration/test_reference_data_install_model.py -v`
Expected: FAIL with `ModuleNotFoundError` (model does not exist yet).

- [ ] **Step 3: Create the model**

Create `backend/src/cookfully/infrastructure/models/reference_data_installs.py`:

```python
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from cookfully.domain.common import uuid7
from cookfully.infrastructure.models.base import Base, TimestampMixin


class ReferenceDataInstall(TimestampMixin, Base):
    __tablename__ = "reference_data_installs"
    __table_args__ = (Index("ix_reference_data_installs_owner_id", "owner_id"),)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    owner_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("owner_accounts.id", ondelete="CASCADE"),
        nullable=False,
    )
    input_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    datasets: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    job_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
```

- [ ] **Step 4: Create the migration**

Create `backend/migrations/versions/0015_reference_data_install.py`:

```python
"""Reference data install requests."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0015_reference_data_install"
down_revision: str | None = "0014_established_onboarding"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "reference_data_installs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "owner_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("owner_accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("input_hash", sa.String(128), nullable=False),
        sa.Column("datasets", postgresql.JSONB(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_reference_data_installs_owner_id", "reference_data_installs", ["owner_id"])


def downgrade() -> None:
    op.drop_table("reference_data_installs")
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `uv run --directory backend pytest tests/integration/test_reference_data_install_model.py -v`
Expected: PASS (the fixture creates tables from `Base.metadata`, which now includes the model).

- [ ] **Step 6: Run the full integration suite for regressions**

Run: `uv run --directory backend pytest tests/integration -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/src/cookfully/infrastructure/models/reference_data_installs.py backend/migrations/versions/0015_reference_data_install.py backend/tests/integration/test_reference_data_install_model.py
git commit -m "feat: reference data install request model and migration"
```

---

### Task 3: Install service — request, in-flight guard, status

**Files:**
- Modify: `backend/src/cookfully/application/reference_data.py` (add service)
- Test: `backend/tests/integration/test_reference_data_install_service.py`

**Interfaces:**
- Consumes: `PINNED_RELEASES`, `INSTALL_JOB_KIND`, `INSTALL_JOB_DEADLINE`, `install_input_hash` (Task 1); `ReferenceDataInstall` model (Task 2); `JobService.accept_in_session`, `JobService.progress`, `JobService.latest_for_aggregate`; `cookfully.cli.reference_data.release_status`; `cookfully.domain.common.DomainError, utc_now, uuid7`; `cookfully.infrastructure.models.jobs.NONTERMINAL_JOB_STATUSES, ProcessingJob`.
- Produces: dataclass `InstallAccepted(job_id: UUID, status: str)`; class `ReferenceDataInstallService(session_factory)` with `request(owner_id: UUID, units: tuple[InstallUnit, ...], *, trace_id: str) -> InstallAccepted`, `run(job_id: UUID) -> None` (implemented in Task 4), and `status() -> tuple[dict[str, object], object | None]` returning `(release_status() dict, JobProgress | None)`.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/integration/test_reference_data_install_service.py`:

```python
from __future__ import annotations

from uuid import UUID

import pytest
from sqlalchemy import select

from cookfully.application.reference_data import (
    INSTALL_JOB_KIND,
    ReferenceDataInstallService,
)
from cookfully.domain.common import DomainError
from cookfully.infrastructure.models.jobs import ProcessingJob
from cookfully.infrastructure.models.reference_data_installs import ReferenceDataInstall

OWNER = UUID("0198b100-0000-7000-8000-000000000001")


def test_request_creates_install_row_and_job_with_extended_deadline(
    session_factory,
) -> None:
    service = ReferenceDataInstallService(session_factory)
    accepted = service.request(OWNER, ("foundation_sr_legacy",), trace_id="trace-12345678")
    assert accepted.status == "queued"
    with session_factory() as session:
        install = session.scalar(
            select(ReferenceDataInstall).where(ReferenceDataInstall.owner_id == OWNER)
        )
        job = session.get(ProcessingJob, accepted.job_id)
    assert install is not None
    assert install.datasets == ["foundation_sr_legacy"]
    assert install.input_hash.startswith("sha256:")
    assert job is not None
    assert job.kind == INSTALL_JOB_KIND
    assert job.aggregate_type == "reference_data"
    assert job.aggregate_id == install.id
    assert job.terminal_deadline_at - job.accepted_at >= __import__(
        "datetime"
    ).timedelta(hours=6)


def test_second_request_while_in_flight_is_rejected(session_factory) -> None:
    service = ReferenceDataInstallService(session_factory)
    service.request(OWNER, ("foundation_sr_legacy",), trace_id="trace-12345678")
    with pytest.raises(DomainError) as raised:
        service.request(OWNER, ("branded",), trace_id="trace-12345678")
    assert raised.value.code == "install_in_flight"


def test_request_rejects_unknown_units_and_empty_selection(session_factory) -> None:
    service = ReferenceDataInstallService(session_factory)
    with pytest.raises(DomainError) as raised:
        service.request(OWNER, ("not_a_unit",), trace_id="trace-12345678")  # type: ignore[arg-type]
    assert raised.value.code == "install_unit_invalid"
    with pytest.raises(DomainError):
        service.request(OWNER, (), trace_id="trace-12345678")  # type: ignore[arg-type]


def test_status_reports_missing_datasets_and_no_job_before_first_request(
    session_factory,
) -> None:
    service = ReferenceDataInstallService(session_factory)
    releases, job = service.status()
    assert releases["available"] is False
    assert set(releases["missing"]) == {"foundation", "sr_legacy"}
    assert job is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --directory backend pytest tests/integration/test_reference_data_install_service.py -v`
Expected: FAIL with `AttributeError` / `NameError` (service missing).

- [ ] **Step 3: Implement the service (request + status; run stub raises NotImplemented)**

Append to `backend/src/cookfully/application/reference_data.py`:

```python
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from cookfully.application.jobs import JobService
from cookfully.cli.reference_data import release_status
from cookfully.domain.common import DomainError, utc_now, uuid7
from cookfully.infrastructure.models.jobs import NONTERMINAL_JOB_STATUSES, ProcessingJob
from cookfully.infrastructure.models.reference_data_installs import ReferenceDataInstall

INSTALL_LOCK_KEY = 701937


class ReferenceDataInstallService:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory
        self._jobs = JobService(session_factory)

    def request(
        self,
        owner_id: UUID,
        units: tuple[InstallUnit, ...],
        *,
        trace_id: str,
    ) -> InstallAccepted:
        requested = frozenset(units)
        if not requested:
            raise DomainError("install_units_required", "Choose at least one dataset unit.", 422)
        unknown = requested - PINNED_RELEASES.keys()
        if unknown:
            raise DomainError(
                "install_unit_invalid", f"Unknown dataset unit: {sorted(unknown)[0]}", 422
            )
        ordered = tuple(unit for unit in ("foundation_sr_legacy", "branded") if unit in requested)
        input_hash = install_input_hash(ordered)
        now = utc_now()
        with self._session_factory.begin() as session:
            session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": INSTALL_LOCK_KEY})
            in_flight = session.scalar(
                select(ProcessingJob)
                .where(
                    ProcessingJob.kind == INSTALL_JOB_KIND,
                    ProcessingJob.status.in_(NONTERMINAL_JOB_STATUSES),
                )
                .limit(1)
            )
            if in_flight is not None:
                raise DomainError(
                    "install_in_flight", "A USDA data install is already running.", 409
                )
            install = ReferenceDataInstall(
                id=uuid7(),
                owner_id=owner_id,
                input_hash=input_hash,
                datasets=list(ordered),
                status="queued",
            )
            session.add(install)
            session.flush()
            job = self._jobs.accept_in_session(
                session,
                kind=INSTALL_JOB_KIND,
                aggregate_type="reference_data",
                aggregate_id=install.id,
                input_hash=input_hash,
                trace_id=trace_id,
                now=now,
            )
            job.terminal_deadline_at = now + INSTALL_JOB_DEADLINE
            install.job_id = job.id
            return InstallAccepted(job.id, job.status)

    def run(self, job_id: UUID) -> None:
        raise NotImplementedError

    def status(self) -> tuple[dict[str, object], object | None]:
        releases = release_status()
        with self._session_factory() as session:
            latest = session.scalar(
                select(ProcessingJob)
                .where(ProcessingJob.kind == INSTALL_JOB_KIND)
                .order_by(ProcessingJob.accepted_at.desc())
                .limit(1)
            )
        progress = self._jobs.progress(latest.id) if latest is not None else None
        return releases, progress
```

Also add the `InstallAccepted` dataclass and the missing `select` import to the top of the module:

```python
from sqlalchemy import select
```

and:

```python
@dataclass(frozen=True, slots=True)
class InstallAccepted:
    job_id: UUID
    status: str
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --directory backend pytest tests/integration/test_reference_data_install_service.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/src/cookfully/application/reference_data.py backend/tests/integration/test_reference_data_install_service.py
git commit -m "feat: reference data install request with single-install guard"
```

---

### Task 4: Install service — worker run (download, import, activate, cleanup, heartbeat)

**Files:**
- Modify: `backend/src/cookfully/application/reference_data.py`
- Test: `backend/tests/integration/test_reference_data_install_run.py`

**Interfaces:**
- Consumes: Task 1 constants; `cookfully.cli.reference_data.import_release, activate_release`; `JobService.claim, heartbeat, update_progress, succeed, fail_attempt, supersede`; module-level `download_archive(url: str, destination: Path) -> None` (added here; monkeypatched in tests).
- Produces: `download_archive` (HTTPX streaming to `destination`); `run(job_id)` behavior: claim → load install row → per unit download/import/activate → percent progress → cleanup in `finally` → succeed/fail. Retryable codes: `download_failed`, `network_timeout`. Heartbeat every `HEARTBEAT_INTERVAL` while working via a daemon thread.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/integration/test_reference_data_install_run.py`:

```python
from __future__ import annotations

import json
import zipfile
from datetime import date
from pathlib import Path
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from cookfully.application import reference_data as app_reference_data
from cookfully.application.reference_data import ReferenceDataInstallService
from cookfully.cli import reference_data as cli_reference_data
from cookfully.infrastructure.config import Settings
from cookfully.infrastructure.models.jobs import ProcessingJob
from cookfully.infrastructure.models.reference_foods import FoodReference, ReferenceDataset

OWNER = UUID("0198b100-1111-7111-8111-111111111111")


def write_fixture_zip(path: Path, fdc_id: int, description: str) -> None:
    payload = {
        "foods": [
            {
                "fdcId": fdc_id,
                "description": description,
                "dataType": "Foundation",
                "foodCategory": {"description": "Test foods"},
                "foodNutrients": [
                    {
                        "nutrient": {"number": "1008", "unitName": "KCAL"},
                        "amount": 123.4567895,
                    }
                ],
            }
        ]
    }
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("foods.json", json.dumps(payload))


def test_run_downloads_imports_activates_and_reports_full_progress(
    isolated_database_url: str,
    session_factory: sessionmaker[Session],
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        cli_reference_data,
        "get_settings",
        lambda: Settings(database_url=isolated_database_url, environment="test"),
    )
    fixture = tmp_path / "foundation.zip"
    write_fixture_zip(fixture, 1001, "Chicken breast")
    download_targets: list[tuple[str, Path]] = []

    def fake_download(url: str, destination: Path) -> None:
        download_targets.append((url, destination))
        destination.write_bytes(fixture.read_bytes())

    monkeypatch.setattr(app_reference_data, "download_archive", fake_download)
    service = ReferenceDataInstallService(session_factory)
    accepted = service.request(OWNER, ("foundation_sr_legacy",), trace_id="trace-12345678")
    service.run(accepted.job_id)

    with session_factory() as session:
        job = session.get(ProcessingJob, accepted.job_id)
        assert job is not None and job.status == "succeeded"
        assert job.progress_current == job.progress_total == 2
        datasets = session.scalars(
            select(ReferenceDataset).where(ReferenceDataset.status == "active")
        ).all()
        assert {item.dataset_type for item in datasets} == {"foundation", "sr_legacy"}
    assert len(download_targets) == 2
    assert all(not destination.exists() for _, destination in download_targets)


def test_run_skips_already_installed_releases_and_cleans_temp_files(
    isolated_database_url: str,
    session_factory: sessionmaker[Session],
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        cli_reference_data,
        "get_settings",
        lambda: Settings(database_url=isolated_database_url, environment="test"),
    )
    fixture = tmp_path / "foundation.zip"
    write_fixture_zip(fixture, 1001, "Chicken breast")
    downloads: list[tuple[str, Path]] = []

    def fake_download(url: str, destination: Path) -> None:
        downloads.append((url, destination))
        destination.write_bytes(fixture.read_bytes())

    monkeypatch.setattr(app_reference_data, "download_archive", fake_download)
    service = ReferenceDataInstallService(session_factory)
    first = service.request(OWNER, ("foundation_sr_legacy",), trace_id="trace-12345678")
    service.run(first.job_id)
    first_count = len(downloads)
    second = service.request(OWNER, ("foundation_sr_legacy",), trace_id="trace-12345678")
    service.run(second.job_id)
    assert len(downloads) == first_count
    with session_factory() as session:
        job = session.get(ProcessingJob, second.job_id)
        assert job is not None and job.status == "succeeded"
        assert job.progress_current == 2


def test_run_fails_safely_on_download_error_leaving_zero_rows(
    isolated_database_url: str,
    session_factory: sessionmaker[Session],
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        cli_reference_data,
        "get_settings",
        lambda: Settings(database_url=isolated_database_url, environment="test"),
    )
    downloads: list[tuple[str, Path]] = []

    def failing_download(url: str, destination: Path) -> None:
        downloads.append((url, destination))
        raise OSError("disk full")

    monkeypatch.setattr(app_reference_data, "download_archive", failing_download)
    service = ReferenceDataInstallService(session_factory)
    accepted = service.request(OWNER, ("foundation_sr_legacy",), trace_id="trace-12345678")
    service.run(accepted.job_id)
    with session_factory() as session:
        job = session.get(ProcessingJob, accepted.job_id)
        assert job is not None and job.status == "retry_wait"
        assert job.failure_code == "download_failed"
        assert session.scalar(select(FoodReference).limit(1)) is None
    assert all(not destination.exists() for _, destination in downloads)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --directory backend pytest tests/integration/test_reference_data_install_run.py -v`
Expected: FAIL (run raises NotImplementedError).

- [ ] **Step 3: Implement `download_archive`, the heartbeat thread, and `run`**

Add to `backend/src/cookfully/application/reference_data.py` (imports: `logging`, `tempfile`, `threading`, `httpx`, `Path`, `datetime` for the logger/timer; `import_release, activate_release` from the cli module; `cookfully.domain.common.DomainError` already present):

```python
import logging
import tempfile
import threading
from pathlib import Path

import httpx

from cookfully.application.jobs import JobService
from cookfully.cli.reference_data import activate_release, import_release, release_status

logger = logging.getLogger(__name__)
RETRYABLE_CODES = frozenset({"download_failed", "network_timeout"})


def download_archive(url: str, destination: Path) -> None:
    timeout = httpx.Timeout(connect=20.0, read=60.0, write=60.0, pool=20.0)
    try:
        with httpx.stream("GET", url, follow_redirects=True, timeout=timeout) as response:
            response.raise_for_status()
            with destination.open("wb") as handle:
                for chunk in response.iter_bytes():
                    handle.write(chunk)
    except httpx.HTTPStatusError as exc:
        raise DomainError(
            "download_failed",
            f"USDA download returned HTTP {exc.response.status_code}.",
            502,
        ) from exc
    except httpx.TransportError as exc:
        raise DomainError("download_failed", "USDA download failed to transfer.", 502) from exc


class _Heartbeat(threading.Thread):
    def __init__(self, jobs: JobService, job_id: UUID, interval: timedelta) -> None:
        super().__init__(daemon=True)
        self._jobs = jobs
        self._job_id = job_id
        self._interval = interval.total_seconds()
        self._stop = threading.Event()

    def run(self) -> None:
        while not self._stop.wait(self._interval):
            try:
                self._jobs.heartbeat(self._job_id)
            except Exception:
                return

    def stop(self) -> None:
        self._stop.set()
```

Replace the `run` stub in `ReferenceDataInstallService` with:

```python
    def run(self, job_id: UUID) -> None:
        job = self._jobs.claim(job_id)
        if job.status != "running":
            return
        with self._session_factory() as session:
            install = session.get(ReferenceDataInstall, job.aggregate_id)
            if install is None or install.input_hash != job.input_hash:
                self._jobs.supersede(job_id)
                return
            units = tuple(install.datasets)
        heartbeat = _Heartbeat(self._jobs, job_id, HEARTBEAT_INTERVAL)
        heartbeat.start()
        try:
            self._install_units(job_id, units)
            self._jobs.succeed(job_id)
        except DomainError as exc:
            self._jobs.fail_attempt(
                job_id,
                exc.code,
                retryable=exc.code in RETRYABLE_CODES,
                safe_message=exc.safe_message,
            )
        except Exception:
            logger.exception(
                "reference data install failed",
                extra={"job_id": str(job_id)},
            )
            self._jobs.fail_attempt(
                job_id,
                "install_failed",
                retryable=True,
                safe_message="USDA data install failed safely.",
            )
        finally:
            heartbeat.stop()

    def _install_units(self, job_id: UUID, units: tuple[str, ...]) -> None:
        releases = tuple(
            release for unit in units for release in PINNED_RELEASES[unit]
        )
        total = len(releases)
        completed = 0
        self._jobs.update_progress(job_id, completed, total)
        for release in releases:
            if self._installed(release):
                completed += 1
                self._jobs.update_progress(job_id, completed, total)
                continue
            destination = Path(tempfile.gettempdir()) / f"usda-{release.dataset_type}-{uuid7()}.zip"
            try:
                download_archive(release.source_url, destination)
                imported = import_release(
                    destination,
                    dataset_type=release.dataset_type,
                    release_id=release.release_id,
                    released_on=release.released_on,
                    source_url=release.source_url,
                )
                activate_release(str(imported.id))
            finally:
                destination.unlink(missing_ok=True)
            completed += 1
            self._jobs.update_progress(job_id, completed, total)

    def _installed(self, release: PinnedRelease) -> bool:
        with self._session_factory() as session:
            return (
                session.scalar(
                    select(ReferenceDataset).where(
                        ReferenceDataset.provider == "usda_fdc",
                        ReferenceDataset.dataset_type == release.dataset_type,
                        ReferenceDataset.release_id == release.release_id,
                        ReferenceDataset.status.in_(("ready", "active")),
                    )
                )
                is not None
            )
```

Also add `from cookfully.infrastructure.models.reference_foods import ReferenceDataset` to the imports of `reference_data.py`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --directory backend pytest tests/integration/test_reference_data_install_run.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Run the existing reference-data integration tests for regressions**

Run: `uv run --directory backend pytest tests/integration/test_reference_data.py tests/integration/test_job_lifecycle.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/src/cookfully/application/reference_data.py backend/tests/integration/test_reference_data_install_run.py
git commit -m "feat: background USDA install with progress, heartbeat, and cleanup"
```

---

### Task 5: Job dispatcher wiring

**Files:**
- Create: `backend/src/cookfully/jobs/reference_data_install.py`
- Modify: `backend/src/cookfully/jobs/tasks.py`

**Interfaces:**
- Consumes: `ReferenceDataInstallService.run`; the Celery dispatcher envelope pattern in `tasks.py`.
- Produces: `run_reference_data_install_job(session_factory, job_id) -> None`; dispatcher case for kind `"reference_data_install"`.

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/integration/test_reference_data_install_run.py`:

```python
def test_dispatcher_routes_install_kind_to_the_service(
    isolated_database_url: str,
    session_factory: sessionmaker[Session],
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        cli_reference_data,
        "get_settings",
        lambda: Settings(database_url=isolated_database_url, environment="test"),
    )
    fixture = tmp_path / "foundation.zip"
    write_fixture_zip(fixture, 1001, "Chicken breast")

    def fake_download(url: str, destination: Path) -> None:
        destination.write_bytes(fixture.read_bytes())

    monkeypatch.setattr(app_reference_data, "download_archive", fake_download)
    service = ReferenceDataInstallService(session_factory)
    accepted = service.request(OWNER, ("foundation_sr_legacy",), trace_id="trace-12345678")
    from cookfully.jobs.reference_data_install import run_reference_data_install_job

    run_reference_data_install_job(session_factory, accepted.job_id)
    with session_factory() as session:
        job = session.get(ProcessingJob, accepted.job_id)
        assert job is not None and job.status == "succeeded"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run --directory backend pytest tests/integration/test_reference_data_install_run.py::test_dispatcher_routes_install_kind_to_the_service -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Create the handler and register the kind**

Create `backend/src/cookfully/jobs/reference_data_install.py`:

```python
from uuid import UUID

from sqlalchemy.orm import Session, sessionmaker

from cookfully.application.reference_data import ReferenceDataInstallService


def run_reference_data_install_job(
    session_factory: sessionmaker[Session], job_id: UUID
) -> None:
    """Run an idempotent USDA reference data install through the shared worker boundary."""

    ReferenceDataInstallService(session_factory).run(job_id)
```

Modify `backend/src/cookfully/jobs/tasks.py`:

- Add import after line 12 (`from cookfully.jobs.suggestions import run_suggestion_job`):

```python
from cookfully.jobs.reference_data_install import run_reference_data_install_job
```

- Add the dispatcher branch after the `suggestion` branch (line 56–57):

```python
        if envelope["kind"] == "reference_data_install":
            run_reference_data_install_job(sessions, UUID(str(envelope["jobId"])))
            return None
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run --directory backend pytest tests/integration/test_reference_data_install_run.py::test_dispatcher_routes_install_kind_to_the_service -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/src/cookfully/jobs/reference_data_install.py backend/src/cookfully/jobs/tasks.py backend/tests/integration/test_reference_data_install_run.py
git commit -m "feat: dispatch reference data install jobs to the worker"
```

---

### Task 6: API routes, schemas, and OpenAPI contract

**Files:**
- Create: `backend/src/cookfully/api/schemas/reference_data.py`
- Create: `backend/src/cookfully/api/routes/reference_data.py`
- Modify: `backend/src/cookfully/api/main.py`
- Modify: `specs/001-nutrition-recipe-planner/contracts/openapi.yaml`
- Test: `backend/tests/contract/test_reference_data_api.py`

**Interfaces:**
- Consumes: `ReferenceDataInstallService` (Task 3–4), `IdempotencyService` + `idempotency_key` from `cookfully.api.routes.recipes`, `require_browser_owner`, `JobAcceptedResponse`, `JobResponse`.
- Produces: `GET /api/v1/reference-data/status` (operationId `get_reference_data_status`) returning `ReferenceDataStatusResponse`; `POST /api/v1/reference-data/install` (operationId `install_reference_data`) returning `JobAcceptedResponse` (202). Schemas: `ReferenceRelease`, `ReferenceDataStatusResponse`, `ReferenceDataInstallRequest`.

- [ ] **Step 1: Write the failing contract tests**

Create `backend/tests/contract/test_reference_data_api.py`:

```python
from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select

from cookfully.api.main import create_app
from cookfully.infrastructure.config import Settings
from cookfully.infrastructure.models.jobs import ProcessingJob


def client_for(isolated_database_url: str, tmp_path: Path) -> TestClient:
    return TestClient(
        create_app(
            Settings(
                environment="test",
                database_url=isolated_database_url,
                owner_email="owner@example.com",
                owner_bootstrap_password="correct horse battery staple",
                media_root=tmp_path / "media",
                export_root=tmp_path / "exports",
                erasure_ledger_root=tmp_path / "ledger",
            )
        )
    )


def authenticate(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/session",
        json={"email": "owner@example.com", "password": "correct horse battery staple"},
    )
    assert response.status_code == 204
    return {"X-CSRF-Token": client.cookies["cookfully_csrf"]}


def test_reference_data_status_and_install_surface(
    isolated_database_url: str, tmp_path: Path
) -> None:
    with client_for(isolated_database_url, tmp_path) as client:
        headers = authenticate(client)
        status = client.get("/api/v1/reference-data/status", headers=headers)
        assert status.status_code == 200
        body = status.json()
        assert body["available"] is False
        assert set(body["missing"]) == {"foundation", "sr_legacy"}
        assert body["releases"] == []
        assert body["job"] is None

        accepted = client.post(
            "/api/v1/reference-data/install",
            headers=headers,
            json={"datasets": ["foundation_sr_legacy"]},
        )
        assert accepted.status_code == 202
        job_id = accepted.json()["jobId"]

        replay = client.post(
            "/api/v1/reference-data/install",
            headers={**headers, "Idempotency-Key": "install-replay-key-0001"},
            json={"datasets": ["foundation_sr_legacy"]},
        )
        assert replay.status_code == 202
        assert replay.json()["jobId"] == job_id

        with client.app.state.sessions() as session:
            job = session.get(ProcessingJob, job_id)
            assert job is not None
            assert job.kind == "reference_data_install"
            assert job.status == "queued"

        running = client.get("/api/v1/reference-data/status", headers=headers)
        assert running.json()["job"]["status"] == "queued"


def test_reference_data_install_rejects_duplicate_in_flight(
    isolated_database_url: str, tmp_path: Path
) -> None:
    with client_for(isolated_database_url, tmp_path) as client:
        headers = authenticate(client)
        first = client.post(
            "/api/v1/reference-data/install",
            headers=headers,
            json={"datasets": ["foundation_sr_legacy"]},
        )
        assert first.status_code == 202
        second = client.post(
            "/api/v1/reference-data/install",
            headers=headers,
            json={"datasets": ["branded"]},
        )
        assert second.status_code == 409
        assert second.json()["code"] == "install_in_flight"
```

Note: the second POST uses a fresh auto-generated idempotency key, so it reaches the service and gets the 409.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --directory backend pytest tests/contract/test_reference_data_api.py -v`
Expected: FAIL with 404 on `/api/v1/reference-data/status`.

- [ ] **Step 3: Create schemas**

Create `backend/src/cookfully/api/schemas/reference_data.py`:

```python
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from cookfully.api.schemas.jobs import JobResponse

InstallUnit = Literal["foundation_sr_legacy", "branded"]


class ReferenceRelease(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    dataset_type: str = Field(alias="datasetType")
    release_id: str = Field(alias="releaseId")
    released_on: str = Field(alias="releasedOn")
    source_url: str = Field(alias="sourceUrl")
    license: str
    review_overdue: bool = Field(alias="reviewOverdue")


class ReferenceDataStatusResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    available: bool
    missing: tuple[str, ...]
    releases: tuple[ReferenceRelease, ...]
    requested_datasets: tuple[str, ...] | None = Field(alias="requestedDatasets", default=None)
    job: JobResponse | None = None


class ReferenceDataInstallRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    datasets: tuple[InstallUnit, ...] = Field(min_length=1)
```

- [ ] **Step 4: Create the route**

Create `backend/src/cookfully/api/routes/reference_data.py`:

```python
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, status

from cookfully.api.dependencies.auth import require_browser_owner
from cookfully.api.routes.recipes import idempotency_key
from cookfully.api.schemas.jobs import JobAcceptedResponse
from cookfully.api.schemas.reference_data import (
    ReferenceDataInstallRequest,
    ReferenceDataStatusResponse,
    ReferenceRelease,
)
from cookfully.application.idempotency import IdempotencyService
from cookfully.application.reference_data import ReferenceDataInstallService
from cookfully.domain.common import DomainError
from cookfully.infrastructure.models.identity import OwnerAccount
from cookfully.infrastructure.observability import correlation_id

router = APIRouter(prefix="/reference-data", tags=["Reference Data"])


def reference_data_service(request: Request) -> ReferenceDataInstallService:
    service: ReferenceDataInstallService = request.app.state.reference_data
    return service


def idempotency_service(request: Request) -> IdempotencyService:
    service: IdempotencyService = request.app.state.idempotency
    return service


@router.get(
    "/status", response_model=ReferenceDataStatusResponse, response_model_by_alias=True
)
def get_reference_data_status(
    service: Annotated[ReferenceDataInstallService, Depends(reference_data_service)],
    _: Annotated[OwnerAccount, Depends(require_browser_owner)],
) -> ReferenceDataStatusResponse:
    releases, progress = service.status()
    return ReferenceDataStatusResponse(
        available=bool(releases["available"]),
        missing=tuple(releases["missing"]),
        releases=tuple(ReferenceRelease.model_validate(item) for item in releases["releases"]),
        requestedDatasets=None,
        job=None,
    )


@router.post(
    "/install",
    response_model=JobAcceptedResponse,
    response_model_by_alias=True,
    status_code=status.HTTP_202_ACCEPTED,
)
def install_reference_data(
    payload: ReferenceDataInstallRequest,
    service: Annotated[ReferenceDataInstallService, Depends(reference_data_service)],
    idempotency: Annotated[IdempotencyService, Depends(idempotency_service)],
    owner: Annotated[OwnerAccount, Depends(require_browser_owner)],
    key: Annotated[str, Depends(idempotency_key)],
) -> JobAcceptedResponse:
    decision = idempotency.begin(
        owner_id=owner.id,
        key=key,
        operation="reference_data.install",
        payload=payload.model_dump(mode="json", by_alias=True),
    )
    if decision.replay:
        if decision.response_body is None:
            raise DomainError(
                "idempotency_response_missing", "Stored response is unavailable.", 500
            )
        return JobAcceptedResponse.model_validate(decision.response_body)
    try:
        accepted = service.request(owner.id, payload.datasets, trace_id=correlation_id.get())
        response = JobAcceptedResponse(job_id=accepted.job_id, status=accepted.status)
    except Exception:
        idempotency.abort(owner_id=owner.id, key=key)
        raise
    idempotency.complete(
        owner_id=owner.id,
        key=key,
        response_status=202,
        resource_id=accepted.job_id,
        job_id=accepted.job_id,
        response_body=response.model_dump(mode="json", by_alias=True),
    )
    return response
```

- [ ] **Step 5: Wire the service and router in `main.py`**

In `backend/src/cookfully/api/main.py`:
- Add `from cookfully.application.reference_data import ReferenceDataInstallService` to the imports.
- After `app.state.exports = ExportJobService(...)` (line 224) add:

```python
            app.state.reference_data = ReferenceDataInstallService(sessions)
```

- After `versioned.include_router(foods.router)` (line 266) add:

```python
    versioned.include_router(reference_data.router)
```

with the corresponding `from cookfully.api.routes import reference_data` import.

- [ ] **Step 6: Update the OpenAPI contract**

In `specs/001-nutrition-recipe-planner/contracts/openapi.yaml`, add these two operations (match the file's existing indentation and conventions):

```yaml
  /reference-data/status:
    get:
      operationId: get_reference_data_status
      tags:
        - Reference Data
      security:
        - cookieAuth: []
      responses:
        "200":
          description: Reference data availability and latest install job.
  /reference-data/install:
    post:
      operationId: install_reference_data
      tags:
        - Reference Data
      security:
        - cookieAuth: []
      responses:
        "202":
          description: Install job accepted.
        "409":
          description: An install is already in flight.
```

- [ ] **Step 7: Run the contract tests**

Run: `uv run --directory backend pytest tests/contract/test_reference_data_api.py tests/contract/test_openapi_compatibility.py -v`
Expected: PASS.

- [ ] **Step 8: Run the full backend suite for regressions**

Run: `uv run --directory backend pytest -q`
Expected: PASS. If `test_openapi_compatibility` reports drift, re-check that the operationIds and paths in the YAML match exactly (path without `/api/v1` prefix in canonical).

- [ ] **Step 9: Commit**

```bash
git add backend/src/cookfully/api/schemas/reference_data.py backend/src/cookfully/api/routes/reference_data.py backend/src/cookfully/api/main.py specs/001-nutrition-recipe-planner/contracts/openapi.yaml backend/tests/contract/test_reference_data_api.py
git commit -m "feat: reference data status and install API endpoints"
```

---

### Task 7: Onboarding reference-data choice (backend)

**Files:**
- Modify: `backend/src/cookfully/infrastructure/models/identity.py`
- Create: `backend/migrations/versions/0016_onboarding_reference_choice.py`
- Modify: `backend/src/cookfully/application/owner_onboarding.py`
- Modify: `backend/src/cookfully/api/routes/owner.py`
- Test: extend `backend/tests/contract/test_account_session_api.py` (add one test) — or create `backend/tests/contract/test_onboarding_choice.py`

**Interfaces:**
- Consumes: existing `OwnerOnboardingState`, `OwnerOnboardingService`.
- Produces: `reference_data_choice` column (`String(32)`, nullable) on `owner_onboarding_states`; `OwnerOnboardingService.resolve(..., reference_data_choice: str | None = None)`; `OnboardingStateRead.reference_data_choice`; API field `referenceDataChoice` on the onboarding GET/PUT (nullable; accepted values `both | foundation_sr_legacy | none`).

- [ ] **Step 1: Write the failing test**

Create `backend/tests/contract/test_onboarding_choice.py`:

```python
from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from cookfully.api.main import create_app
from cookfully.infrastructure.config import Settings


def client_for(isolated_database_url: str, tmp_path: Path) -> TestClient:
    return TestClient(
        create_app(
            Settings(
                environment="test",
                database_url=isolated_database_url,
                owner_email="owner@example.com",
                owner_bootstrap_password="correct horse battery staple",
                media_root=tmp_path / "media",
                export_root=tmp_path / "exports",
                erasure_ledger_root=tmp_path / "ledger",
            )
        )
    )


def authenticate(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/session",
        json={"email": "owner@example.com", "password": "correct horse battery staple"},
    )
    assert response.status_code == 204
    return {"X-CSRF-Token": client.cookies["cookfully_csrf"]}


def test_onboarding_persists_reference_data_choice(
    isolated_database_url: str, tmp_path: Path
) -> None:
    with client_for(isolated_database_url, tmp_path) as client:
        headers = authenticate(client)
        onboarding = client.get("/api/v1/owner/onboarding", headers=headers)
        assert onboarding.status_code == 200
        version = onboarding.json()["version"]

        resolved = client.put(
            "/api/v1/owner/onboarding",
            headers=headers,
            json={
                "state": "completed",
                "referenceDataChoice": "foundation_sr_legacy",
                "version": version,
            },
        )
        assert resolved.status_code == 200
        assert resolved.json()["referenceDataChoice"] == "foundation_sr_legacy"

        reloaded = client.get("/api/v1/owner/onboarding", headers=headers)
        assert reloaded.json()["referenceDataChoice"] == "foundation_sr_legacy"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run --directory backend pytest tests/contract/test_onboarding_choice.py -v`
Expected: FAIL — the response has no `referenceDataChoice` field (422 or missing attribute).

- [ ] **Step 3: Add the column to the model**

In `backend/src/cookfully/infrastructure/models/identity.py`, inside `OwnerOnboardingState` after `first_action` (line 62):

```python
    reference_data_choice: Mapped[str | None] = mapped_column(String(32))
```

- [ ] **Step 4: Create the migration**

Create `backend/migrations/versions/0016_onboarding_reference_choice.py`:

```python
"""Onboarding reference-data choice."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0016_onboarding_reference_choice"
down_revision: str | None = "0015_reference_data_install"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "owner_onboarding_states", sa.Column("reference_data_choice", sa.String(32))
    )


def downgrade() -> None:
    op.drop_column("owner_onboarding_states", "reference_data_choice")
```

- [ ] **Step 5: Extend the application service**

In `backend/src/cookfully/application/owner_onboarding.py`:
- Add `reference_data_choice: str | None` to `OnboardingStateRead`.
- Extend `resolve` signature with `reference_data_choice: str | None = None` and store it:

```python
            value.reference_data_choice = reference_data_choice
```

- Extend `_read` to pass `value.reference_data_choice` through.

- [ ] **Step 6: Extend the route schema**

In `backend/src/cookfully/api/routes/owner.py`:
- Add to `OwnerOnboarding`:

```python
    reference_data_choice: Literal["both", "foundation_sr_legacy", "none"] | None = Field(
        alias="referenceDataChoice", default=None
    )
```

- Pass the field through in `get_onboarding` and `resolve_onboarding` responses, and forward it in `resolve_onboarding`:

```python
        reference_data_choice=payload.reference_data_choice,
```

- [ ] **Step 7: Run the tests**

Run: `uv run --directory backend pytest tests/contract/test_onboarding_choice.py tests/contract/test_account_session_api.py -q`
Expected: PASS.

- [ ] **Step 8: Run the full backend suite**

Run: `uv run --directory backend pytest -q`
Expected: PASS (including the OpenAPI drift test — onboarding schema is not part of the operation set).

- [ ] **Step 9: Commit**

```bash
git add backend/src/cookfully/infrastructure/models/identity.py backend/migrations/versions/0016_onboarding_reference_choice.py backend/src/cookfully/application/owner_onboarding.py backend/src/cookfully/api/routes/owner.py backend/tests/contract/test_onboarding_choice.py
git commit -m "feat: persist onboarding reference-data choice"
```

---

### Task 8: Frontend — regenerated client, reference data API, Nutrition data tab

**Files:**
- Regenerate: `frontend/src/app/api/generated/schema.ts`
- Create: `frontend/src/features/referenceData/api.ts`
- Create: `frontend/src/features/referenceData/NutritionDataTab.tsx`
- Modify: `frontend/src/features/settings/SettingsPage.tsx`
- Create: `frontend/src/features/referenceData/__tests__/NutritionDataTab.test.tsx`
- Modify: `frontend/src/features/settings/__tests__/SettingsPage.test.tsx`

**Interfaces:**
- Consumes: generated `components["schemas"]["ReferenceDataStatusResponse"]`, `components["schemas"]["ReferenceDataInstallRequest"]`, `components["schemas"]["JobAccepted"]`, `components["schemas"]["Job"]`; `apiRequest` from `frontend/src/features/recipes/api.ts`; `Button`, `PageHeader` from `frontend/src/components`.
- Produces: `referenceDataApi.status()` and `referenceDataApi.install(datasets: ("foundation_sr_legacy" | "branded")[])`; `NutritionDataTab` component (self-contained status card + install buttons + progress + retry); a new Settings tab `{ id: "data", label: "Nutrition data", description: "USDA reference foods", Icon: Database }`.

- [ ] **Step 1: Regenerate the TypeScript client**

Dump the runtime OpenAPI document and regenerate:

```powershell
uv run --directory backend python -c "import json; from cookfully.api.main import create_app; print(json.dumps(create_app().openapi()))" > "$env:TEMP\cookfully-openapi.json"
pnpm --dir frontend exec openapi-typescript "$env:TEMP\cookfully-openapi.json" -o src/app/api/generated/schema.ts
```

Run: `pnpm --dir frontend typecheck`
Expected: PASS; `schema.ts` now contains `ReferenceDataStatusResponse`, `ReferenceRelease`, and `ReferenceDataInstallRequest` components.

- [ ] **Step 2: Write the failing tests**

Create `frontend/src/features/referenceData/__tests__/NutritionDataTab.test.tsx`:

```tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { NutritionDataTab } from "../NutritionDataTab";

function json(value: unknown) {
  return { ok: true, status: 200, json: async () => value } as Response;
}

function renderTab() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <NutritionDataTab />
    </QueryClientProvider>
  );
}

describe("NutritionDataTab", () => {
  it("shows missing datasets and install buttons when nothing is installed", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => json({
      available: false,
      missing: ["foundation", "sr_legacy"],
      releases: [],
      requestedDatasets: null,
      job: null,
    })));
    renderTab();
    expect(await screen.findByText("Foundation + SR Legacy")).toBeVisible();
    expect(screen.getByRole("button", { name: "Install Foundation + SR Legacy" })).toBeVisible();
    expect(screen.getByRole("button", { name: "Install Branded foods" })).toBeVisible();
  });

  it("shows active releases with license and disables installed buttons", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => json({
      available: true,
      missing: [],
      releases: [
        { datasetType: "foundation", releaseId: "foundation-2024-04", releasedOn: "2024-04-18", sourceUrl: "https://fdc.nal.usda.gov/fdc-datasets.html", license: "CC0-1.0", reviewOverdue: false },
        { datasetType: "sr_legacy", releaseId: "sr-legacy-2018-04", releasedOn: "2018-04-01", sourceUrl: "https://fdc.nal.usda.gov/fdc-datasets.html", license: "CC0-1.0", reviewOverdue: false },
      ],
      requestedDatasets: null,
      job: null,
    })));
    renderTab();
    expect(await screen.findByText("CC0-1.0")).toBeVisible();
    expect(screen.getByRole("button", { name: "Install Foundation + SR Legacy" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Install Branded foods" })).toBeEnabled();
  });

  it("posts the selected datasets on install", async () => {
    const fetchMock = vi.fn(async () => json({
      available: false, missing: ["foundation", "sr_legacy"], releases: [],
      requestedDatasets: null, job: null,
    }));
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    renderTab();
    await screen.findByText("Foundation + SR Legacy");
    await user.click(screen.getByRole("button", { name: "Install Foundation + SR Legacy" }));
    await waitFor(() => {
      const call = fetchMock.mock.calls.find(([input]) => String(input).includes("/reference-data/install"));
      expect(call).toBeDefined();
      const [, init] = call as [unknown, RequestInit];
      expect(init.method).toBe("POST");
      expect(JSON.parse(String(init.body))).toEqual({ datasets: ["foundation_sr_legacy"] });
    });
  });

  it("shows progress while a job is running", async () => {
    let calls = 0;
    vi.stubGlobal("fetch", vi.fn(async () => {
      calls += 1;
      return json({
        available: false, missing: ["foundation", "sr_legacy"], releases: [],
        requestedDatasets: ["foundation_sr_legacy"],
        job: {
          id: "00000000-0000-4000-8000-000000000001", kind: "reference_data_install",
          aggregateId: "00000000-0000-4000-8000-000000000002", status: "running", attempt: 1,
          maxAttempts: 5, inputHash: "sha256:abc", progressCurrent: 1, progressTotal: 2,
          nextRetryAt: null, terminalDeadlineAt: "2026-08-15T00:00:00Z",
          failureCode: null, failureMessage: null, createdAt: "2026-08-15T00:00:00Z",
          finishedAt: null, pollAfterSeconds: 2, recoveryActions: [],
        },
      });
    }));
    renderTab();
    expect(await screen.findByText(/Installing/)).toBeVisible();
    expect(calls).toBeGreaterThanOrEqual(1);
  });
});
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `pnpm --dir frontend test --run src/features/referenceData/__tests__/NutritionDataTab.test.tsx`
Expected: FAIL with `ModuleNotFoundError`-style resolution error (`Cannot find module '../NutritionDataTab'`).

- [ ] **Step 4: Create the API module**

Create `frontend/src/features/referenceData/api.ts`:

```ts
import { apiRequest } from "../recipes/api";
import type { JobAccepted } from "../recipes/types";
import type { components } from "../../app/api/generated/schema";

export type ReferenceDataStatus = components["schemas"]["ReferenceDataStatusResponse"];
export type InstallUnit = "foundation_sr_legacy" | "branded";

export const referenceDataApi = {
  status() {
    return apiRequest<ReferenceDataStatus>("/reference-data/status");
  },
  install(datasets: InstallUnit[]) {
    return apiRequest<JobAccepted>("/reference-data/install", {
      method: "POST",
      idempotent: true,
      body: JSON.stringify({ datasets }),
    });
  },
};
```

- [ ] **Step 5: Create the NutritionDataTab component**

Create `frontend/src/features/referenceData/NutritionDataTab.tsx`:

```tsx
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Database, Download, LoaderCircle } from "lucide-react";
import { Button } from "../../components";
import { referenceDataApi, type InstallUnit } from "./api";
import { ApiProblem } from "../recipes/api";

const ACTIVE_STATUSES = new Set(["queued", "running", "retry_wait"]);

const UNITS: { unit: InstallUnit; title: string; blurb: string; size: string; datasets: InstallUnit[] }[] = [
  {
    unit: "foundation_sr_legacy",
    title: "Foundation + SR Legacy",
    blurb: "About 10,000 whole foods and ingredients — the two databases behind the nutrition engine. Recommended for everyday cooking.",
    size: "~100 MB download",
    datasets: ["foundation_sr_legacy"],
  },
  {
    unit: "branded",
    title: "Branded foods",
    blurb: "Packaged gym products — protein powders, bars, Greek yogurt, nut butters — with brand names and serving sizes.",
    size: "~1.5 GB download",
    datasets: ["branded"],
  },
];

export function NutritionDataTab() {
  const queryClient = useQueryClient();
  const status = useQuery({
    queryKey: ["reference-data-status"],
    queryFn: referenceDataApi.status,
    refetchInterval: (query) => {
      const job = query.state.data?.job;
      if (!job || !ACTIVE_STATUSES.has(job.status)) return false;
      return 2_000;
    },
  });
  const install = useMutation({
    mutationFn: (datasets: InstallUnit[]) => referenceDataApi.install(datasets),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["reference-data-status"] });
    },
  });

  const job = status.data?.job;
  const working = job !== undefined && job !== null && ACTIVE_STATUSES.has(job.status);
  const progress =
    job?.progressTotal && job.progressTotal > 0
      ? Math.round(((job.progressCurrent ?? 0) / job.progressTotal) * 100)
      : 0;
  const requested = new Set(status.data?.requestedDatasets ?? []);

  return (
    <section className="settings-section" aria-labelledby="nutrition-data-title">
      <h2 id="nutrition-data-title">Nutrition reference data</h2>
      <p>
        USDA FoodData Central powers ingredient matching. Without it, nutrition estimates cannot
        resolve any ingredient; with it, macros and micronutrients are estimated from official
        laboratory data.
      </p>
      {working && job ? (
        <div className="settings-card" role="status">
          <p className="settings-card__title">
            <LoaderCircle aria-hidden="true" className="spin" /> Installing USDA data… {progress}%
          </p>
          <progress aria-label="USDA data install progress" max={100} value={progress}>
            {progress}%
          </progress>
        </div>
      ) : null}
      {job?.status === "failed" ? (
        <div className="settings-card" role="alert">
          <p className="settings-card__title">Install failed</p>
          <p>{job.failureMessage ?? "The download could not be completed."}</p>
          <Button
            variant="secondary"
            onClick={() => install.mutate(Array.from(requested) as InstallUnit[])}
            disabled={install.isPending || requested.size === 0}
          >
            <Download aria-hidden="true" /> Retry
          </Button>
        </div>
      ) : null}
      <div className="settings-card">
        {UNITS.map(({ unit, title, blurb, size, datasets }) => {
          const installed = requested.has(unit) && job?.status === "succeeded";
          const active = status.data?.releases.some((release) =>
            unit === "foundation_sr_legacy"
              ? release.datasetType === "foundation" || release.datasetType === "sr_legacy"
              : release.datasetType === "branded_food"
          );
          return (
            <div key={unit} className="reference-data-unit">
              <div>
                <p className="settings-card__title">
                  <Database aria-hidden="true" /> {title}
                </p>
                <p>{blurb}</p>
                <p className="muted">{size}</p>
              </div>
              <Button
                variant="secondary"
                onClick={() => install.mutate(datasets)}
                disabled={Boolean(active) || working || install.isPending}
              >
                {active ? "Installed" : `Install ${title}`}
              </Button>
            </div>
          );
        })}
      </div>
      {status.data?.releases.length ? (
        <div className="settings-card">
          <p className="settings-card__title">Active releases</p>
          <ul>
            {status.data.releases.map((release) => (
              <li key={release.datasetType}>
                {release.datasetType} — {release.releaseId} — {release.license}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      {install.error instanceof ApiProblem ? (
        <p className="error-text" role="alert">{install.error.message}</p>
      ) : null}
    </section>
  );
}
```

Note: if the project has no `.spin` animation class, define the button/progress styles with the existing `settings-*` classes and drop the `spin` class name (lint must pass with `--max-warnings=0`).

- [ ] **Step 6: Add the Settings tab**

Modify `frontend/src/features/settings/SettingsPage.tsx`:
- Import `Database` from `lucide-react` and `NutritionDataTab` from `../referenceData/NutritionDataTab`.
- Add to `TABS`:

```tsx
  { id: "data", label: "Nutrition data", description: "USDA reference foods", Icon: Database },
```

- Add the panel after the `api` branch:

```tsx
        {tab === "data" ? (
          <div id="settings-panel-data" role="tabpanel" aria-labelledby="settings-tab-data">
            <NutritionDataTab />
          </div>
        ) : null}
```

Update `frontend/src/features/settings/__tests__/SettingsPage.test.tsx`:
- Change the first test title to `"renders Account, Security, Connections, and Nutrition data tabs and edits account details"` and add after the Connections assertion:

```tsx
    expect(screen.getByRole("tab", { name: "Nutrition data" })).toBeVisible();
```

- [ ] **Step 7: Run the frontend tests**

Run: `pnpm --dir frontend test --run`
Expected: PASS (new tab tests + updated SettingsPage test).

- [ ] **Step 8: Lint, typecheck, and build**

Run: `pnpm --dir frontend lint`, `pnpm --dir frontend typecheck`, `pnpm --dir frontend build`
Expected: all PASS.

- [ ] **Step 9: Commit**

```bash
git add frontend/src/app/api/generated/schema.ts frontend/src/features/referenceData frontend/src/features/settings/SettingsPage.tsx frontend/src/features/settings/__tests__/SettingsPage.test.tsx
git commit -m "feat: Nutrition data settings tab with USDA install controls"
```

---

### Task 9: Frontend — onboarding nutrition step

**Files:**
- Modify: `frontend/src/features/onboarding/types.ts`
- Modify: `frontend/src/features/onboarding/api.ts`
- Modify: `frontend/src/features/onboarding/FirstRunJourney.tsx`
- Modify: `frontend/src/features/onboarding/__tests__/FirstRunJourney.test.tsx`

**Interfaces:**
- Consumes: `onboardingApi.resolve` (extended with `referenceDataChoice`), `referenceDataApi.install` (Task 8), `Button`/`KitchenCompanion` components.
- Produces: `OnboardingState.referenceDataChoice: "both" | "foundation_sr_legacy" | "none" | null`; a second onboarding screen "Real nutrition numbers?" reachable via a "Set up nutrition data" action; choice flow: persist choice → fire install when not `none` → continue to the library (never blocked by install failure).

- [ ] **Step 1: Write the failing tests**

Modify `frontend/src/features/onboarding/__tests__/FirstRunJourney.test.tsx` — add:

```tsx
  it("guides the nutrition choice and installs in the background without blocking", async () => {
    const putBodies: unknown[] = [];
    const postBodies: unknown[] = [];
    fetchMock.mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/owner/onboarding") && init?.method === "PUT") {
        putBodies.push(JSON.parse(String(init.body)));
        return response({ state: "completed", firstAction: null, referenceDataChoice: "foundation_sr_legacy", resolvedAt: "2026-08-13T00:00:00Z", version: 2 });
      }
      if (url.endsWith("/reference-data/install") && init?.method === "POST") {
        postBodies.push(JSON.parse(String(init.body)));
        return response({ jobId: "00000000-0000-4000-8000-000000000009", status: "queued" });
      }
      return response({ state: "pending", firstAction: null, resolvedAt: null, version: 1 });
    });
    const user = userEvent.setup();
    renderJourney();
    await user.click(await screen.findByRole("button", { name: "Set up nutrition data" }));
    expect(screen.getByRole("heading", { name: "Real nutrition numbers?" })).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Foundation + SR Legacy only" }));
    await waitFor(() => {
      expect(putBodies).toEqual([expect.objectContaining({ state: "completed", referenceDataChoice: "foundation_sr_legacy" })]);
      expect(postBodies).toEqual([{ datasets: ["foundation_sr_legacy"] }]);
    });
    expect(window.location.pathname).toBe("/app/recipes");
  });

  it("persists 'not now' without starting an install", async () => {
    const putBodies: unknown[] = [];
    fetchMock.mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      if (String(input).endsWith("/owner/onboarding") && init?.method === "PUT") {
        putBodies.push(JSON.parse(String(init.body)));
        return response({ state: "completed", firstAction: null, referenceDataChoice: "none", resolvedAt: "2026-08-13T00:00:00Z", version: 2 });
      }
      return response({ state: "pending", firstAction: null, resolvedAt: null, version: 1 });
    });
    const user = userEvent.setup();
    renderJourney();
    await user.click(await screen.findByRole("button", { name: "Set up nutrition data" }));
    await user.click(screen.getByRole("button", { name: "Not now" }));
    await waitFor(() => {
      expect(putBodies).toEqual([expect.objectContaining({ referenceDataChoice: "none" })]);
    });
    expect(fetchMock.mock.calls.some(([input]) => String(input).includes("/reference-data/install"))).toBe(false);
  });
```

Adjust the existing `renderJourney` helper to include the new mocked routes if it currently fails unknown paths.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pnpm --dir frontend test --run src/features/onboarding/__tests__/FirstRunJourney.test.tsx`
Expected: FAIL (no "Set up nutrition data" button; types lack `referenceDataChoice`).

- [ ] **Step 3: Extend types and API**

In `frontend/src/features/onboarding/types.ts`:

```ts
export type ReferenceDataChoice = "both" | "foundation_sr_legacy" | "none";

export type OnboardingState = {
  state: "pending" | "completed" | "dismissed";
  firstAction: OnboardingAction | null;
  referenceDataChoice: ReferenceDataChoice | null;
  resolvedAt: string | null;
  version: number;
};
```

In `frontend/src/features/onboarding/api.ts`, extend the resolve input:

```ts
  resolve(value: { state: "completed" | "dismissed"; firstAction?: OnboardingAction; referenceDataChoice?: ReferenceDataChoice; version: number }) {
```

with `ReferenceDataChoice` imported from `./types`, and include `referenceDataChoice: value.referenceDataChoice` in the body.

- [ ] **Step 4: Extend the journey with the nutrition step**

Modify `frontend/src/features/onboarding/FirstRunJourney.tsx`:

- Imports: add `Database` from `lucide-react`, `referenceDataApi` from `../referenceData/api`, and `type ReferenceDataChoice` from `./types`.
- Add state: `const [step, setStep] = useState<"welcome" | "nutrition">("welcome");`
- Add a handler:

```tsx
  async function chooseNutrition(choice: ReferenceDataChoice) {
    try {
      await resolve.mutateAsync({
        state: "completed",
        referenceDataChoice: choice,
        version: onboarding.version,
      });
    } catch {
      // The mutation retains the error for diagnostics; onboarding remains non-blocking.
    }
    if (choice !== "none") {
      const datasets =
        choice === "both"
          ? (["foundation_sr_legacy", "branded"] as const)
          : (["foundation_sr_legacy"] as const);
      try {
        await referenceDataApi.install([...datasets]);
      } catch {
        // Install failures never block the kitchen; Settings shows the retry surface.
      }
    }
    navigate("/app/recipes");
  }
```

- In the welcome screen, add a secondary action before the existing planner link:

```tsx
          <Button variant="ghost" onClick={() => setStep("nutrition")} disabled={resolve.isPending}>Set up nutrition data <ArrowRight aria-hidden="true" /></Button>
```

- Add the nutrition step render branch (when `step === "nutrition"`), replacing the welcome content:

```tsx
  if (step === "nutrition") {
    return (
      <section className="first-run" aria-labelledby="nutrition-step-title">
        <div className="first-run__illustration">
          <KitchenCompanion moment="empty" size="lg" />
          <p>Real macros come from real food data.</p>
        </div>
        <div className="first-run__content">
          <div className="first-run__topline">
            <p className="eyebrow">Nutrition reference data</p>
            <Button variant="ghost" onClick={() => setStep("welcome")} disabled={resolve.isPending}>Back</Button>
          </div>
          <h1 id="nutrition-step-title">Real nutrition numbers?</h1>
          <p>Cookfully estimates macros from the USDA food database. Pick what to install — the app downloads and sets it up in the background while you cook.</p>
          <div className="first-run__actions first-run__actions--stacked">
            <button type="button" className="option-card" onClick={() => void chooseNutrition("both")} disabled={resolve.isPending}>
              <strong>Install both <span className="badge">Recommended</span></strong>
              <span>Foundation + SR Legacy (~10,000 foods, ~100 MB) and Branded gym products (~1.5 GB).</span>
            </button>
            <button type="button" className="option-card" onClick={() => void chooseNutrition("foundation_sr_legacy")} disabled={resolve.isPending}>
              <strong>Foundation + SR Legacy only</strong>
              <span>Whole foods and ingredients — everything most home cooks use. ~100 MB.</span>
            </button>
            <button type="button" className="option-card" onClick={() => void chooseNutrition("none")} disabled={resolve.isPending}>
              <strong>Not now</strong>
              <span>You can install this later from Settings → Nutrition data.</span>
            </button>
          </div>
          {resolve.error instanceof Error ? <p className="error-text" role="alert">Your choice could not be saved. You can still use the kitchen normally.</p> : null}
        </div>
      </section>
    );
  }
```

- [ ] **Step 5: Run the onboarding tests**

Run: `pnpm --dir frontend test --run src/features/onboarding/__tests__/FirstRunJourney.test.tsx`
Expected: PASS.

- [ ] **Step 6: Lint, typecheck, build, and full frontend suite**

Run: `pnpm --dir frontend lint`, `pnpm --dir frontend typecheck`, `pnpm --dir frontend build`, `pnpm --dir frontend test --run`
Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/features/onboarding
git commit -m "feat: onboarding nutrition data step"
```

---

### Task 10: E2E coverage and documentation

**Files:**
- Modify: `frontend/e2e/onboarding.spec.ts`
- Modify: `frontend/e2e/settings.spec.ts`
- Modify: `docs/docker-quickstart.md`

- [ ] **Step 1: Extend the onboarding E2E spec**

In `frontend/e2e/onboarding.spec.ts`, extend the route mock inside `mockOnboarding`:

```ts
    if (path === "/api/v1/reference-data/status") return route.fulfill({ json: { available: false, missing: ["foundation", "sr_legacy"], releases: [], requestedDatasets: null, job: null } });
    if (path === "/api/v1/reference-data/install" && method === "POST") return route.fulfill({ status: 202, json: { jobId: "00000000-0000-4000-8000-000000000009", status: "queued" } });
```

Add a test:

```ts
test("onboarding offers the nutrition data choice and continues after install", async ({ page }, testInfo) => {
  await mockOnboarding(page);
  await page.goto("/app/recipes");
  await page.getByRole("button", { name: "Set up nutrition data" }).click();
  await expect(page.getByRole("heading", { name: "Real nutrition numbers?" })).toBeVisible();
  await captureUi(page, testInfo, "onboarding-nutrition-step");
  await page.getByRole("button", { name: "Foundation + SR Legacy only" }).click();
  await expect(page).toHaveURL(/\/app\/recipes$/);
  await expect(page.getByRole("heading", { name: "No recipes yet" })).toBeVisible();
});
```

- [ ] **Step 2: Extend the settings E2E spec**

In `frontend/e2e/settings.spec.ts` (route-mock the same `/api/v1/reference-data/status` payload as above within the existing mock helper, or add a standalone test with its own route):

```ts
test("settings Nutrition data tab shows install controls", async ({ page }) => {
  await page.route("**/api/v1/reference-data/status", (route) =>
    route.fulfill({ json: { available: false, missing: ["foundation", "sr_legacy"], releases: [], requestedDatasets: null, job: null } })
  );
  await page.goto("/app/settings");
  await page.getByRole("tab", { name: "Nutrition data" }).click();
  await expect(page.getByRole("button", { name: "Install Foundation + SR Legacy" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Install Branded foods" })).toBeVisible();
});
```

- [ ] **Step 3: Update the Docker quickstart**

In `docs/docker-quickstart.md`, replace the body of the "Nutrition reference data (optional)" section with:

```markdown
Nutrition estimates work without any setup: ingredients that cannot be matched to a reference
food are simply excluded from the coverage ratio. To raise estimate quality, install the USDA
FoodData Central datasets from inside the app:

- On first run, the welcome journey offers a "Real nutrition numbers?" step (Foundation + SR
  Legacy, optionally Branded foods).
- Later, use Settings → Nutrition data.

The app downloads the official bulk files, imports them into PostgreSQL, and activates them in the
background — no local tools or manual files are needed. Operators who prefer the CLI can still use
`cookfully reference-data import` + `activate` (see the development quickstart, section 4).
```

- [ ] **Step 4: Run the E2E specs**

Run: `pnpm --dir frontend exec playwright test onboarding.spec.ts settings.spec.ts`
Expected: PASS against the running Docker stack (the web client is served by the stack; the specs route-mock the APIs).

- [ ] **Step 5: Final full verification**

Run: `uv run --directory backend ruff format --check .`, `uv run --directory backend ruff check .`, `uv run --directory backend mypy src`, `uv run --directory backend pytest`, `pnpm --dir frontend lint`, `pnpm --dir frontend typecheck`, `pnpm --dir frontend test --run`, `pnpm --dir frontend build`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/e2e/onboarding.spec.ts frontend/e2e/settings.spec.ts docs/docker-quickstart.md
git commit -m "test: cover nutrition data install in onboarding and settings e2e; docs"
```

---

### Task 11: Deployment verification on the Docker stack

**Files:** none (verification only).

- [ ] **Step 1: Rebuild and restart the stack**

Run: `docker compose -f deploy/compose.yaml up -d --build`
Expected: all services healthy; API runs migrations `0015` and `0016` automatically.

- [ ] **Step 2: Verify migrations and endpoints**

Run: `docker compose -f deploy/compose.yaml exec api python -c "import urllib.request; print(urllib.request.urlopen('http://localhost:8000/api/v1/health', timeout=5).status)"`
Expected: `200`.

- [ ] **Step 3: Verify the onboarding choice survives a reload (fresh database)**

Open `http://localhost:8080` in the browser (Docker Desktop: use the web container IP from `docker compose -f deploy/compose.yaml ps`), sign in with the bootstrap owner, and:
1. Confirm the welcome screen shows "Set up nutrition data".
2. Choose "Not now" and reload — the journey does not reappear.
3. Go to Settings → Nutrition data — the two install buttons and "missing" state are visible.

- [ ] **Step 4: Verify a real install end-to-end (optional but recommended)**

In Settings → Nutrition data, click "Install Foundation + SR Legacy". The status card should show "Installing USDA data… N%" and settle on "Installed" with the Foundation and SR Legacy releases listed (this downloads ~100 MB and imports ~10,000 foods; allow several minutes). Then open any recipe with an ingredient and confirm its nutrition estimate resolves with a non-zero coverage ratio.

- [ ] **Step 5: Commit any fix-ups from verification**

If the verification surfaces issues, fix them with new commits on the same branch before reporting completion.