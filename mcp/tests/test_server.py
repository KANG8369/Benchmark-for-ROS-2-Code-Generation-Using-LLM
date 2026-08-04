from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from mcp import Client
from mcp.client.stdio import StdioServerParameters, stdio_client

from benchmark_mcp.artifacts import ArtifactStore
from benchmark_mcp.schemas import BuildResult, InterfaceShowResult, PackageFile
from benchmark_mcp.server import create_server
from benchmark_mcp.services import BuildService, InterfaceService

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def test_coder_server_exposes_only_public_resources_and_two_tools(
    tmp_path: Path,
) -> None:
    server = create_server(
        REPOSITORY_ROOT,
        interface_service=InterfaceService(ros2_path=tmp_path / "missing", environment={}),
        build_service=BuildService(workspace_root=tmp_path, max_build_calls=0),
    )

    async def inspect_surface() -> None:
        async with Client(server) as client:
            tools = await client.list_tools()
            resources = await client.list_resources()
            templates = await client.list_resource_templates()

            assert [tool.name for tool in tools.tools] == [
                "ros2_interface_show",
                "build_ros_package",
            ]
            assert [str(resource.uri) for resource in resources.resources] == ["benchmark://cases"]
            template_uris = [template.uri_template for template in templates.resource_templates]
            assert template_uris == [
                "benchmark://cases/{case_id}/description",
                "benchmark://cases/{case_id}/description/{section}",
            ]
            assert all("internal" not in uri for uri in template_uris)
            assert all("metric" not in uri for uri in template_uris)
            assert all("reference" not in uri for uri in template_uris)

    asyncio.run(inspect_surface())


def test_evaluator_server_exposes_metric_and_artifact_reads_without_build(
    tmp_path: Path,
) -> None:
    server = create_server(
        REPOSITORY_ROOT,
        profile="evaluator",
        interface_service=InterfaceService(ros2_path=tmp_path / "missing", environment={}),
        artifact_store=ArtifactStore(tmp_path / "artifacts"),
    )

    async def inspect_surface() -> None:
        async with Client(server) as client:
            tools = await client.list_tools()
            resources = await client.list_resources()
            templates = await client.list_resource_templates()

            assert [tool.name for tool in tools.tools] == ["ros2_interface_show"]
            assert [str(resource.uri) for resource in resources.resources] == ["benchmark://cases"]
            template_uris = [template.uri_template for template in templates.resource_templates]
            assert template_uris == [
                "benchmark://cases/{case_id}/description",
                "benchmark://cases/{case_id}/description/{section}",
                "benchmark-internal://cases/{case_id}/metric",
                "benchmark-run://runs/{run_id}/package",
                "benchmark-run://runs/{run_id}/package/files/{file_id}",
            ]
            assert "build_ros_package" not in [tool.name for tool in tools.tools]

    asyncio.run(inspect_surface())


def test_evaluator_reads_hidden_metric_and_immutable_artifact(tmp_path: Path) -> None:
    artifact_store = ArtifactStore(tmp_path / "artifacts")
    run_id = "a" * 32
    artifact_store.record(
        run_id=run_id,
        package_name="demo_package",
        files=[PackageFile(path="package.xml", content="<package/>")],
        build_result=BuildResult(
            build_id=run_id,
            package_name="demo_package",
            snapshot_sha256="b" * 64,
            ros_distro="jazzy",
            status="passed",
            success=True,
            command=["colcon", "build"],
            exit_code=0,
            timed_out=False,
            duration_ms=10,
            stdout="",
            stderr="",
            stdout_truncated=False,
            stderr_truncated=False,
            validation_errors=[],
            workspace_retained=False,
            artifact_recorded=True,
        ),
    )
    server = create_server(
        REPOSITORY_ROOT,
        profile="evaluator",
        interface_service=InterfaceService(ros2_path=tmp_path / "missing", environment={}),
        artifact_store=artifact_store,
    )

    async def read_private_resources() -> None:
        async with Client(server) as client:
            metric_result = await client.read_resource(
                "benchmark-internal://cases/dummy_sensors/metric"
            )
            artifact_result = await client.read_resource(f"benchmark-run://runs/{run_id}/package")

            metric = json.loads(metric_result.contents[0].text)
            artifact = json.loads(artifact_result.contents[0].text)
            file_id = artifact["files"][0]["file_id"]
            file_result = await client.read_resource(
                f"benchmark-run://runs/{run_id}/package/files/{file_id}"
            )
            package_file = json.loads(file_result.contents[0].text)

            assert metric["case_id"] == "dummy_sensors"
            assert metric["metric_sha256"]
            assert artifact["run_id"] == run_id
            assert artifact["build"]["status"] == "passed"
            assert package_file["content"] == "<package/>"

    asyncio.run(read_private_resources())


