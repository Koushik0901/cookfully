from __future__ import annotations

import json
from decimal import Decimal
from enum import StrEnum
from math import ceil
from pathlib import Path
from typing import Annotated, Literal, Self

import typer
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from pydantic.alias_generators import to_camel

app = typer.Typer(
    name="usability-study",
    help="Validate SC-008 human-study or independent-agent proxy evidence.",
)


class EvidenceModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        extra="forbid",
    )


class ExclusionCode(StrEnum):
    PRIOR_USE = "prior_use"
    PROJECT_INVOLVEMENT = "project_involvement"
    PRE_TIMER_TECHNICAL_FAILURE = "pre_timer_technical_failure"
    NO_CONSENT = "no_consent"


class StudySteps(EvidenceModel):
    capture_complete: bool
    status_identified: bool
    added_to_day: bool
    impact_identified: bool

    @property
    def all_complete(self) -> bool:
        return all(
            (
                self.capture_complete,
                self.status_identified,
                self.added_to_day,
                self.impact_identified,
            )
        )


class ParticipantEvidence(EvidenceModel):
    anonymous_id: str = Field(pattern=r"^P-[A-Z0-9]{3,12}$")
    experience: Literal["novice", "experienced", "other"]
    viewport: Literal["narrow-mobile", "desktop"]
    product_naive_confirmed: bool
    consent_anonymous_evidence: bool
    project_involvement: bool
    pre_timer_technical_failure: bool
    exclusion_codes: tuple[ExclusionCode, ...]
    session_completed: bool
    steps: StudySteps
    completion_seconds: Decimal | None = Field(default=None, gt=0, le=300)
    hints: int = Field(ge=0)
    observation_codes: tuple[str, ...] = Field(default_factory=tuple)

    @model_validator(mode="after")
    def validate_exclusions_and_session(self) -> Self:
        if len(set(self.exclusion_codes)) != len(self.exclusion_codes):
            raise ValueError("exclusionCodes must not contain duplicates")
        expected: set[ExclusionCode] = set()
        if not self.product_naive_confirmed:
            expected.add(ExclusionCode.PRIOR_USE)
        if self.project_involvement:
            expected.add(ExclusionCode.PROJECT_INVOLVEMENT)
        if self.pre_timer_technical_failure:
            expected.add(ExclusionCode.PRE_TIMER_TECHNICAL_FAILURE)
        if not self.consent_anonymous_evidence:
            expected.add(ExclusionCode.NO_CONSENT)
        if set(self.exclusion_codes) != expected:
            raise ValueError(
                "exclusionCodes must exactly match product naivety, project involvement, "
                "pre-timer technical failure, and anonymous-evidence consent"
            )
        if self.eligible and (not self.session_completed or self.completion_seconds is None):
            raise ValueError(
                "eligible participants require a completed study session and completionSeconds"
            )
        for code in self.observation_codes:
            if (
                not code
                or len(code) > 40
                or not all(
                    character.isupper() or character.isdigit() or character == "_"
                    for character in code
                )
            ):
                raise ValueError(
                    "observationCodes must use 1-40 uppercase letters, digits, or underscores"
                )
        return self

    @property
    def eligible(self) -> bool:
        return not self.exclusion_codes

    @property
    def passed(self) -> bool:
        return bool(
            self.eligible
            and self.session_completed
            and self.steps.all_complete
            and self.completion_seconds is not None
            and self.completion_seconds < Decimal("300")
            and self.hints == 0
        )


class StudyData(EvidenceModel):
    schema_version: Literal["1.0"]
    round_id: str = Field(pattern=r"^SC008-[A-Z0-9-]{3,40}$")
    participants: tuple[ParticipantEvidence, ...]

    @model_validator(mode="after")
    def unique_anonymous_ids(self) -> Self:
        identifiers = [participant.anonymous_id for participant in self.participants]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("anonymousId values must be unique within a study round")
        return self


