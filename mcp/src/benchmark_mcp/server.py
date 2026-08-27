"""MCP server entry point for public benchmark resources and Coder tools."""

from __future__ import annotations

import argparse
import logging
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Literal

from mcp.server import MCPServer

from benchmark_mcp.artifacts import ArtifactStore
from benchmark_mcp.registry import BenchmarkRegistry, resolve_repository_root
from benchmark_mcp.schemas import BuildResult, InterfaceShowResult, PackageFile
from benchmark_mcp.services import BuildService, InterfaceService

SERVER_VERSION = "0.3.0"
Profile = Literal["coder", "evaluator"]


def _default_runtime_root() -> Path:
    return Path(tempfile.gettempdir()) / "ros2-codegen-benchmark-mcp"


def create_server(
    repository_root: str | Path | None = None,
    *,
    profile: Profile = "coder",
    interface_service: InterfaceService | None = None,
    build_service: BuildService | None = None,
    artifact_store: ArtifactStore | None = None,
) -> MCPServer:
    """Create one fixed-role MCP server from one immutable benchmark snapshot."""

    if profile not in {"coder", "evaluator"}:
        raise ValueError(f"Unknown server profile: {profile}")
    resolved_root = resolve_repository_root(repository_root)
    registry = BenchmarkRegistry(resolved_root, include_metrics=profile == "evaluator")
    interface_service = interface_service or InterfaceService()
    artifact_store = artifact_store or ArtifactStore(_default_runtime_root() / "artifacts")
    if profile == "coder":
        build_service = build_service or BuildService(
            workspace_root=_default_runtime_root() / "workspaces",
            artifact_store=artifact_store,
        )

    server = MCPServer(
        "ROS 2 Code Generation Benchmark",
        version=SERVER_VERSION,
        instructions=(
            "Coder profile: read a complete public description before generating a "
            "package; use ros2_interface_show only for existing ROS interfaces needed "
            "by a public functional requirement; submit one complete package snapshot "
            "to build_ros_package."
            if profile == "coder"
            else "Evaluator profile: read the public description, hidden FR/PC metric, "
            "and one immutable generated-package artifact, then return PC-level "
            "FunctionalEvaluationFeedback to the orchestrator outside MCP. Do not build, "
            "generate, or modify packages."
        ),
    )

    @server.resource(
        "benchmark://cases",
        name="benchmark_cases",
        title="Public benchmark case catalog",
        description="Lists generator-visible benchmark cases from one server-start snapshot.",
        mime_type="application/json",
    )
    def benchmark_cases() -> dict:
        return registry.catalog_resource()

    @server.resource(
        "benchmark://cases/{case_id}/description",
        name="benchmark_description",
        title="Complete public benchmark description",
        description="Returns the complete generator-visible description for one case.",
        mime_type="application/json",
    )
    def benchmark_description(case_id: str) -> dict:
        return registry.description_resource(case_id)

    @server.resource(
        "benchmark://cases/{case_id}/description/{section}",
        name="benchmark_description_section",
        title="Public benchmark description section",
        description=(
            "Returns intent, functional_requirements, or optional target_environment "
            "from the same immutable description snapshot."
        ),
        mime_type="application/json",
    )
    def benchmark_description_section(case_id: str, section: str) -> dict:
        return registry.section_resource(case_id, section)

    if profile == "evaluator":

        @server.resource(
            "benchmark-internal://cases/{case_id}/metric",
            name="benchmark_metric",
            title="Hidden functional-evaluation metric",
            description="Returns one evaluator-only metric snapshot for a benchmark case.",
            mime_type="application/json",
        )
        def benchmark_metric(case_id: str) -> dict:
            return registry.metric_resource(case_id)

        @server.resource(
            "benchmark-run://runs/{run_id}/package",
            name="generated_package_artifact",
            title="Immutable generated ROS package artifact",
            description=(
                "Returns a generated package manifest and build observation by opaque run ID."
            ),
            mime_type="application/json",
        )
        def generated_package_artifact(run_id: str) -> dict:
            return artifact_store.package_resource(run_id)

        @server.resource(
            "benchmark-run://runs/{run_id}/package/files/{file_id}",
            name="generated_package_file",
            title="Immutable generated ROS package file",
            description="Returns one file body from an immutable generated package artifact.",
            mime_type="application/json",
        )
        def generated_package_file(run_id: str, file_id: str) -> dict:
            return artifact_store.file_resource(run_id, file_id)

    @server.tool(
        name="ros2_interface_show",
        title="Show an installed ROS 2 interface",
        structured_output=True,
    )
    def ros2_interface_show(interface_type: str) -> InterfaceShowResult:
        """Return the exact installed definition of one canonical msg, srv, or action type.

        Call once per distinct existing interface type that generated code directly uses.
        This tool does not discover unspecified types and does not install packages.
        """

        return interface_service.show(interface_type)

    if profile == "coder":
        assert build_service is not None

        @server.tool(
            name="build_ros_package",
            title="Build one complete ROS 2 package snapshot",
            structured_output=True,
        )
        def build_ros_package(package_name: str, files: list[PackageFile]) -> BuildResult:
            """Materialize and build one complete package snapshot in a fresh workspace.

            The tool returns observations only. It never changes the submitted snapshot,
            never triggers an automatic repair or retry, and records a valid immutable
            artifact for the evaluator after a real build attempt.
            """

            return build_service.build(package_name, files)

    return server


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root",
        help="Benchmark repository root (or set ROS2_BENCHMARK_ROOT).",
    )
    parser.add_argument(
        "--workspace-root",
        default=str(_default_runtime_root() / "workspaces"),
        help="Dedicated parent directory for ephemeral build workspaces.",
    )
    parser.add_argument(
        "--artifact-root",
        default=str(_default_runtime_root() / "artifacts"),
        help="Private shared directory for immutable evaluator-visible build artifacts.",
    )
    parser.add_argument(
        "--profile",
        choices=("coder", "evaluator"),
        default="coder",
        help="Fixed server role; the model cannot change it at runtime.",
    )
    parser.add_argument(
        "--max-build-calls",
        type=int,
        default=1,
        help="Server-side build-call budget. Keep identical across compared models.",
    )
    parser.add_argument(
        "--build-timeout-seconds",
        type=int,
        default=300,
        help="Fixed timeout for each package build.",
    )
    parser.add_argument(
        "--allow-unsafe-local-build",
        action="store_true",
        help=(
            "Enable host colcon builds. Generated CMake/setup.py code is arbitrary code; "
            "use only in a trusted machine or replace with an OCI sandbox."
        ),
    )
    parser.add_argument(
        "--keep-workspaces",
        action="store_true",
        help="Keep build directories for debugging instead of deleting them.",
    )
    parser.add_argument(
        "--transport",
        choices=("stdio", "sse", "streamable-http"),
        default="stdio",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    parser = build_argument_parser()
    args = parser.parse_args(argv)
    if args.max_build_calls < 0:
        parser.error("--max-build-calls must be non-negative")
    if args.build_timeout_seconds <= 0:
        parser.error("--build-timeout-seconds must be positive")

    logging.basicConfig(level=logging.INFO)
    try:
        repository_root = resolve_repository_root(args.repo_root)
        artifact_store = ArtifactStore(args.artifact_root)
        build_service = None
        if args.profile == "coder":
            build_service = BuildService(
                workspace_root=args.workspace_root,
                timeout_seconds=args.build_timeout_seconds,
                max_build_calls=args.max_build_calls,
                allow_unsafe_local_builds=args.allow_unsafe_local_build,
                keep_workspaces=args.keep_workspaces,
                artifact_store=artifact_store,
            )
        server = create_server(
            repository_root,
            profile=args.profile,
            build_service=build_service,
            artifact_store=artifact_store,
        )
    except (OSError, RuntimeError, ValueError) as exc:
        parser.error(str(exc))

    if args.transport == "stdio":
        server.run("stdio")
    else:
        server.run(args.transport, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
