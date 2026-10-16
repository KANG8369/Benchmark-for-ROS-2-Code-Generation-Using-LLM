"""Attach main-branch pass criteria directly to FR metrics without reference fields."""

from __future__ import annotations

import argparse
import re
import subprocess
import textwrap
from collections import defaultdict
from pathlib import Path
from typing import Any

import yaml


FR_BLOCK = re.compile(
    r"(?ms)^(?P<indent> *)- id: (?P<id>FR-[1-9][0-9]*)\n.*?"
    r"(?=\n(?P=indent)- id: FR-[1-9][0-9]*\n|\Z)"
)


def load_yaml_text(text: str, source: str) -> dict[str, Any]:
    value = yaml.safe_load(text)
    if not isinstance(value, dict):
        raise ValueError(f"YAML must be a mapping: {source}")
    return value


def git_show(repository: Path, revision: str, relative_path: str) -> str:
    command = [
        "git",
        "-c",
        f"safe.directory={repository.as_posix()}",
        "-C",
        str(repository),
        "show",
        f"{revision}:{relative_path}",
    ]
    return subprocess.run(command, check=True, capture_output=True, text=True).stdout


def criteria_by_requirement(main_metric: dict[str, Any]) -> dict[str, list[str]]:
    result: dict[str, list[str]] = defaultdict(list)
    for metric in main_metric.get("metrics", []):
        if not isinstance(metric, dict):
            raise ValueError("main metric entry must be a mapping")
        requirement_ids = metric.get("requirement_ids")
        criteria = metric.get("pass_criteria")
        if not isinstance(requirement_ids, list) or not requirement_ids:
            raise ValueError(f"missing requirement_ids: {metric.get('id')}")
        if not isinstance(criteria, list) or not criteria:
            raise ValueError(f"missing pass_criteria: {metric.get('id')}")
        for criterion in criteria:
            if not isinstance(criterion, dict) or not isinstance(criterion.get("text"), str):
                raise ValueError(f"invalid pass criterion: {metric.get('id')}")
            for requirement_id in requirement_ids:
                result[str(requirement_id)].append(criterion["text"])
    return dict(result)


def folded_text(text: str, indent: str) -> str:
    normalized = " ".join(text.split())
    return "\n".join(
        indent + line
        for line in textwrap.wrap(
            normalized,
            width=76 - len(indent),
            break_long_words=False,
            break_on_hyphens=False,
        )
    )


def criterion_block(requirement_id: str, criteria: list[str], item_indent: str) -> str:
    key_indent = item_indent + "  "
    criterion_indent = item_indent + "    "
    criterion_key_indent = item_indent + "      "
    content_indent = item_indent + "        "
    lines = [key_indent + "pass_criteria:"]
    for index, criterion in enumerate(criteria, 1):
        lines.extend(
            [
                criterion_indent + f"- id: {requirement_id}-PC-{index}",
                criterion_key_indent + "text: >-",
                folded_text(criterion, content_indent),
            ]
        )
    return "\n".join(lines)


def migrate_case(repository: Path, case_id: str, revision: str, *, write: bool) -> str:
    relative = f"benchmarks/{case_id}/metric.yaml"
    current_path = repository / relative
    current_text = current_path.read_text(encoding="utf-8")
    current_metric = load_yaml_text(current_text, str(current_path))
    main_text = git_show(repository, revision, relative)
    main_metric = load_yaml_text(main_text, f"{revision}:{relative}")
    mapping = criteria_by_requirement(main_metric)

    current_requirements = current_metric.get("metrics")
    if not isinstance(current_requirements, list) or not current_requirements:
        raise ValueError(f"current metric has no FR metrics: {case_id}")
    requirement_ids = [item.get("id") for item in current_requirements]
    if set(mapping) != set(requirement_ids):
        raise ValueError(
            f"FR/PC mapping mismatch for {case_id}: "
            f"FRs={requirement_ids}, mapped={sorted(mapping)}"
        )
    if "pass_criteria:" in current_text:
        raise ValueError(f"pass_criteria already present: {case_id}")

    pieces: list[str] = []
    cursor = 0
    matched_ids: list[str] = []
    for match in FR_BLOCK.finditer(current_text):
        requirement_id = match.group("id")
        item_indent = match.group("indent")
        matched_ids.append(requirement_id)
        pieces.append(current_text[cursor : match.start()])
        pieces.append(match.group(0).rstrip())
        pieces.append("\n")
        pieces.append(criterion_block(requirement_id, mapping[requirement_id], item_indent))
        pieces.append("\n")
        cursor = match.end()
    pieces.append(current_text[cursor:])
    if matched_ids != requirement_ids:
        raise ValueError(
            f"text FR blocks do not match parsed metrics for {case_id}: "
            f"blocks={matched_ids}, metrics={requirement_ids}"
        )

    migrated = "".join(pieces).rstrip() + "\n"
    migrated_metric = load_yaml_text(migrated, f"migrated:{case_id}")
    before_fr = [(item["id"], item["text"]) for item in current_requirements]
    after_fr = [(item["id"], item["text"]) for item in migrated_metric["metrics"]]
    if after_fr != before_fr:
        raise ValueError(f"FR content changed while migrating {case_id}")

    total = sum(len(items) for items in mapping.values())
    summary = f"{case_id}: FRs={len(requirement_ids)} PCs={total}"
    if write:
        current_path.write_text(migrated, encoding="utf-8")
        summary += " written"
    return summary


def review_case(repository: Path, case_id: str, revision: str) -> str:
    relative = f"benchmarks/{case_id}/metric.yaml"
    current_metric = load_yaml_text(
        (repository / relative).read_text(encoding="utf-8"),
        str(repository / relative),
    )
    main_metric = load_yaml_text(
        git_show(repository, revision, relative),
        f"{revision}:{relative}",
    )
    mapping = criteria_by_requirement(main_metric)
    lines = [f"# {case_id}", ""]
    for requirement in current_metric["metrics"]:
        requirement_id = requirement["id"]
        lines.extend(
            [
                f"## {requirement_id}",
                "",
                requirement["text"],
                "",
            ]
        )
        for index, criterion in enumerate(mapping[requirement_id], 1):
            lines.append(f"- {requirement_id}-PC-{index}: {criterion}")
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("repository", type=Path)
    parser.add_argument("case_ids", nargs="+")
    parser.add_argument("--main-revision", default="origin/main")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--review-output", type=Path)
    args = parser.parse_args()

    repository = args.repository.resolve()
    review_sections: list[str] = []
    for case_id in args.case_ids:
        if args.review_output:
            review_sections.append(review_case(repository, case_id, args.main_revision))
        print(
            migrate_case(
                repository,
                case_id,
                args.main_revision,
                write=args.write,
            )
        )
    if args.review_output:
        args.review_output.write_text("\n\n".join(review_sections), encoding="utf-8")


if __name__ == "__main__":
    main()
