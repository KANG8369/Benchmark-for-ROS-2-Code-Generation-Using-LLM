from __future__ import annotations

import copy
from pathlib import Path

import pytest
import yaml

from benchmark_mcp.registry import BenchmarkRegistry, resolve_repository_root

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def repository_case_ids(root: Path = REPOSITORY_ROOT) -> list[str]:
    return sorted(
        path.name
        for path in (root / "benchmarks").iterdir()
        if path.is_dir()
        and (path / "description.yaml").is_file()
        and (path / "metric.yaml").is_file()
    )


def valid_description() -> dict:
    return {
        "intent": {
            "package_name": "example_package",
            "summary": "Example package summary.",
            "scope": "Example package scope.",
        },
        "functional_requirements": [{"id": "FR-1", "text": "The package implements one behavior."}],
        "target_environment": "An example ROS 2 system.",
    }


def valid_metric() -> dict:
    return {
        "package_name": "example_package",
        "metrics": [
            {
                "id": "FR-1",
                "text": "The package implements one behavior.",
                "pass_criteria": [{"id": "FR-1-PC-1", "text": "The behavior is reachable."}],
            }
        ],
    }


def write_repository(
    root: Path,
    *,
    description: dict | None = None,
    metric: dict | None = None,
    with_reference: bool = False,
) -> Path:
    case_dir = root / "benchmarks" / "example_package"
    case_dir.mkdir(parents=True)
    (case_dir / "description.yaml").write_text(
        yaml.safe_dump(description or valid_description(), sort_keys=False),
        encoding="utf-8",
    )
    (case_dir / "metric.yaml").write_text(
        yaml.safe_dump(metric or valid_metric(), sort_keys=False),
        encoding="utf-8",
    )
    if with_reference:
        (case_dir / "reference").mkdir()
    return root


def test_catalog_discovers_all_repository_cases() -> None:
    registry = BenchmarkRegistry(REPOSITORY_ROOT)
    expected_ids = repository_case_ids()

    assert registry.case_ids == expected_ids
    catalog = registry.catalog_resource()
    assert catalog["case_count"] == len(expected_ids) == 17
    assert len(catalog["snapshot_sha256"]) == 64


def test_public_sections_share_the_same_snapshot_hash() -> None:
    registry = BenchmarkRegistry(REPOSITORY_ROOT)

    complete = registry.description_resource("turtlebot3_follower")
    requirements = registry.section_resource("turtlebot3_follower", "functional_requirements")
    target = registry.section_resource("turtlebot3_follower", "target_environment")

    assert complete["description_sha256"] == requirements["description_sha256"]
    assert complete["description_sha256"] == target["description_sha256"]
    assert requirements["present"] is True
    assert requirements["content"] == complete["description"]["functional_requirements"]
    assert target["present"] is True
    assert target["content"] == complete["description"]["target_environment"]


def test_optional_target_environment_is_reported_absent() -> None:
    registry = BenchmarkRegistry(REPOSITORY_ROOT)

    section = registry.section_resource("dummy_map_server", "target_environment")

    assert section["present"] is False
    assert section["content"] is None


@pytest.mark.parametrize(
    "case_id",
    ["../dummy_sensors", "dummy_sensors/metric", "dummy-sensors", ""],
)
def test_case_identifier_rejects_path_like_values(case_id: str) -> None:
    registry = BenchmarkRegistry(REPOSITORY_ROOT)

    with pytest.raises(ValueError):
        registry.description_resource(case_id)


@pytest.mark.parametrize("section", ["interfaces", "../metric", "metric"])
def test_section_is_an_allowlisted_top_level_name(section: str) -> None:
    registry = BenchmarkRegistry(REPOSITORY_ROOT)

    with pytest.raises(ValueError):
        registry.section_resource("dummy_sensors", section)


def test_explicit_repository_root_does_not_fall_back_to_current_directory(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError):
        resolve_repository_root(tmp_path / "missing")


def test_reference_directory_is_optional(tmp_path: Path) -> None:
    root = write_repository(tmp_path)

    registry = BenchmarkRegistry(root, include_metrics=True)

    assert registry.case_ids == ["example_package"]
    assert not (root / "benchmarks" / "example_package" / "reference").exists()


@pytest.mark.parametrize(
    ("mutate", "expected"),
    [
        (
            lambda description, metric: description.update({"interfaces": {}}),
            "unsupported sections",
        ),
        (
            lambda description, metric: description.update({"target_environment": ""}),
            "target_environment must be a non-empty string",
        ),
        (
            lambda description, metric: metric["metrics"][0].update(
                {"text": "A hidden behavior not present in the Description."}
            ),
            "Description and Metric FRs differ",
        ),
        (
            lambda description, metric: metric["metrics"][0].update({"pass_criteria": []}),
            "pass_criteria must be non-empty",
        ),
        (
            lambda description, metric: metric["metrics"][0]["pass_criteria"][0].update(
                {"evaluation": "static"}
            ),
            "must contain only id and text",
        ),
        (
            lambda description, metric: metric["metrics"][0]["pass_criteria"][0].update(
                {"id": "FR-1-PC-2"}
            ),
            "Expected sequential PC FR-1-PC-1",
        ),
    ],
)
def test_invalid_revised_schema_is_rejected(
    tmp_path: Path,
    mutate,
    expected: str,
) -> None:
    description = copy.deepcopy(valid_description())
    metric = copy.deepcopy(valid_metric())
    mutate(description, metric)
    root = write_repository(tmp_path, description=description, metric=metric)

    with pytest.raises(ValueError, match=expected):
        BenchmarkRegistry(root, include_metrics=True)