class StudySummary(EvidenceModel):
    schema_version: Literal["1.0"] = "1.0"
    round_id: str
    total_records: int
    excluded_records: int
    eligible_participants: int
    novice_participants: int
    experienced_participants: int
    narrow_mobile_sessions: int
    desktop_sessions: int
    required_passes: int
    actual_passes: int
    passed: bool
    failures: tuple[str, ...]


class AgentEvaluation(EvidenceModel):
    evaluation_id: str = Field(pattern=r"^A-[0-9]{3}$")
    model: Literal["gpt-5.6-terra"]
    persona_experience: Literal["novice", "experienced", "other"]
    persona_description: str = Field(min_length=10, max_length=240)
    viewport: Literal["narrow-mobile", "desktop"]
    fresh_context_confirmed: Literal[True]
    inspected_artifacts: tuple[str, ...] = Field(min_length=1)
    capture_discoverable: bool
    status_meaning_correct: bool
    plan_add_discoverable: bool
    target_impact_correct: bool
    critical_blockers: tuple[str, ...] = Field(default_factory=tuple)
    non_critical_findings: tuple[str, ...] = Field(default_factory=tuple)
    confidence: Literal["low", "medium", "high"]

    @model_validator(mode="after")
    def validate_codes_and_artifacts(self) -> Self:
        for code in self.critical_blockers:
            if (
                not code
                or len(code) > 40
                or not all(
                    character.isupper() or character.isdigit() or character == "_"
                    for character in code
                )
            ):
                raise ValueError(
                    "criticalBlockers must use 1-40 uppercase letters, digits, or underscores"
                )
        if not any(
            artifact.startswith(("frontend/", "http://127.0.0.1", "http://localhost"))
            for artifact in self.inspected_artifacts
        ):
            raise ValueError(
                "inspectedArtifacts must include implemented frontend or rendered local UI evidence"
            )
        return self

    @property
    def passed(self) -> bool:
        return bool(
            self.capture_discoverable
            and self.status_meaning_correct
            and self.plan_add_discoverable
            and self.target_impact_correct
            and not self.critical_blockers
        )


class AgentProxyData(EvidenceModel):
    schema_version: Literal["1.0"]
    method: Literal["independent-agent-cognitive-walkthrough-v1"]
    round_id: str = Field(pattern=r"^SC008-PROXY-[A-Z0-9-]{3,40}$")
    evaluations: tuple[AgentEvaluation, ...]

    @model_validator(mode="after")
    def unique_evaluation_ids(self) -> Self:
        identifiers = [evaluation.evaluation_id for evaluation in self.evaluations]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("evaluationId values must be unique within a proxy round")
        return self


class AgentProxySummary(EvidenceModel):
    schema_version: Literal["1.0"] = "1.0"
    method: Literal["independent-agent-cognitive-walkthrough-v1"] = (
        "independent-agent-cognitive-walkthrough-v1"
    )
    round_id: str
    total_evaluations: int
    novice_personas: int
    experienced_personas: int
    narrow_mobile_evaluations: int
    desktop_evaluations: int
    required_passes: int
    actual_passes: int
    passed: bool
    failures: tuple[str, ...]


def summarize(study: StudyData) -> StudySummary:
    eligible = tuple(participant for participant in study.participants if participant.eligible)
    required = ceil(Decimal("0.90") * len(eligible))
    actual = sum(participant.passed for participant in eligible)
    novice = sum(participant.experience == "novice" for participant in eligible)
    experienced = sum(participant.experience == "experienced" for participant in eligible)
    narrow_mobile = sum(
        participant.viewport == "narrow-mobile" and participant.session_completed
        for participant in eligible
    )
    desktop = sum(
        participant.viewport == "desktop" and participant.session_completed
        for participant in eligible
    )
    failures: list[str] = []
    if len(eligible) < 20:
        failures.append("eligible_sample")
    if novice < 5:
        failures.append("novice_quota")
    if experienced < 5:
        failures.append("experienced_quota")
    if narrow_mobile < 8:
        failures.append("narrow_mobile_quota")
    if desktop < 8:
        failures.append("desktop_quota")
    if actual < required:
        failures.append("pass_rate")
    return StudySummary(
        round_id=study.round_id,
        total_records=len(study.participants),
        excluded_records=len(study.participants) - len(eligible),
        eligible_participants=len(eligible),
        novice_participants=novice,
        experienced_participants=experienced,
        narrow_mobile_sessions=narrow_mobile,
        desktop_sessions=desktop,
        required_passes=required,
        actual_passes=actual,
        passed=not failures,
        failures=tuple(failures),
    )


