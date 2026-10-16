from __future__ import annotations

import pytest
from pydantic import ValidationError

from benchmark_mcp.schemas import (
    FunctionalEvaluationFeedback,
    FunctionalRequirementResult,
    PassCriterionResult,
)


def criterion(
    criterion_id: str = "FR-1-PC-1",
    *,
    status: str = "pass",
) -> PassCriterionResult:
    return PassCriterionResult(
        criterion_id=criterion_id,
        status=status,
        evidence=["src/example.cpp:10 - verified behavior"] if status == "pass" else [],
        feedback=None if status == "pass" else "The required behavior is missing.",
    )


@pytest.mark.parametrize(
    ("status", "evidence", "feedback", "expected"),
    [
        ("pass", [], None, "must include candidate evidence"),
        ("pass", ["src/example.cpp:10"], "change it", "must set feedback to null"),
        ("fail", [], None, "failed criterion must include feedback"),
    ],
)
def test_pc_result_rejects_inconsistent_payloads(
    status: str,
    evidence: list[str],
    feedback: str | None,
    expected: str,
) -> None:
    with pytest.raises(ValidationError, match=expected):
        PassCriterionResult(
            criterion_id="FR-1-PC-1",
            status=status,
            evidence=evidence,
            feedback=feedback,
        )


def test_fr_result_requires_deterministic_pc_aggregation() -> None:
    with pytest.raises(ValidationError, match="deterministic aggregate"):
        FunctionalRequirementResult(
            requirement_id="FR-1",
            status="pass",
            criteria=[criterion(status="fail")],
            feedback=None,
        )


def test_fr_result_requires_sequential_pc_ids() -> None:
    with pytest.raises(ValidationError, match="unique, sequential"):
        FunctionalRequirementResult(
            requirement_id="FR-1",
            status="pass",
            criteria=[criterion("FR-1-PC-2")],
            feedback=None,
        )


def test_feedback_requires_sequential_fr_ids() -> None:
    requirement = FunctionalRequirementResult(
        requirement_id="FR-2",
        status="pass",
        criteria=[criterion("FR-2-PC-1")],
        feedback=None,
    )

    with pytest.raises(ValidationError, match="unique and sequential"):
        FunctionalEvaluationFeedback(
            case_id="example_package",
            description_sha256="d" * 64,
            package_artifact_id="a" * 32,
            requirements=[requirement],
        )


def test_valid_pc_level_feedback_is_accepted() -> None:
    feedback = FunctionalEvaluationFeedback(
        case_id="example_package",
        description_sha256="d" * 64,
        package_artifact_id="a" * 32,
        requirements=[
            FunctionalRequirementResult(
                requirement_id="FR-1",
                status="pass",
                criteria=[criterion()],
                feedback=None,
            )
        ],
    )

    assert feedback.requirements[0].criteria[0].criterion_id == "FR-1-PC-1"
