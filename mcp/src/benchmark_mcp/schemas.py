"""Structured inputs and outputs exposed by the benchmark MCP tools."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


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


class FunctionalRequirementResult(BaseModel):
    """One evaluator decision tied to a public functional requirement."""

    model_config = ConfigDict(extra="forbid")

    requirement_id: str
    status: Literal["pass", "fail", "not_evaluated"]
    evidence: list[str]
    feedback: str | None = None


class FunctionalEvaluationFeedback(BaseModel):
    """Structured evaluator output returned to the orchestrator, never the Coder MCP."""

    model_config = ConfigDict(extra="forbid")

    case_id: str
    description_sha256: str
    package_artifact_id: str
    requirements: list[FunctionalRequirementResult]
