from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from vigor_vine.cli.main import app
from vigor_vine.cli.usability_study import (
    AgentProxyData,
    StudyData,
    summarize,
    summarize_agent_proxy,
)


def participant(
    index: int,
    *,
    complete: bool = True,
    seconds: str = "240.0",
    hints: int = 0,
) -> dict[str, object]:
    return {
        "anonymousId": f"P-{index:03d}",
        "experience": "novice" if index <= 5 else "experienced" if index <= 10 else "other",
        "viewport": "narrow-mobile" if index <= 8 else "desktop",
        "productNaiveConfirmed": True,
        "consentAnonymousEvidence": True,
        "projectInvolvement": False,
        "preTimerTechnicalFailure": False,
        "exclusionCodes": [],
        "sessionCompleted": True,
        "steps": {
            "captureComplete": complete,
            "statusIdentified": complete,
            "addedToDay": complete,
            "impactIdentified": complete,
        },
        "completionSeconds": seconds,
        "hints": hints,
        "observationCodes": [],
    }


def study(rows: list[dict[str, object]]) -> StudyData:
    return StudyData.model_validate(
        {"schemaVersion": "1.0", "roundId": "SC008-ROUND-01", "participants": rows}
    )


def test_exact_twenty_requires_eighteen_unaided_under_five_minute_passes() -> None:
    rows = [participant(index) for index in range(1, 21)]
    rows[-2] = participant(19, seconds="300.0")
    rows[-1] = participant(20, hints=1)

    summary = summarize(study(rows))

    assert summary.eligible_participants == 20
    assert summary.required_passes == 18
    assert summary.actual_passes == 18
    assert summary.novice_participants == 5
    assert summary.experienced_participants == 5
    assert summary.narrow_mobile_sessions == 8
    assert summary.desktop_sessions == 12
    assert summary.passed is True
    assert summary.failures == ()


def test_ceiling_rule_and_every_quota_are_enforced() -> None:
    rows = [participant(index, complete=index <= 18) for index in range(1, 22)]
    for index in range(1, 5):
        rows[index - 1]["experience"] = "novice"
    rows[4]["experience"] = "other"
    for row in rows:
        row["viewport"] = "desktop"

    summary = summarize(study(rows))

    assert summary.eligible_participants == 21
    assert summary.required_passes == 19
    assert summary.actual_passes == 18
    assert summary.passed is False
    assert set(summary.failures) == {
        "novice_quota",
        "narrow_mobile_quota",
        "pass_rate",
    }


def test_exclusions_are_consistent_computed_and_removed_before_rate() -> None:
    rows = [participant(index) for index in range(1, 21)]
    excluded = participant(21)
    excluded.update(
        {
            "productNaiveConfirmed": False,
            "exclusionCodes": ["prior_use"],
            "sessionCompleted": False,
            "completionSeconds": None,
        }
    )
    rows.append(excluded)

    summary = summarize(study(rows))

    assert summary.total_records == 21
    assert summary.excluded_records == 1
    assert summary.eligible_participants == 20
    assert summary.actual_passes == 20
    assert summary.passed is True


def test_unknown_personal_fields_and_inconsistent_exclusions_are_rejected() -> None:
    personal = participant(1)
    personal["email"] = "do-not-store@example.test"
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        study([personal])

    inconsistent = participant(1)
    inconsistent["productNaiveConfirmed"] = False
    with pytest.raises(ValidationError, match="exclusionCodes"):
        study([inconsistent])


def test_cli_writes_pending_summary_and_require_pass_fails(tmp_path: Path) -> None:
    input_path = tmp_path / "study.json"
    output_path = tmp_path / "summary.json"
    input_path.write_text(
        json.dumps({"schemaVersion": "1.0", "roundId": "SC008-ROUND-01", "participants": []}),
        encoding="utf-8",
    )

    result = CliRunner().invoke(
        app,
        [
            "usability-study",
            "validate",
            "--input",
            str(input_path),
            "--output",
            str(output_path),
            "--require-pass",
        ],
    )

    assert result.exit_code == 1
    summary = json.loads(output_path.read_text(encoding="utf-8"))
    assert summary["passed"] is False
    assert summary["failures"] == [
        "eligible_sample",
        "novice_quota",
        "experienced_quota",
        "narrow_mobile_quota",
        "desktop_quota",
    ]


def agent_evaluation(index: int, *, passes: bool = True) -> dict[str, object]:
    return {
        "evaluationId": f"A-{index:03d}",
        "personaExperience": (
            "novice" if index <= 5 else "experienced" if index <= 10 else "other"
        ),
        "personaDescription": f"Independent simulated evaluator persona number {index}",
        "viewport": "narrow-mobile" if index <= 8 else "desktop",
        "freshContextConfirmed": True,
        "inspectedArtifacts": ["frontend/src/features/recipes/RecipeEditor.tsx"],
        "captureDiscoverable": passes,
        "statusMeaningCorrect": passes,
        "planAddDiscoverable": passes,
        "targetImpactCorrect": passes,
        "criticalBlockers": [] if passes else ["TARGET_IMPACT_BLOCKED"],
        "nonCriticalFindings": [],
        "confidence": "medium",
    }


def test_agent_proxy_is_transparent_independent_and_uses_ceiling_pass_math() -> None:
    rows = [agent_evaluation(index, passes=index <= 18) for index in range(1, 21)]
    proxy = AgentProxyData.model_validate(
        {
            "schemaVersion": "1.0",
            "method": "independent-agent-cognitive-walkthrough-v1",
            "roundId": "SC008-PROXY-ROUND-01",
            "evaluations": rows,
        }
    )

    summary = summarize_agent_proxy(proxy)

    assert summary.total_evaluations == 20
    assert summary.required_passes == 18
    assert summary.actual_passes == 18
    assert summary.passed is True


def test_agent_proxy_rejects_shared_context_and_non_ui_evidence() -> None:
    shared = agent_evaluation(1)
    shared["freshContextConfirmed"] = False
    with pytest.raises(ValidationError, match="Input should be True"):
        AgentProxyData.model_validate(
            {
                "schemaVersion": "1.0",
                "method": "independent-agent-cognitive-walkthrough-v1",
                "roundId": "SC008-PROXY-ROUND-01",
                "evaluations": [shared],
            }
        )

    no_ui = agent_evaluation(1)
    no_ui["inspectedArtifacts"] = ["specs/001-nutrition-recipe-planner/spec.md"]
    with pytest.raises(ValidationError, match="implemented frontend"):
        AgentProxyData.model_validate(
            {
                "schemaVersion": "1.0",
                "method": "independent-agent-cognitive-walkthrough-v1",
                "roundId": "SC008-PROXY-ROUND-01",
                "evaluations": [no_ui],
            }
        )
