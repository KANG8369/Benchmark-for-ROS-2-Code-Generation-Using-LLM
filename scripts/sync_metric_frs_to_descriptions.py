"""Copy public FR ids and text from each metric into its description."""

from __future__ import annotations

import argparse
import textwrap
from pathlib import Path
from typing import Any

import yaml


def load_mapping(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"YAML must be a mapping: {path}")
    return value


def folded_text(text: str) -> str:
    normalized = " ".join(text.split())
    return "\n".join(
        "      " + line
        for line in textwrap.wrap(
            normalized,
            width=70,
            break_long_words=False,
            break_on_hyphens=False,
        )
    )


def requirement_section(requirements: list[dict[str, Any]]) -> str:
    lines = ["functional_requirements:"]
    for requirement in requirements:
        lines.extend(
            [
                f"  - id: {requirement['id']}",
                "    text: >-",
                folded_text(requirement["text"]),
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def fr_identity(requirements: list[dict[str, Any]]) -> list[tuple[str, str]]:
    return [(item["id"], item["text"]) for item in requirements]


def sync_case(case_dir: Path, *, write: bool) -> str:
    description_path = case_dir / "description.yaml"
    metric_path = case_dir / "metric.yaml"
    description_text = description_path.read_text(encoding="utf-8")
    description = load_mapping(description_path)
    metric = load_mapping(metric_path)
    requirements = metric.get("metrics")
    if not isinstance(requirements, list) or not requirements:
        raise ValueError(f"metric has no FR list: {metric_path}")
    if "functional_requirements" in description:
        raise ValueError(f"description already has FRs: {description_path}")

    section = requirement_section(requirements)
    target_marker = "\ntarget_environment:"
    target_index = description_text.find(target_marker)
    if target_index >= 0:
        updated = (
            description_text[:target_index].rstrip()
            + "\n\n"
            + section
            + "\n"
            + description_text[target_index + 1 :].lstrip("\n")
        )
    else:
        updated = description_text.rstrip() + "\n\n" + section
    updated = updated.rstrip() + "\n"

    parsed_updated = yaml.safe_load(updated)
    if not isinstance(parsed_updated, dict):
        raise ValueError(f"updated description is invalid: {description_path}")
    if fr_identity(parsed_updated["functional_requirements"]) != fr_identity(requirements):
        raise ValueError(f"description/metric FR mismatch after sync: {case_dir.name}")
    if "interfaces" in parsed_updated:
        raise ValueError(f"interfaces unexpectedly present: {description_path}")

    if write:
        description_path.write_text(updated, encoding="utf-8")
    return f"{case_dir.name}: FRs={len(requirements)}{' written' if write else ''}"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("repository", type=Path)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()

    benchmark_root = args.repository.resolve() / "benchmarks"
    case_dirs = sorted(
        path
        for path in benchmark_root.iterdir()
        if path.is_dir()
        and (path / "description.yaml").is_file()
        and (path / "metric.yaml").is_file()
    )
    for case_dir in case_dirs:
        print(sync_case(case_dir, write=args.write))


if __name__ == "__main__":
    main()
