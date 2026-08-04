"""ROS command services used by the MCP tool handlers."""

from __future__ import annotations

import contextlib
import hashlib
import os
import re
import shutil
import signal
import subprocess
import threading
import time
import uuid
import xml.etree.ElementTree as ET
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Protocol

from benchmark_mcp.schemas import BuildResult, InterfaceShowResult, PackageFile
from benchmark_mcp.snapshot import snapshot_sha256

PACKAGE_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
INTERFACE_TYPE_PATTERN = re.compile(r"^[a-z][a-z0-9_]*/(msg|srv|action)/[A-Za-z][A-Za-z0-9_]*$")
RESERVED_TOP_LEVEL_PATHS = {".git", "build", "install", "log"}
MAX_PACKAGE_FILES = 256
MAX_FILE_BYTES = 2 * 1024 * 1024
MAX_PACKAGE_BYTES = 20 * 1024 * 1024


@dataclass(frozen=True)
class ProcessOutcome:
    """Captured result from a subprocess, including timeout state."""

    exit_code: int | None
    stdout: str
    stderr: str
    timed_out: bool
    duration_ms: int


def run_process(
    command: Sequence[str],
    *,
    cwd: Path | None,
    environment: Mapping[str, str],
    timeout_seconds: int,
) -> ProcessOutcome:
    """Run one fixed argv command and kill its process group on timeout."""

    started = time.monotonic()
    process = subprocess.Popen(
        list(command),
        cwd=cwd,
        env=dict(environment),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        start_new_session=True,
    )
    timed_out = False
    try:
        stdout, stderr = process.communicate(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        timed_out = True
        with contextlib.suppress(ProcessLookupError):
            os.killpg(process.pid, signal.SIGKILL)
        stdout, stderr = process.communicate()
    duration_ms = round((time.monotonic() - started) * 1000)
    return ProcessOutcome(
        exit_code=None if timed_out else process.returncode,
        stdout=stdout,
        stderr=stderr,
        timed_out=timed_out,
        duration_ms=duration_ms,
    )


def load_clean_ros_environment(ros_distro: str) -> dict[str, str]:
    """Load only the selected system ROS installation into a clean environment."""

    if ros_distro != "jazzy":
        raise ValueError("This benchmark server currently supports ROS 2 Jazzy only")
    setup_file = Path("/opt/ros") / ros_distro / "setup.bash"
    if not setup_file.is_file():
        raise FileNotFoundError(f"ROS setup file not found: {setup_file}")

    base_path = "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
    command = [
        "/usr/bin/env",
        "-i",
        f"PATH={base_path}",
        "LANG=C.UTF-8",
        "/bin/bash",
        "--noprofile",
        "--norc",
        "-c",
        f"source {setup_file} >/dev/null 2>&1 && env -0",
    ]
    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        timeout=15,
    )
    if completed.returncode != 0:
        stderr = completed.stderr.decode("utf-8", errors="replace")
        raise RuntimeError(f"Failed to load ROS environment: {stderr.strip()}")

    environment: dict[str, str] = {}
    for entry in completed.stdout.split(b"\0"):
        if not entry or b"=" not in entry:
            continue
        key, value = entry.split(b"=", 1)
        environment[key.decode("utf-8")] = value.decode("utf-8", errors="replace")
    environment["PYTHONNOUSERSITE"] = "1"
    environment["ROS_AUTOMATIC_DISCOVERY_RANGE"] = "OFF"
    return environment


class ArtifactRecorder(Protocol):
    """Minimal writer contract used by a build backend."""

    def record(
        self,
        *,
        run_id: str,
        package_name: str,
        files: list[PackageFile],
        build_result: BuildResult,
    ) -> None: ...


