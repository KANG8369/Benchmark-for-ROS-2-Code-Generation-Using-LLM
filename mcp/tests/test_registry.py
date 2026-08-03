from __future__ import annotations

from pathlib import Path

import pytest

from benchmark_mcp.registry import BenchmarkRegistry, resolve_repository_root

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def test_catalog_discovers_the_nine_repository_cases() -> None:
    registry = BenchmarkRegistry(REPOSITORY_ROOT)

    assert registry.case_ids == [
        "apriltag_ros",
        "dummy_map_server",
        "dummy_robot_bringup",
        "dummy_sensors",
        "human_detector",
        "image_proc",
        "image_tools",
        "turtlebot3_automatic_parking",
        "turtlebot3_follower",
    ]
    catalog = registry.catalog_resource()
    assert catalog["case_count"] == 9
    assert len(catalog["snapshot_sha256"]) == 64


def test_full_and_section_resources_share_the_same_snapshot_hash() -> None:
    registry = BenchmarkRegistry(REPOSITORY_ROOT)

    complete = registry.description_resource("dummy_sensors")
    section = registry.section_resource("dummy_sensors", "interfaces")

    assert complete["description_sha256"] == section["description_sha256"]
    assert section["present"] is True
    assert section["content"] == complete["description"]["interfaces"]


@pytest.mark.parametrize(
    "case_id",
    ["../dummy_sensors", "dummy_sensors/metric", "dummy-sensors", ""],
)
def test_case_identifier_rejects_path_like_values(case_id: str) -> None:
    registry = BenchmarkRegistry(REPOSITORY_ROOT)

    with pytest.raises(ValueError):
        registry.description_resource(case_id)


def test_section_is_an_allowlisted_top_level_name() -> None:
    registry = BenchmarkRegistry(REPOSITORY_ROOT)

    with pytest.raises(ValueError):
        registry.section_resource("dummy_sensors", "../metric")


def test_explicit_repository_root_does_not_fall_back_to_current_directory(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError):
        resolve_repository_root(tmp_path / "missing")
