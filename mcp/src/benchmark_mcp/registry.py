"""Immutable public benchmark snapshots exposed as MCP resources."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

CASE_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
DESCRIPTION_SECTIONS = ("intent", "functional_requirements", "target_environment")
DESCRIPTION_KEYS = frozenset(DESCRIPTION_SECTIONS)
INTENT_KEYS = frozenset({"package_name", "summary", "scope"})
FR_KEYS = frozenset({"id", "text"})
METRIC_KEYS = frozenset({"package_name", "metrics"})
METRIC_FR_KEYS = frozenset({"id", "text", "pass_criteria"})
PC_KEYS = frozenset({"id", "text"})


@dataclass(frozen=True)
class CaseSnapshot:
    """One description loaded once when the server starts."""

    case_id: str
    description_sha256: str
    description: dict[str, Any]
    requirement_identity: tuple[tuple[str, str], ...]

    @property
    def available_sections(self) -> list[str]:
        return [section for section in DESCRIPTION_SECTIONS if section in self.description]


@dataclass(frozen=True)
class MetricSnapshot:
    """One hidden metric loaded only by an evaluator-profile registry."""

    case_id: str
    metric_sha256: str
    metric: dict[str, Any]


class BenchmarkRegistry:
    """Validated, immutable view of public benchmark descriptions."""

    def __init__(self, repository_root: Path, *, include_metrics: bool = False) -> None:
        self.repository_root = repository_root.resolve(strict=True)
        self.benchmarks_root = (self.repository_root / "benchmarks").resolve(strict=True)
        if not self.benchmarks_root.is_dir():
            raise ValueError(f"Benchmark directory not found: {self.benchmarks_root}")
        self._cases = self._load_cases()
        if not self._cases:
            raise ValueError(f"No valid benchmark cases found under {self.benchmarks_root}")
        self._metrics = self._load_metrics() if include_metrics else None

    @property
    def case_ids(self) -> list[str]:
        return sorted(self._cases)

    def catalog_resource(self) -> dict[str, Any]:
        cases = []
        for case_id in self.case_ids:
            snapshot = self._cases[case_id]
            intent = snapshot.description.get("intent", {})
            cases.append(
                {
                    "case_id": case_id,
                    "package_name": intent.get("package_name"),
                    "summary": intent.get("summary"),
                    "description_sha256": snapshot.description_sha256,
                    "available_sections": snapshot.available_sections,
                    "description_uri": f"benchmark://cases/{case_id}/description",
                }
            )
        digest_input = json.dumps(cases, ensure_ascii=False, sort_keys=True).encode("utf-8")
        return {
            "snapshot_sha256": hashlib.sha256(digest_input).hexdigest(),
            "case_count": len(cases),
            "cases": cases,
        }

    def description_resource(self, case_id: str) -> dict[str, Any]:
        snapshot = self._get_case(case_id)
        return {
            "case_id": case_id,
            "description_sha256": snapshot.description_sha256,
            "description": copy.deepcopy(snapshot.description),
        }

    def section_resource(self, case_id: str, section: str) -> dict[str, Any]:
        snapshot = self._get_case(case_id)
        if section not in DESCRIPTION_SECTIONS:
            allowed = ", ".join(DESCRIPTION_SECTIONS)
            raise ValueError(f"Unknown description section {section!r}; expected one of: {allowed}")
        return {
            "case_id": case_id,
            "description_sha256": snapshot.description_sha256,
            "section": section,
            "present": section in snapshot.description,
            "content": copy.deepcopy(snapshot.description.get(section)),
        }

    def metric_resource(self, case_id: str) -> dict[str, Any]:
        if self._metrics is None:
            raise PermissionError("Hidden metric resources are unavailable in this server profile")
        self._get_case(case_id)
        snapshot = self._metrics[case_id]
        return {
            "case_id": case_id,
            "metric_sha256": snapshot.metric_sha256,
            "metric": copy.deepcopy(snapshot.metric),
        }

    def _get_case(self, case_id: str) -> CaseSnapshot:
        if not CASE_ID_PATTERN.fullmatch(case_id):
            raise ValueError(f"Invalid benchmark case identifier: {case_id!r}")
        try:
            return self._cases[case_id]
        except KeyError as exc:
            raise ValueError(f"Unknown benchmark case: {case_id}") from exc

    def _load_cases(self) -> dict[str, CaseSnapshot]:
        cases: dict[str, CaseSnapshot] = {}
        for case_dir in sorted(self.benchmarks_root.iterdir(), key=lambda path: path.name):
            if not case_dir.is_dir() or case_dir.is_symlink():
                continue
            case_id = case_dir.name
            if not CASE_ID_PATTERN.fullmatch(case_id):
                continue

            resolved_case_dir = case_dir.resolve(strict=True)
            if resolved_case_dir.parent != self.benchmarks_root:
                continue

            description_path = case_dir / "description.yaml"
            metric_path = case_dir / "metric.yaml"
            if not self._is_regular_direct_file(description_path, resolved_case_dir):
                continue
            if not self._is_regular_direct_file(metric_path, resolved_case_dir):
                continue

            raw_description = description_path.read_bytes()
            parsed = yaml.safe_load(raw_description)
            requirement_identity = self._validate_description(case_id, parsed, description_path)
            self._read_metric_snapshot(case_id, metric_path, requirement_identity)

            cases[case_id] = CaseSnapshot(
                case_id=case_id,
                description_sha256=hashlib.sha256(raw_description).hexdigest(),
                description=parsed,
                requirement_identity=requirement_identity,
            )
        return cases

    def _load_metrics(self) -> dict[str, MetricSnapshot]:
        metrics: dict[str, MetricSnapshot] = {}
        for case_id in self.case_ids:
            metric_path = self.benchmarks_root / case_id / "metric.yaml"
            metrics[case_id] = self._read_metric_snapshot(
                case_id,
                metric_path,
                self._cases[case_id].requirement_identity,
            )
        return metrics

    @classmethod
    def _validate_description(
        cls,
        case_id: str,
        parsed: Any,
        description_path: Path,
    ) -> tuple[tuple[str, str], ...]:
        if not isinstance(parsed, dict):
            raise ValueError(f"Description must be a mapping: {description_path}")
        keys = set(parsed)
        required = {"intent", "functional_requirements"}
        if not required.issubset(keys):
            raise ValueError(f"Description is missing required sections: {description_path}")
        unexpected = keys - DESCRIPTION_KEYS
        if unexpected:
            raise ValueError(
                f"Description contains unsupported sections {sorted(unexpected)}: "
                f"{description_path}"
            )

        intent = parsed["intent"]
        if not isinstance(intent, dict):
            raise ValueError(f"intent must be a mapping: {description_path}")
        if set(intent) - INTENT_KEYS or not {"package_name", "summary"}.issubset(intent):
            raise ValueError(f"intent contains invalid fields: {description_path}")
        if intent.get("package_name") != case_id:
            raise ValueError(
                f"intent.package_name must match directory {case_id!r}: {description_path}"
            )
        for field in ("package_name", "summary"):
            cls._require_nonempty_string(intent.get(field), f"intent.{field}", description_path)
        if "scope" in intent:
            cls._require_nonempty_string(intent["scope"], "intent.scope", description_path)

        if "target_environment" in parsed:
            cls._require_nonempty_string(
                parsed["target_environment"], "target_environment", description_path
            )

        requirements = parsed["functional_requirements"]
        if not isinstance(requirements, list) or not requirements:
            raise ValueError(f"functional_requirements must be non-empty: {description_path}")
        identity: list[tuple[str, str]] = []
        for index, requirement in enumerate(requirements, 1):
            expected_id = f"FR-{index}"
            if not isinstance(requirement, dict) or set(requirement) != FR_KEYS:
                raise ValueError(f"{expected_id} must contain only id and text: {description_path}")
            if requirement.get("id") != expected_id:
                raise ValueError(
                    f"Expected sequential requirement {expected_id}: {description_path}"
                )
            text = cls._require_nonempty_string(
                requirement.get("text"), f"{expected_id}.text", description_path
            )
            identity.append((expected_id, text))
        return tuple(identity)

    @classmethod
    def _read_metric_snapshot(
        cls,
        case_id: str,
        metric_path: Path,
        public_identity: tuple[tuple[str, str], ...],
    ) -> MetricSnapshot:
        raw_metric = metric_path.read_bytes()
        parsed = yaml.safe_load(raw_metric)
        if not isinstance(parsed, dict) or set(parsed) != METRIC_KEYS:
            raise ValueError(f"Metric must contain only package_name and metrics: {metric_path}")
        if parsed.get("package_name") != case_id:
            raise ValueError(f"metric.package_name must match directory {case_id!r}: {metric_path}")
        requirements = parsed.get("metrics")
        if not isinstance(requirements, list) or not requirements:
            raise ValueError(f"metrics must be a non-empty list: {metric_path}")
        hidden_identity: list[tuple[str, str]] = []
        for requirement_index, requirement in enumerate(requirements, 1):
            expected_id = f"FR-{requirement_index}"
            if not isinstance(requirement, dict) or set(requirement) != METRIC_FR_KEYS:
                raise ValueError(
                    f"Metric {expected_id} must contain only id, text, and pass_criteria: "
                    f"{metric_path}"
                )
            if requirement.get("id") != expected_id:
                raise ValueError(f"Expected sequential Metric FR {expected_id}: {metric_path}")
            text = cls._require_nonempty_string(
                requirement.get("text"), f"metric {expected_id}.text", metric_path
            )
            hidden_identity.append((expected_id, text))

            criteria = requirement.get("pass_criteria")
            if not isinstance(criteria, list) or not criteria:
                raise ValueError(f"{expected_id}.pass_criteria must be non-empty: {metric_path}")
            for criterion_index, criterion in enumerate(criteria, 1):
                expected_pc_id = f"{expected_id}-PC-{criterion_index}"
                if not isinstance(criterion, dict) or set(criterion) != PC_KEYS:
                    raise ValueError(
                        f"{expected_pc_id} must contain only id and text: {metric_path}"
                    )
                if criterion.get("id") != expected_pc_id:
                    raise ValueError(f"Expected sequential PC {expected_pc_id}: {metric_path}")
                cls._require_nonempty_string(
                    criterion.get("text"), f"{expected_pc_id}.text", metric_path
                )

        if tuple(hidden_identity) != public_identity:
            raise ValueError(f"Description and Metric FRs differ: {metric_path}")
        return MetricSnapshot(
            case_id=case_id,
            metric_sha256=hashlib.sha256(raw_metric).hexdigest(),
            metric=parsed,
        )

    @staticmethod
    def _require_nonempty_string(value: Any, field: str, path: Path) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{field} must be a non-empty string: {path}")
        return value

    @staticmethod
    def _is_regular_direct_file(path: Path, expected_parent: Path) -> bool:
        return (
            path.is_file()
            and not path.is_symlink()
            and path.resolve(strict=True).parent == expected_parent
        )


def resolve_repository_root(explicit_root: str | Path | None = None) -> Path:
    """Find a checkout containing a ``benchmarks`` directory."""

    if explicit_root is not None:
        return _validate_repository_root(Path(explicit_root))
    environment_root = os.environ.get("ROS2_BENCHMARK_ROOT")
    if environment_root:
        return _validate_repository_root(Path(environment_root))

    candidates: list[Path] = []
    for start in (Path.cwd(), Path(__file__).resolve()):
        candidates.extend((start, *start.parents))

    seen: set[Path] = set()
    for candidate in candidates:
        try:
            resolved = candidate.expanduser().resolve(strict=True)
        except OSError:
            continue
        if resolved in seen:
            continue
        seen.add(resolved)
        try:
            return _validate_repository_root(resolved)
        except ValueError:
            continue

    raise ValueError(
        "Could not locate the benchmark repository. Pass --repo-root or set ROS2_BENCHMARK_ROOT."
    )


def _validate_repository_root(candidate: Path) -> Path:
    try:
        resolved = candidate.expanduser().resolve(strict=True)
    except OSError as exc:
        raise ValueError(f"Benchmark repository root does not exist: {candidate}") from exc
    if not (resolved / "benchmarks").is_dir():
        raise ValueError(f"Benchmark repository root must contain benchmarks/: {resolved}")
    return resolved