def validate_package_snapshot(package_name: str, files: Sequence[PackageFile]) -> list[str]:
    """Validate names, limits, paths, and the manifest before materialization."""

    errors: list[str] = []
    if not PACKAGE_NAME_PATTERN.fullmatch(package_name):
        errors.append("package_name must match ^[a-z][a-z0-9_]*$")
    if not files:
        errors.append("files must contain the complete package snapshot")
        return errors
    if len(files) > MAX_PACKAGE_FILES:
        errors.append(f"package contains more than {MAX_PACKAGE_FILES} files")

    seen_paths: set[str] = set()
    total_bytes = 0
    package_xml_content: str | None = None
    for package_file in files:
        path = package_file.path
        if not path or "\x00" in path:
            errors.append("file paths must be non-empty and contain no NUL bytes")
            continue
        if "\\" in path:
            errors.append(f"file path must use POSIX separators: {path!r}")
            continue
        pure_path = PurePosixPath(path)
        if pure_path.is_absolute() or any(part in ("", ".", "..") for part in pure_path.parts):
            errors.append(f"file path must be normalized and relative: {path!r}")
            continue
        if pure_path.as_posix() != path:
            errors.append(f"file path must be normalized: {path!r}")
            continue
        if pure_path.parts[0] in RESERVED_TOP_LEVEL_PATHS:
            errors.append(f"reserved top-level path is not allowed: {path!r}")
            continue
        if path in seen_paths:
            errors.append(f"duplicate file path: {path!r}")
            continue
        seen_paths.add(path)

        content_bytes = package_file.content.encode("utf-8")
        if b"\x00" in content_bytes:
            errors.append(f"file content must be UTF-8 text without NUL bytes: {path!r}")
        if len(content_bytes) > MAX_FILE_BYTES:
            errors.append(f"file exceeds the {MAX_FILE_BYTES}-byte limit: {path!r}")
        total_bytes += len(content_bytes)
        if path == "package.xml":
            package_xml_content = package_file.content

    if total_bytes > MAX_PACKAGE_BYTES:
        errors.append(f"package exceeds the {MAX_PACKAGE_BYTES}-byte total limit")
    for path in seen_paths:
        parent = PurePosixPath(path).parent
        while parent != PurePosixPath("."):
            if parent.as_posix() in seen_paths:
                errors.append(
                    f"file path conflicts with a parent path that is also a file: {path!r}"
                )
                break
            parent = parent.parent
    if package_xml_content is None:
        errors.append("the complete package snapshot must include package.xml")
    else:
        try:
            root = ET.fromstring(package_xml_content)
            manifest_name = root.findtext("name")
        except ET.ParseError as exc:
            errors.append(f"package.xml is not well-formed XML: {exc}")
        else:
            if manifest_name != package_name:
                errors.append(
                    "package.xml <name> must exactly match package_name "
                    f"({manifest_name!r} != {package_name!r})"
                )
    return errors


def _truncate_text(text: str, limit_bytes: int, *, keep_tail: bool) -> tuple[str, bool]:
    encoded = text.encode("utf-8")
    if len(encoded) <= limit_bytes:
        return text, False
    marker = "\n...[output truncated]...\n"
    marker_bytes = marker.encode("utf-8")
    remaining = max(0, limit_bytes - len(marker_bytes))
    selected = b"" if remaining == 0 else encoded[-remaining:] if keep_tail else encoded[:remaining]
    decoded = selected.decode("utf-8", errors="replace")
    return (marker + decoded if keep_tail else decoded + marker), True


class InterfaceService:
    """Read installed interface definitions with a fixed command contract."""

    def __init__(
        self,
        *,
        ros_distro: str = "jazzy",
        ros2_path: str | Path | None = None,
        timeout_seconds: int = 10,
        max_output_bytes: int = 256 * 1024,
        environment: Mapping[str, str] | None = None,
    ) -> None:
        self.ros_distro = ros_distro
        default_path = Path("/opt/ros") / ros_distro / "bin" / "ros2"
        self.ros2_path = Path(ros2_path) if ros2_path else default_path
        self.timeout_seconds = timeout_seconds
        self.max_output_bytes = max_output_bytes
        self._environment = dict(environment) if environment is not None else None
        self._cache: dict[str, InterfaceShowResult] = {}
        self._lock = threading.Lock()

    def show(self, interface_type: str) -> InterfaceShowResult:
        started = time.monotonic()
        if not INTERFACE_TYPE_PATTERN.fullmatch(interface_type):
            return InterfaceShowResult(
                interface_type=interface_type,
                ros_distro=self.ros_distro,
                found=False,
                definition=None,
                definition_sha256=None,
                exit_code=None,
                stderr="interface_type must use package/(msg|srv|action)/Type syntax",
                duration_ms=round((time.monotonic() - started) * 1000),
                output_truncated=False,
                error_kind="invalid_request",
            )

        with self._lock:
            cached = self._cache.get(interface_type)
        if cached is not None:
            return cached.model_copy(deep=True)

        if not self.ros2_path.is_file() or not os.access(self.ros2_path, os.X_OK):
            return InterfaceShowResult(
                interface_type=interface_type,
                ros_distro=self.ros_distro,
                found=False,
                definition=None,
                definition_sha256=None,
                exit_code=None,
                stderr=f"ros2 executable not found: {self.ros2_path}",
                duration_ms=round((time.monotonic() - started) * 1000),
                output_truncated=False,
                error_kind="configuration",
            )

        try:
            environment = self._environment or load_clean_ros_environment(self.ros_distro)
            outcome = run_process(
                [str(self.ros2_path), "interface", "show", interface_type],
                cwd=None,
                environment=environment,
                timeout_seconds=self.timeout_seconds,
            )
        except (OSError, RuntimeError, ValueError) as exc:
            return InterfaceShowResult(
                interface_type=interface_type,
                ros_distro=self.ros_distro,
                found=False,
                definition=None,
                definition_sha256=None,
                exit_code=None,
                stderr=str(exc),
                duration_ms=round((time.monotonic() - started) * 1000),
                output_truncated=False,
                error_kind="configuration",
            )

        definition, stdout_truncated = _truncate_text(
            outcome.stdout,
            self.max_output_bytes,
            keep_tail=False,
        )
        stderr, stderr_truncated = _truncate_text(
            outcome.stderr,
            self.max_output_bytes,
            keep_tail=True,
        )
        found = not outcome.timed_out and outcome.exit_code == 0
        result = InterfaceShowResult(
            interface_type=interface_type,
            ros_distro=self.ros_distro,
            found=found,
            definition=definition if found else None,
            definition_sha256=(
                hashlib.sha256(outcome.stdout.encode("utf-8")).hexdigest() if found else None
            ),
            exit_code=outcome.exit_code,
            stderr=stderr,
            duration_ms=outcome.duration_ms,
            output_truncated=stdout_truncated or stderr_truncated,
            error_kind=(None if found else "timeout" if outcome.timed_out else "not_found"),
        )
        with self._lock:
            self._cache[interface_type] = result.model_copy(deep=True)
        return result


