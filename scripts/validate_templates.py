"""Validate revised Description and Metric example templates."""

from __future__ import annotations

import argparse
from pathlib import Path

import yaml


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("repository", type=Path)
    args = parser.parse_args()

    root = args.repository.resolve()
    description = yaml.safe_load(
        (root / "templates" / "description.yaml").read_text(encoding="utf-8")
    )
    metric = yaml.safe_load(
        (root / "templates" / "metric.yaml").read_text(encoding="utf-8")
    )

    if set(description) != {"intent", "functional_requirements", "target_environment"}:
        raise ValueError("unexpected Description template fields")
    if set(metric) != {"package_name", "metrics"}:
        raise ValueError("unexpected Metric template fields")
    if description["intent"]["package_name"] != metric["package_name"]:
        raise ValueError("template package names differ")

    public = [(item["id"], item["text"]) for item in description["functional_requirements"]]
    hidden = [(item["id"], item["text"]) for item in metric["metrics"]]
    if public != hidden:
        raise ValueError("Description and Metric template FRs differ")

    criterion_count = 0
    for requirement_index, requirement in enumerate(metric["metrics"], 1):
        expected_requirement_id = f"FR-{requirement_index}"
        if set(requirement) != {"id", "text", "pass_criteria"}:
            raise ValueError(f"unexpected keys in {expected_requirement_id}")
        if requirement["id"] != expected_requirement_id:
            raise ValueError(f"expected {expected_requirement_id}")
        for criterion_index, criterion in enumerate(requirement["pass_criteria"], 1):
            expected_criterion_id = f"{expected_requirement_id}-PC-{criterion_index}"
            if set(criterion) != {"id", "text"}:
                raise ValueError(f"unexpected keys in {expected_criterion_id}")
            if criterion["id"] != expected_criterion_id:
                raise ValueError(f"expected {expected_criterion_id}")
            criterion_count += 1

    print(
        f"templates_yaml=ok FRs={len(public)} PCs={criterion_count} "
        "public_metric_FR_match=yes"
    )


if __name__ == "__main__":
    main()
