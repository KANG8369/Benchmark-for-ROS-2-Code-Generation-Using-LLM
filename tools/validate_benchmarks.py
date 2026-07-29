#!/usr/bin/env python3

import argparse
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET

try:
    import yaml
except ImportError as exc:
    raise SystemExit(
        "PyYAML is required: install it with `python3 -m pip install PyYAML`."
    ) from exc


REPO_ROOT = Path(__file__).resolve().parents[1]
BENCHMARKS_ROOT = REPO_ROOT / "benchmarks"
EVALUATION_METHODS = {"static", "dynamic", "hybrid"}
EVIDENCE_KINDS = {
    "source_code",
    "launch",
    "config",
    "build",
    "manifest",
    "resource",
}


def normalize_newlines(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def read_yaml(path: Path) -> dict:
    with path.open(encoding="utf-8") as stream:
        document = yaml.safe_load(stream)
    if not isinstance(document, dict):
        raise ValueError(f"{path}: expected a YAML mapping")
    return document


def reference_package_name(reference_root: Path) -> str:
    manifest = reference_root / "package.xml"
    if not manifest.is_file():
        raise ValueError(f"{manifest}: missing reference package manifest")
    try:
        name = ET.parse(manifest).getroot().findtext("name")
    except ET.ParseError as exc:
        raise ValueError(f"{manifest}: invalid XML: {exc}") from exc
    if not name:
        raise ValueError(f"{manifest}: package name is missing")
    return name


def validate_case(case_root: Path, static_only: bool) -> tuple[int, int, int]:
    package_name = case_root.name
    description_path = case_root / "description.yaml"
    metric_path = case_root / "metric.yaml"
    reference_root = case_root / "reference"

    if not description_path.is_file() or not metric_path.is_file():
        raise ValueError(
            f"{package_name}: description.yaml and metric.yaml are both required"
        )

    description = read_yaml(description_path)
    metric_document = read_yaml(metric_path)
    metric_source = metric_path.read_text(encoding="utf-8")

    description_package = description.get("intent", {}).get("package_name")
    metric_package = metric_document.get("package_name")
    manifest_package = reference_package_name(reference_root)
    if {description_package, metric_package, manifest_package} != {package_name}:
        raise ValueError(
            f"{package_name}: package names disagree: description={description_package!r}, "
            f"metric={metric_package!r}, reference={manifest_package!r}"
        )

    if metric_document.get("schema_version") != "2.0":
        raise ValueError(f"{package_name}: metric schema_version must be '2.0'")
    if metric_document.get("reference") != {"root": "reference/"}:
        raise ValueError(f"{package_name}: reference.root must be 'reference/'")
    if metric_document.get("evaluation_policy") != {
        "equivalence": "semantic",
        "exact_constants_only_when_specified": True,
    }:
        raise ValueError(f"{package_name}: unsupported evaluation_policy")
    if re.search(r"(?m)^\s*requirement_ids:\s*\[", metric_source):
        raise ValueError(
            f"{package_name}: requirement_ids must use YAML block-list style"
        )

    requirements = description.get("functional_requirements")
    if not isinstance(requirements, list) or not requirements:
        raise ValueError(f"{package_name}: functional_requirements must be non-empty")
    expected_requirement_ids = {requirement["id"] for requirement in requirements}

    metrics = metric_document.get("metrics")
    if not isinstance(metrics, list) or not metrics:
        raise ValueError(f"{package_name}: metrics must be non-empty")

    covered_requirement_ids = set()
    metric_ids = set()
    criterion_ids = set()
    criterion_count = 0
    evidence_count = 0
    resolved_reference_root = reference_root.resolve()

    for metric in metrics:
        metric_id = metric["id"]
        if metric_id in metric_ids:
            raise ValueError(f"{package_name}: duplicate metric ID {metric_id}")
        metric_ids.add(metric_id)

        requirement_ids = metric.get("requirement_ids")
        if not isinstance(requirement_ids, list) or not requirement_ids:
            raise ValueError(
                f"{package_name}: {metric_id} requirement_ids must be a non-empty list"
            )
        unknown_requirement_ids = set(requirement_ids) - expected_requirement_ids
        if unknown_requirement_ids:
            raise ValueError(
                f"{package_name}: {metric_id} references unknown requirements "
                f"{sorted(unknown_requirement_ids)}"
            )
        covered_requirement_ids.update(requirement_ids)

        criteria = metric.get("pass_criteria")
        if not isinstance(criteria, list) or not criteria:
            raise ValueError(f"{package_name}: {metric_id} has no pass criteria")

        for criterion in criteria:
            criterion_count += 1
            criterion_id = criterion["id"]
            if criterion_id in criterion_ids:
                raise ValueError(
                    f"{package_name}: duplicate pass criterion ID {criterion_id}"
                )
            criterion_ids.add(criterion_id)

            evaluation = criterion.get("evaluation")
            if evaluation not in EVALUATION_METHODS:
                raise ValueError(
                    f"{package_name}: {criterion_id} has invalid evaluation "
                    f"{evaluation!r}"
                )
            if static_only and evaluation != "static":
                raise ValueError(
                    f"{package_name}: {criterion_id} is not static-only"
                )

            evidence_items = criterion.get("reference_evidence")
            if not isinstance(evidence_items, list) or not evidence_items:
                raise ValueError(
                    f"{package_name}: {criterion_id} has no reference evidence"
                )

            for evidence in evidence_items:
                evidence_count += 1
                kind = evidence.get("kind")
                if kind not in EVIDENCE_KINDS:
                    raise ValueError(
                        f"{package_name}: {criterion_id} evidence has invalid kind "
                        f"{kind!r}"
                    )

                relative_path = evidence.get("path")
                if not isinstance(relative_path, str) or not relative_path:
                    raise ValueError(
                        f"{package_name}: {criterion_id} evidence has no path"
                    )
                evidence_path = (reference_root / relative_path).resolve()
                if (
                    evidence_path != resolved_reference_root
                    and resolved_reference_root not in evidence_path.parents
                ):
                    raise ValueError(
                        f"{package_name}: evidence escapes reference root: "
                        f"{relative_path}"
                    )
                if not evidence_path.is_file():
                    raise ValueError(
                        f"{package_name}: missing evidence path {relative_path}"
                    )

                locator = evidence.get("locator")
                if not isinstance(locator, str) or not locator:
                    raise ValueError(
                        f"{package_name}: evidence {relative_path} has no locator"
                    )
                source_text = normalize_newlines(
                    evidence_path.read_text(encoding="utf-8", errors="ignore")
                )
                locator_candidates = {
                    locator,
                    locator.split("::")[-1],
                    locator.split(".")[-1],
                }
                if not any(
                    candidate in source_text for candidate in locator_candidates
                ):
                    raise ValueError(
                        f"{package_name}: {criterion_id} locator {locator!r} was not found "
                        f"in {relative_path}"
                    )

                snippet = evidence.get("snippet")
                if not isinstance(snippet, str) or not snippet.strip():
                    raise ValueError(
                        f"{package_name}: evidence {relative_path} has no snippet"
                    )
                normalized_snippet = normalize_newlines(snippet)
                if normalized_snippet not in source_text:
                    raise ValueError(
                        f"{package_name}: {criterion_id} evidence snippet is not an "
                        f"exact contiguous excerpt of {relative_path}"
                    )

                if not evidence.get("explanation"):
                    raise ValueError(
                        f"{package_name}: evidence {relative_path} has no explanation"
                    )

    if covered_requirement_ids != expected_requirement_ids:
        raise ValueError(
            f"{package_name}: requirement coverage mismatch; "
            f"expected {sorted(expected_requirement_ids)}, "
            f"covered {sorted(covered_requirement_ids)}"
        )

    return len(metric_ids), criterion_count, evidence_count


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--static-only",
        action="store_true",
        help="Require every pass criterion to use static evaluation.",
    )
    args = parser.parse_args()

    case_roots = sorted(
        path
        for path in BENCHMARKS_ROOT.iterdir()
        if path.is_dir() and not path.name.startswith(".")
    )
    if not case_roots:
        raise ValueError("No benchmark cases were found")

    total_metrics = 0
    total_criteria = 0
    total_evidence = 0
    for case_root in case_roots:
        metrics, criteria, evidence = validate_case(case_root, args.static_only)
        total_metrics += metrics
        total_criteria += criteria
        total_evidence += evidence
        print(
            f"PASS {case_root.name}: {metrics} metrics, {criteria} criteria, "
            f"{evidence} evidence items"
        )

    print(
        f"PASS all: {len(case_roots)} packages, {total_metrics} metrics, "
        f"{total_criteria} criteria, {total_evidence} evidence items"
    )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (KeyError, TypeError, ValueError) as exc:
        raise SystemExit(f"ERROR: {exc}") from exc
