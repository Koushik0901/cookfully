from __future__ import annotations

import re
from pathlib import Path

from cookfully.jobs.retention_process import HEARTBEAT_PATH

COMPOSE = Path(__file__).resolve().parents[3] / "deploy" / "compose.yaml"


def test_retention_heartbeat_path_matches_the_compose_healthcheck() -> None:
    """The container is only reported healthy if both sides agree on this file."""

    healthcheck_paths = re.findall(r"Path\('([^']*heartbeat[^']*)'\)", COMPOSE.read_text("utf-8"))

    assert healthcheck_paths == [HEARTBEAT_PATH.as_posix()]