def test_resources_are_readable_through_an_in_memory_mcp_client(tmp_path: Path) -> None:
    server = create_server(
        REPOSITORY_ROOT,
        interface_service=InterfaceService(ros2_path=tmp_path / "missing", environment={}),
        build_service=BuildService(workspace_root=tmp_path, max_build_calls=0),
    )

    async def read_resources() -> None:
        async with Client(server) as client:
            catalog_result = await client.read_resource("benchmark://cases")
            complete_result = await client.read_resource(
                "benchmark://cases/dummy_sensors/description"
            )
            section_result = await client.read_resource(
                "benchmark://cases/dummy_sensors/description/interfaces"
            )

            catalog = json.loads(catalog_result.contents[0].text)
            complete = json.loads(complete_result.contents[0].text)
            section = json.loads(section_result.contents[0].text)

            assert catalog["case_count"] == 9
            assert complete["description"]["intent"]["package_name"] == "dummy_sensors"
            assert complete["description_sha256"] == section["description_sha256"]
            assert section["section"] == "interfaces"

    asyncio.run(read_resources())


def test_tool_returns_structured_content_through_mcp_client(tmp_path: Path) -> None:
    class StubInterfaceService:
        def show(self, interface_type: str) -> InterfaceShowResult:
            return InterfaceShowResult(
                interface_type=interface_type,
                ros_distro="jazzy",
                found=True,
                definition="string data\n",
                definition_sha256="0" * 64,
                exit_code=0,
                stderr="",
                duration_ms=1,
                output_truncated=False,
            )

    server = create_server(
        REPOSITORY_ROOT,
        interface_service=StubInterfaceService(),
        build_service=BuildService(workspace_root=tmp_path, max_build_calls=0),
    )

    async def call_tool() -> None:
        async with Client(server) as client:
            result = await client.call_tool(
                "ros2_interface_show",
                {"interface_type": "std_msgs/msg/String"},
            )

            assert result.is_error is False
            assert result.structured_content == {
                "interface_type": "std_msgs/msg/String",
                "ros_distro": "jazzy",
                "found": True,
                "definition": "string data\n",
                "definition_sha256": "0" * 64,
                "exit_code": 0,
                "stderr": "",
                "duration_ms": 1,
                "output_truncated": False,
                "error_kind": None,
            }

    asyncio.run(call_tool())


def test_console_server_uses_a_clean_stdio_transport() -> None:
    parameters = StdioServerParameters(
        command=sys.executable,
        args=[
            "-m",
            "benchmark_mcp",
            "--repo-root",
            str(REPOSITORY_ROOT),
            "--max-build-calls",
            "0",
        ],
    )

    async def inspect_subprocess() -> None:
        async with Client(stdio_client(parameters)) as client:
            tools = await client.list_tools()
            resources = await client.list_resources()

            assert [tool.name for tool in tools.tools] == [
                "ros2_interface_show",
                "build_ros_package",
            ]
            assert [str(resource.uri) for resource in resources.resources] == ["benchmark://cases"]

    asyncio.run(inspect_subprocess())
