"""Validate one FR-as-metric YAML file with direct pass criteria."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import yaml


FORBIDDEN_KEYS = {
    "evaluation",
    "reference",
    "reference_evidence",
    "requirement_ids",
}


def load_mapping(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"metric must be a mapping: {path}")
    return value


def find_forbidden_keys(value: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(value, dict):
        found.update(FORBIDDEN_KEYS.intersection(value))
        for child in value.values():
            found.update(find_forbidden_keys(child))
    elif isinstance(value, list):
        for child in value:
            found.update(find_forbidden_keys(child))
    return found


def validate(metric: dict[str, Any]) -> tuple[int, int]:
    if not isinstance(metric.get("package_name"), str):
        raise ValueError("package_name must be a string")
    requirements = metric.get("metrics")
    if not isinstance(requirements, list) or not requirements:
        raise ValueError("metrics must be a non-empty list")

    criterion_count = 0
    for requirement_index, requirement in enumerate(requirements, 1):
        if not isinstance(requirement, dict):
            raise ValueError(f"FR-{requirement_index} must be a mapping")
        expected_requirement_id = f"FR-{requirement_index}"
        if requirement.get("id") != expected_requirement_id:
            raise ValueError(f"expected {expected_requirement_id}: {requirement!r}")
        if set(requirement) != {"id", "text", "pass_criteria"}:
            raise ValueError(f"unexpected keys in {expected_requirement_id}: {set(requirement)}")
        if not isinstance(requirement.get("text"), str) or not requirement["text"].strip():
            raise ValueError(f"{expected_requirement_id}.text must be non-empty")

        criteria = requirement.get("pass_criteria")
        if not isinstance(criteria, list) or not criteria:
            raise ValueError(f"{expected_requirement_id}.pass_criteria must be non-empty")
        for criterion_index, criterion in enumerate(criteria, 1):
            expected_criterion_id = f"{expected_requirement_id}-PC-{criterion_index}"
            if not isinstance(criterion, dict):
                raise ValueError(f"{expected_criterion_id} must be a mapping")
            if criterion.get("id") != expected_criterion_id:
                raise ValueError(f"expected {expected_criterion_id}: {criterion!r}")
            if set(criterion) != {"id", "text"}:
                raise ValueError(f"unexpected keys in {expected_criterion_id}: {set(criterion)}")
            if not isinstance(criterion.get("text"), str) or not criterion["text"].strip():
                raise ValueError(f"{expected_criterion_id}.text must be non-empty")
            criterion_count += 1

    forbidden = find_forbidden_keys(metric)
    if forbidden:
        raise ValueError(f"forbidden keys present: {sorted(forbidden)}")
    return len(requirements), criterion_count


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("metric", type=Path)
    parser.add_argument("--baseline", type=Path)
    args = parser.parse_args()

    metric = load_mapping(args.metric)
    requirement_count, criterion_count = validate(metric)

    if args.baseline:
        baseline = load_mapping(args.baseline)
        previous = [(item["id"], item["text"]) for item in baseline["metrics"]]
        current = [(item["id"], item["text"]) for item in metric["metrics"]]
        if current != previous:
            raise ValueError("FR ids or text changed from the baseline metric")

    print(
        f"FRs={requirement_count} PCs={criterion_count} "
        f"FR_text_preserved={'yes' if args.baseline else 'not_checked'} "
        "forbidden_layers=absent"
    )


if __name__ == "__main__":
    main()
