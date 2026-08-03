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
DESCRIPTION_SECTIONS = ("intent", "functional_requirements", "interfaces")


@dataclass(frozen=True)
class CaseSnapshot:
    """One description loaded once when the server starts."""

    case_id: str
    description_sha256: str
    description: dict[str, Any]

    @property
    def available_sections(self) -> list[str]:
        return [section for section in DESCRIPTION_SECTIONS if section in self.description]


class BenchmarkRegistry:
    """Validated, immutable view of public benchmark descriptions."""

    def __init__(self, repository_root: Path) -> None:
        self.repository_root = repository_root.resolve(strict=True)
        self.benchmarks_root = (self.repository_root / "benchmarks").resolve(strict=True)
        if not self.benchmarks_root.is_dir():
            raise ValueError(f"Benchmark directory not found: {self.benchmarks_root}")
        self._cases = self._load_cases()
        if not self._cases:
            raise ValueError(f"No valid benchmark cases found under {self.benchmarks_root}")

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
            reference_path = case_dir / "reference"
            if not self._is_regular_direct_file(description_path, resolved_case_dir):
                continue
            if not self._is_regular_direct_file(metric_path, resolved_case_dir):
                continue
            if (
                not reference_path.is_dir()
                or reference_path.is_symlink()
                or reference_path.resolve(strict=True).parent != resolved_case_dir
            ):
                continue

            raw_description = description_path.read_bytes()
            parsed = yaml.safe_load(raw_description)
            if not isinstance(parsed, dict):
                raise ValueError(f"Description must be a mapping: {description_path}")
            if not all(section in parsed for section in ("intent", "functional_requirements")):
                raise ValueError(f"Description is missing required sections: {description_path}")
            intent = parsed.get("intent")
            if not isinstance(intent, dict) or intent.get("package_name") != case_id:
                raise ValueError(
                    f"intent.package_name must match directory {case_id!r}: {description_path}"
                )

            cases[case_id] = CaseSnapshot(
                case_id=case_id,
                description_sha256=hashlib.sha256(raw_description).hexdigest(),
                description=parsed,
            )
        return cases

    @staticmethod
    def _is_regular_direct_file(path: Path, expected_parent: Path) -> bool:
        return (
            path.is_file()
            and not path.is_symlink()
            and path.resolve(strict=True).parent == expected_parent
        )


def resolve_repository_root(explicit_root: str | Path | None = None) -> Path:
    """Find a checkout containing both ``benchmarks`` and ``templates``."""

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
    if not (resolved / "benchmarks").is_dir() or not (resolved / "templates").is_dir():
        raise ValueError(
            f"Benchmark repository root must contain benchmarks/ and templates/: {resolved}"
        )
    return resolved