def summarize_agent_proxy(proxy: AgentProxyData) -> AgentProxySummary:
    evaluations = proxy.evaluations
    required = ceil(Decimal("0.90") * len(evaluations))
    actual = sum(evaluation.passed for evaluation in evaluations)
    novice = sum(evaluation.persona_experience == "novice" for evaluation in evaluations)
    experienced = sum(evaluation.persona_experience == "experienced" for evaluation in evaluations)
    narrow_mobile = sum(evaluation.viewport == "narrow-mobile" for evaluation in evaluations)
    desktop = sum(evaluation.viewport == "desktop" for evaluation in evaluations)
    failures: list[str] = []
    if len(evaluations) < 6:
        failures.append("evaluation_sample")
    if novice < 2:
        failures.append("novice_persona_quota")
    if experienced < 2:
        failures.append("experienced_persona_quota")
    if narrow_mobile < 3:
        failures.append("narrow_mobile_quota")
    if desktop < 3:
        failures.append("desktop_quota")
    if actual < required:
        failures.append("pass_rate")
    return AgentProxySummary(
        round_id=proxy.round_id,
        total_evaluations=len(evaluations),
        novice_personas=novice,
        experienced_personas=experienced,
        narrow_mobile_evaluations=narrow_mobile,
        desktop_evaluations=desktop,
        required_passes=required,
        actual_passes=actual,
        passed=not failures,
        failures=tuple(failures),
    )


@app.command("validate")
def validate_command(
    input_path: Annotated[
        Path,
        typer.Option("--input", help="Anonymized study JSON to validate."),
    ],
    output_path: Annotated[
        Path | None,
        typer.Option("--output", help="Optional computed summary JSON output."),
    ] = None,
    require_pass: Annotated[
        bool,
        typer.Option(
            help="Exit nonzero unless every SC-008 sample, quota, and pass rule succeeds."
        ),
    ] = False,
) -> None:
    try:
        study = StudyData.model_validate_json(input_path.read_text(encoding="utf-8"))
    except (OSError, ValidationError, ValueError) as error:
        typer.echo(f"Invalid SC-008 study evidence: {error}", err=True)
        raise typer.Exit(2) from error
    summary = summarize(study)
    rendered = json.dumps(summary.model_dump(mode="json", by_alias=True), indent=2) + "\n"
    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered, encoding="utf-8")
    typer.echo(rendered, nl=False)
    if require_pass and not summary.passed:
        raise typer.Exit(1)


@app.command("validate-proxy")
def validate_proxy_command(
    input_path: Annotated[
        Path,
        typer.Option("--input", help="Independent simulated-evaluator JSON to validate."),
    ],
    output_path: Annotated[
        Path | None,
        typer.Option("--output", help="Optional computed proxy summary JSON output."),
    ] = None,
    require_pass: Annotated[
        bool,
        typer.Option(help="Exit nonzero unless every SC-008 proxy sample and pass rule succeeds."),
    ] = False,
) -> None:
    try:
        proxy = AgentProxyData.model_validate_json(input_path.read_text(encoding="utf-8"))
    except (OSError, ValidationError, ValueError) as error:
        typer.echo(f"Invalid SC-008 proxy evidence: {error}", err=True)
        raise typer.Exit(2) from error
    summary = summarize_agent_proxy(proxy)
    rendered = json.dumps(summary.model_dump(mode="json", by_alias=True), indent=2) + "\n"
    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered, encoding="utf-8")
    typer.echo(rendered, nl=False)
    if require_pass and not summary.passed:
        raise typer.Exit(1)
