from __future__ import annotations

import os
from pathlib import Path

import pytest

from benchmark_mcp.artifacts import ArtifactStore
from benchmark_mcp.schemas import PackageFile
from benchmark_mcp.services import (
    BuildService,
    InterfaceService,
    snapshot_sha256,
    validate_package_snapshot,
)

PACKAGE_XML = """<?xml version="1.0"?>
<package format="3">
  <name>demo_package</name>
  <version>0.0.0</version>
  <description>Test package</description>
  <maintainer email="test@example.com">Test</maintainer>
  <license>Apache-2.0</license>
  <buildtool_depend>ament_cmake</buildtool_depend>
  <export><build_type>ament_cmake</build_type></export>
</package>
"""

CMAKELISTS = """cmake_minimum_required(VERSION 3.8)
project(demo_package)
find_package(ament_cmake REQUIRED)
ament_package()
"""


def package_files() -> list[PackageFile]:
    return [
        PackageFile(path="package.xml", content=PACKAGE_XML),
        PackageFile(path="CMakeLists.txt", content=CMAKELISTS),
    ]


def write_executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


def test_interface_show_uses_fixed_argv_and_returns_a_hash(tmp_path: Path) -> None:
    fake_ros2 = tmp_path / "ros2"
    write_executable(
        fake_ros2,
        """#!/usr/bin/env python3
import sys
if sys.argv[1:] == ["interface", "show", "sensor_msgs/msg/LaserScan"]:
    print("std_msgs/Header header")
    raise SystemExit(0)
print("Unknown interface", file=sys.stderr)
raise SystemExit(1)
""",
    )
    service = InterfaceService(ros2_path=fake_ros2, environment=os.environ)

    result = service.show("sensor_msgs/msg/LaserScan")

    assert result.found is True
    assert result.definition == "std_msgs/Header header\n"
    assert result.definition_sha256 is not None
    assert result.error_kind is None


def test_interface_show_rejects_command_injection_before_execution(
    tmp_path: Path,
) -> None:
    marker = tmp_path / "should-not-exist"
    service = InterfaceService(ros2_path=tmp_path / "missing", environment=os.environ)

    result = service.show(f"sensor_msgs/msg/LaserScan;touch {marker}")

    assert result.found is False
    assert result.error_kind == "invalid_request"
    assert not marker.exists()


@pytest.mark.parametrize(
    "invalid_path",
    ["../escape", "/tmp/escape", "nested\\escape", "build/output", "a//b"],
)
def test_package_snapshot_rejects_unsafe_paths(invalid_path: str) -> None:
    files = [*package_files(), PackageFile(path=invalid_path, content="bad")]

    assert validate_package_snapshot("demo_package", files)


def test_package_snapshot_rejects_duplicates_and_manifest_mismatch() -> None:
    files = [*package_files(), PackageFile(path="package.xml", content=PACKAGE_XML)]
    errors = validate_package_snapshot("another_package", files)

    assert any("duplicate" in error for error in errors)
    assert any("must exactly match" in error for error in errors)


def test_package_snapshot_rejects_file_and_parent_path_conflicts() -> None:
    files = [
        *package_files(),
        PackageFile(path="config", content="file"),
        PackageFile(path="config/settings.yaml", content="key: value"),
    ]

    errors = validate_package_snapshot("demo_package", files)

    assert any("conflicts with a parent path" in error for error in errors)


def test_snapshot_hash_is_order_independent_and_content_sensitive() -> None:
    files = package_files()

    assert snapshot_sha256("demo_package", files) == snapshot_sha256(
        "demo_package", list(reversed(files))
    )
    modified = [
        files[0],
        files[1].model_copy(update={"content": CMAKELISTS + "\n# change"}),
    ]
    assert snapshot_sha256("demo_package", files) != snapshot_sha256("demo_package", modified)


def test_build_materializes_a_fresh_workspace_and_enforces_budget(
    tmp_path: Path,
) -> None:
    fake_colcon = tmp_path / "fake-colcon"
    write_executable(
        fake_colcon,
        """#!/usr/bin/env python3
from pathlib import Path
import sys
package = Path.cwd() / "src" / "demo_package"
if not (package / "package.xml").is_file():
    print("missing package", file=sys.stderr)
    raise SystemExit(2)
print("fake build passed")
""",
    )
    workspace_root = tmp_path / "workspaces"
    artifact_store = ArtifactStore(tmp_path / "artifacts")
    service = BuildService(
        workspace_root=workspace_root,
        colcon_path=fake_colcon,
        max_build_calls=1,
        allow_unsafe_local_builds=True,
        environment=os.environ,
        artifact_store=artifact_store,
    )

    first = service.build("demo_package", package_files())
    second = service.build("demo_package", package_files())

    assert first.status == "passed"
    assert first.success is True
    assert "fake build passed" in first.stdout
    assert first.workspace_retained is False
    assert first.artifact_recorded is True
    artifact = artifact_store.package_resource(first.build_id)
    assert artifact["snapshot_sha256"] == first.snapshot_sha256
    assert artifact["build"]["artifact_recorded"] is True
    cmake_file = next(item for item in artifact["files"] if item["path"] == "CMakeLists.txt")
    assert (
        artifact_store.file_resource(first.build_id, cmake_file["file_id"])["content"] == CMAKELISTS
    )
    assert list(workspace_root.iterdir()) == []
    assert second.status == "budget_exhausted"


def test_local_build_requires_explicit_operator_opt_in(tmp_path: Path) -> None:
    service = BuildService(workspace_root=tmp_path, max_build_calls=1)

    result = service.build("demo_package", package_files())

    assert result.status == "unavailable"
    assert "--allow-unsafe-local-build" in result.stderr


def test_build_timeout_is_structured_and_workspace_is_removed(tmp_path: Path) -> None:
    fake_colcon = tmp_path / "slow-colcon"
    write_executable(
        fake_colcon,
        """#!/usr/bin/env python3
import time
time.sleep(10)
""",
    )
    workspace_root = tmp_path / "workspaces"
    service = BuildService(
        workspace_root=workspace_root,
        colcon_path=fake_colcon,
        timeout_seconds=1,
        allow_unsafe_local_builds=True,
        environment=os.environ,
    )

    result = service.build("demo_package", package_files())

    assert result.status == "timed_out"
    assert result.timed_out is True
    assert result.exit_code is None
    assert result.workspace_retained is False
    assert list(workspace_root.iterdir()) == []
