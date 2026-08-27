"""Validate every benchmark metric after the FR-to-PC migration."""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

import yaml

from validate_fr_pc_metric import validate


def git_show(repository: Path, revision: str, relative_path: str) -> dict:
    command = [
        "git",
        "-c",
        f"safe.directory={repository.as_posix()}",
        "-C",
        str(repository),
        "show",
        f"{revision}:{relative_path}",
    ]
    raw = subprocess.run(command, check=True, capture_output=True, text=True).stdout
    value = yaml.safe_load(raw)
    if not isinstance(value, dict):
        raise ValueError(f"baseline metric must be a mapping: {relative_path}")
    return value


def fr_identity(metric: dict) -> list[tuple[str, str]]:
    return [(item["id"], item["text"]) for item in metric["metrics"]]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("repository", type=Path)
    parser.add_argument("--baseline-revision")
    parser.add_argument("--expected-case-count", type=int, default=17)
    args = parser.parse_args()

    repository = args.repository.resolve()
    case_dirs = sorted(
        path
        for path in (repository / "benchmarks").iterdir()
        if path.is_dir() and (path / "metric.yaml").is_file()
    )
    if len(case_dirs) != args.expected_case_count:
        raise ValueError(
            f"expected {args.expected_case_count} cases, found {len(case_dirs)}"
        )
    if any(path.name == "nav2_collision_monitor" for path in case_dirs):
        raise ValueError("deleted nav2_collision_monitor case is still present")

    total_requirements = 0
    total_criteria = 0
    for case_dir in case_dirs:
        relative_path = f"benchmarks/{case_dir.name}/metric.yaml"
        metric = yaml.safe_load((case_dir / "metric.yaml").read_text(encoding="utf-8"))
        if not isinstance(metric, dict):
            raise ValueError(f"metric must be a mapping: {relative_path}")
        requirement_count, criterion_count = validate(metric)
        if args.baseline_revision:
            baseline = git_show(repository, args.baseline_revision, relative_path)
            if fr_identity(metric) != fr_identity(baseline):
                raise ValueError(f"FR ids or text changed: {case_dir.name}")
        description = yaml.safe_load(
            (case_dir / "description.yaml").read_text(encoding="utf-8")
        )
        if not isinstance(description, dict):
            raise ValueError(f"description must be a mapping: {case_dir.name}")
        if "interfaces" in description:
            raise ValueError(f"interfaces remain in description: {case_dir.name}")
        public_requirements = description.get("functional_requirements")
        if not isinstance(public_requirements, list) or not public_requirements:
            raise ValueError(f"description has no public FRs: {case_dir.name}")
        if fr_identity({"metrics": public_requirements}) != fr_identity(metric):
            raise ValueError(f"description/metric FR mismatch: {case_dir.name}")
        total_requirements += requirement_count
        total_criteria += criterion_count
        print(f"{case_dir.name}: FRs={requirement_count} PCs={criterion_count}")

    print(
        f"TOTAL cases={len(case_dirs)} FRs={total_requirements} PCs={total_criteria} "
        f"FR_text_preserved={'yes' if args.baseline_revision else 'not_checked'} "
        "public_FRs_match=yes forbidden_layers=absent"
    )


if __name__ == "__main__":
    main()