class BuildService:
    """Materialize and build complete package snapshots in fresh workspaces."""

    def __init__(
        self,
        *,
        workspace_root: str | Path,
        ros_distro: str = "jazzy",
        colcon_path: str | Path = "/usr/bin/colcon",
        timeout_seconds: int = 300,
        max_build_calls: int = 1,
        max_output_bytes: int = 512 * 1024,
        allow_unsafe_local_builds: bool = False,
        keep_workspaces: bool = False,
        environment: Mapping[str, str] | None = None,
        artifact_store: ArtifactRecorder | None = None,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if max_build_calls < 0:
            raise ValueError("max_build_calls must be non-negative")
        self.workspace_root = Path(workspace_root).expanduser().resolve()
        self.ros_distro = ros_distro
        self.colcon_path = Path(colcon_path)
        self.timeout_seconds = timeout_seconds
        self.max_build_calls = max_build_calls
        self.max_output_bytes = max_output_bytes
        self.allow_unsafe_local_builds = allow_unsafe_local_builds
        self.keep_workspaces = keep_workspaces
        self._environment = dict(environment) if environment is not None else None
        self._artifact_store = artifact_store
        self._calls_used = 0
        self._lock = threading.Lock()

    def build(self, package_name: str, files: Sequence[PackageFile]) -> BuildResult:
        build_id = uuid.uuid4().hex
        started = time.monotonic()
        with self._lock:
            if self._calls_used >= self.max_build_calls:
                return self._result(
                    build_id=build_id,
                    package_name=package_name,
                    snapshot_hash=None,
                    status="budget_exhausted",
                    duration_ms=round((time.monotonic() - started) * 1000),
                    stderr="The server-side build-call budget has been exhausted.",
                )
            self._calls_used += 1

        validation_errors = validate_package_snapshot(package_name, files)
        if validation_errors:
            return self._result(
                build_id=build_id,
                package_name=package_name,
                snapshot_hash=None,
                status="rejected",
                duration_ms=round((time.monotonic() - started) * 1000),
                validation_errors=validation_errors,
            )

        snapshot_hash = snapshot_sha256(package_name, files)

        if not self.allow_unsafe_local_builds:
            return self._result(
                build_id=build_id,
                package_name=package_name,
                snapshot_hash=snapshot_hash,
                status="unavailable",
                duration_ms=round((time.monotonic() - started) * 1000),
                stderr=(
                    "Local builds are disabled. Restart the server with "
                    "--allow-unsafe-local-build only in a trusted environment."
                ),
            )
        if not self.colcon_path.is_file() or not os.access(self.colcon_path, os.X_OK):
            return self._result(
                build_id=build_id,
                package_name=package_name,
                snapshot_hash=snapshot_hash,
                status="unavailable",
                duration_ms=round((time.monotonic() - started) * 1000),
                stderr=f"colcon executable not found: {self.colcon_path}",
            )

        self.workspace_root.mkdir(mode=0o700, parents=True, exist_ok=True)
        run_directory = self.workspace_root / build_id
        run_directory.mkdir(mode=0o700, exist_ok=False)
        package_directory = run_directory / "src" / package_name
        package_directory.mkdir(mode=0o755, parents=True)
        command = [
            str(self.colcon_path),
            "--log-base",
            "log",
            "build",
            "--base-paths",
            "src",
            "--build-base",
            "build",
            "--install-base",
            "install",
            "--packages-select",
            package_name,
            "--executor",
            "sequential",
            "--event-handlers",
            "console_direct+",
        ]

        try:
            self._materialize(package_directory, files)
            environment = self._environment or load_clean_ros_environment(self.ros_distro)
            environment = dict(environment)
            environment["COLCON_HOME"] = str(run_directory / ".colcon")
            environment["ROS_LOG_DIR"] = str(run_directory / "ros-logs")
            outcome = run_process(
                command,
                cwd=run_directory,
                environment=environment,
                timeout_seconds=self.timeout_seconds,
            )
            stdout, stdout_truncated = _truncate_text(
                outcome.stdout,
                self.max_output_bytes,
                keep_tail=True,
            )
            stderr, stderr_truncated = _truncate_text(
                outcome.stderr,
                self.max_output_bytes,
                keep_tail=True,
            )
            status = (
                "timed_out"
                if outcome.timed_out
                else "passed"
                if outcome.exit_code == 0
                else "failed"
            )
            result = BuildResult(
                build_id=build_id,
                package_name=package_name,
                snapshot_sha256=snapshot_hash,
                ros_distro=self.ros_distro,
                status=status,
                success=status == "passed",
                command=command,
                exit_code=outcome.exit_code,
                timed_out=outcome.timed_out,
                duration_ms=outcome.duration_ms,
                stdout=stdout,
                stderr=stderr,
                stdout_truncated=stdout_truncated,
                stderr_truncated=stderr_truncated,
                validation_errors=[],
                workspace_retained=self.keep_workspaces,
            )
        except (OSError, RuntimeError, ValueError) as exc:
            result = self._result(
                build_id=build_id,
                package_name=package_name,
                snapshot_hash=snapshot_hash,
                status="internal_error",
                duration_ms=round((time.monotonic() - started) * 1000),
                command=command,
                stderr=str(exc),
                workspace_retained=True,
            )

        if not self.keep_workspaces:
            try:
                if run_directory.parent == self.workspace_root and run_directory.name == build_id:
                    shutil.rmtree(run_directory)
                    result.workspace_retained = False
            except OSError as exc:
                result.workspace_retained = True
                result.stderr = f"{result.stderr}\nWorkspace cleanup failed: {exc}".strip()
        self._record_artifact(result, files)
        return result

    def _record_artifact(self, result: BuildResult, files: Sequence[PackageFile]) -> None:
        """Write an evaluator-visible immutable artifact after a real build attempt."""

        if self._artifact_store is None or result.status not in {"passed", "failed", "timed_out"}:
            return
        result.artifact_recorded = True
        try:
            self._artifact_store.record(
                run_id=result.build_id,
                package_name=result.package_name,
                files=list(files),
                build_result=result,
            )
        except (OSError, RuntimeError, ValueError) as exc:
            result.artifact_recorded = False
            result.status = "internal_error"
            result.success = False
            result.stderr = f"{result.stderr}\nArtifact recording failed: {exc}".strip()

    @staticmethod
    def _materialize(package_directory: Path, files: Sequence[PackageFile]) -> None:
        for package_file in sorted(files, key=lambda item: item.path):
            relative = PurePosixPath(package_file.path)
            destination = package_directory.joinpath(*relative.parts)
            destination.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
            destination.write_text(package_file.content, encoding="utf-8")
            destination.chmod(0o755 if package_file.executable else 0o644)

    def _result(
        self,
        *,
        build_id: str,
        package_name: str,
        snapshot_hash: str | None,
        status: str,
        duration_ms: int,
        command: Sequence[str] = (),
        stderr: str = "",
        validation_errors: Sequence[str] = (),
        workspace_retained: bool = False,
    ) -> BuildResult:
        return BuildResult(
            build_id=build_id,
            package_name=package_name,
            snapshot_sha256=snapshot_hash,
            ros_distro=self.ros_distro,
            status=status,
            success=False,
            command=list(command),
            exit_code=None,
            timed_out=False,
            duration_ms=duration_ms,
            stdout="",
            stderr=stderr,
            stdout_truncated=False,
            stderr_truncated=False,
            validation_errors=list(validation_errors),
            workspace_retained=workspace_retained,
        )
