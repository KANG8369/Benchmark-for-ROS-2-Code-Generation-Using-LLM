"""Structured inputs and outputs exposed by the benchmark MCP tools."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class PackageFile(BaseModel):
    """One UTF-8 file in a package snapshot."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    path: str
    content: str
    executable: bool = False


class InterfaceShowResult(BaseModel):
    """Structured result from ``ros2 interface show``."""

    model_config = ConfigDict(extra="forbid")

    interface_type: str
    ros_distro: str
    found: bool
    definition: str | None
    definition_sha256: str | None
    exit_code: int | None
    stderr: str
    duration_ms: int
    output_truncated: bool
    error_kind: (
        Literal[
            "invalid_request",
            "not_found",
            "timeout",
            "configuration",
            "execution",
        ]
        | None
    ) = None


class BuildResult(BaseModel):
    """Structured result from one isolated-workspace package build."""

    model_config = ConfigDict(extra="forbid")

    build_id: str
    package_name: str
    snapshot_sha256: str | None
    ros_distro: str
    status: Literal[
        "passed",
        "failed",
        "timed_out",
        "rejected",
        "unavailable",
        "budget_exhausted",
        "internal_error",
    ]
    success: bool
    command: list[str]
    exit_code: int | None
    timed_out: bool
    duration_ms: int
    stdout: str
    stderr: str
    stdout_truncated: bool
    stderr_truncated: bool
    validation_errors: list[str]
    workspace_retained: bool
    artifact_recorded: bool = False


class PassCriterionResult(BaseModel):
    """One evaluator decision tied to a hidden pass criterion."""

    model_config = ConfigDict(extra="forbid")

    criterion_id: str = Field(pattern=r"^FR-[1-9][0-9]*-PC-[1-9][0-9]*$")
    status: Literal["pass", "fail"]
    evidence: list[str]
    feedback: str | None = None

    @model_validator(mode="after")
    def require_consistent_evidence_and_feedback(self) -> PassCriterionResult:
        if self.status == "pass":
            if not self.evidence:
                raise ValueError("a passed criterion must include candidate evidence")
            if self.feedback is not None:
                raise ValueError("a passed criterion must set feedback to null")
        elif not self.feedback:
            raise ValueError("a failed criterion must include feedback")
        return self


class FunctionalRequirementResult(BaseModel):
    """Deterministic aggregation of all PCs for one public FR."""

    model_config = ConfigDict(extra="forbid")

    requirement_id: str = Field(pattern=r"^FR-[1-9][0-9]*$")
    status: Literal["pass", "fail"]
    criteria: list[PassCriterionResult] = Field(min_length=1)
    feedback: str | None = None

    @model_validator(mode="after")
    def require_sequential_criteria_and_correct_aggregate(self) -> FunctionalRequirementResult:
        expected_ids = [
            f"{self.requirement_id}-PC-{index}" for index in range(1, len(self.criteria) + 1)
        ]
        actual_ids = [item.criterion_id for item in self.criteria]
        if actual_ids != expected_ids:
            raise ValueError("criterion IDs must be unique, sequential, and match the parent FR")
        expected_status = "pass" if all(item.status == "pass" for item in self.criteria) else "fail"
        if self.status != expected_status:
            raise ValueError("FR status must be the deterministic aggregate of its criteria")
        if self.status == "pass" and self.feedback is not None:
            raise ValueError("a passed requirement must set feedback to null")
        if self.status == "fail" and not self.feedback:
            raise ValueError("a failed requirement must include feedback")
        return self


class FunctionalEvaluationFeedback(BaseModel):
    """Structured evaluator output returned to the orchestrator, never the Coder MCP."""

    model_config = ConfigDict(extra="forbid")

    case_id: str
    description_sha256: str
    package_artifact_id: str
    requirements: list[FunctionalRequirementResult] = Field(min_length=1)

    @model_validator(mode="after")
    def require_sequential_requirements(self) -> FunctionalEvaluationFeedback:
        expected_ids = [f"FR-{index}" for index in range(1, len(self.requirements) + 1)]
        actual_ids = [item.requirement_id for item in self.requirements]
        if actual_ids != expected_ids:
            raise ValueError("requirement IDs must be unique and sequential")
        return self
