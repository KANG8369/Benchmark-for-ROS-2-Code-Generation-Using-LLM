# ROS 2 Benchmark MCP Server

This directory contains the runnable, Coder-facing MCP server for the ROS 2
code-generation benchmark. It exposes immutable public descriptions and two
auditable ROS 2 tools while keeping `metric.yaml` and `reference/` unavailable
to the generator.

## Implemented Scope

The initial server intentionally exposes only the capabilities required by the
Coder Agent:

| Kind | MCP capability | Purpose |
| --- | --- | --- |
| Resource | `benchmark://cases` | Sorted public case catalog and snapshot hashes |
| Resource template | `benchmark://cases/{case_id}/description` | Complete public `description.yaml` snapshot |
| Resource template | `benchmark://cases/{case_id}/description/{section}` | `intent`, `functional_requirements`, or `interfaces` from that same snapshot |
| Tool | `ros2_interface_show` | Exact installed definition of one declared ROS msg/srv/action type |
| Tool | `build_ros_package` | One complete package snapshot built in a fresh workspace |

The server never registers internal metric or reference resources. A future
functional-evaluator server must be a separate process/profile rather than a
model-selectable role on this public server.

## Requirements

- Python 3.10 or newer
- ROS 2 Jazzy installed at `/opt/ros/jazzy`
- `colcon` at `/usr/bin/colcon` for local build-tool use

The runtime dependencies pin MCP Python SDK `2.0.0` and PyYAML `6.0.3` so the
model-visible schemas and description parsing stay fixed across benchmark runs.

## Install

From the repository checkout:

```bash
cd mcp
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[test]'
```

Run the tests:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest
ruff check src tests
ruff format --check src tests
```

Disabling third-party pytest plugin autoload keeps ROS installation plugins from
changing this unit-test environment.

## Run over stdio

From `mcp/` with the virtual environment active:

```bash
ros2-benchmark-mcp --repo-root ..
```

This safe default serves descriptions and `ros2_interface_show`, but
`build_ros_package` returns `status: unavailable`. To opt into host builds:

```bash
ros2-benchmark-mcp \
  --repo-root .. \
  --workspace-root /tmp/ros2-codegen-benchmark-mcp \
  --max-build-calls 1 \
  --build-timeout-seconds 300 \
  --allow-unsafe-local-build
```

An MCP host can launch the server with an equivalent stdio configuration:

```json
{
  "command": "/absolute/path/to/repository/mcp/.venv/bin/ros2-benchmark-mcp",
  "args": [
    "--repo-root",
    "/absolute/path/to/repository",
    "--workspace-root",
    "/tmp/ros2-codegen-benchmark-mcp",
    "--max-build-calls",
    "1",
    "--allow-unsafe-local-build"
  ]
}
```

Repository discovery can alternatively use the `ROS2_BENCHMARK_ROOT`
environment variable. Server logs go to stderr so they do not corrupt the MCP
stdio transport.

Streamable HTTP is available for local integration testing:

```bash
ros2-benchmark-mcp --repo-root .. --transport streamable-http --port 8000
```

The default bind address is `127.0.0.1`.

## Resource Responses

The case registry is loaded once at server startup. Case identifiers come only
from validated direct children of `benchmarks/`; request parameters are never
joined into arbitrary filesystem paths.

The complete and section-level description resources return JSON envelopes:

```json
{
  "case_id": "dummy_sensors",
  "description_sha256": "...",
  "description": {
    "intent": {},
    "functional_requirements": [],
    "interfaces": {}
  }
}
```

Every section read contains the same `description_sha256`, allowing an
orchestrator to reject mixed snapshots. The optional `interfaces` section is
represented with `present: false` when omitted.

## Tool Contracts

### `ros2_interface_show`

Input:

```json
{
  "interface_type": "sensor_msgs/msg/LaserScan"
}
```

The canonical name is validated before a fixed argv command is executed. The
result includes the ROS distribution, exact definition, definition SHA-256,
exit code, stderr, duration, truncation state, and a structured error kind.
Results are cached once per server run.

Use the tool only when generated code directly reads, constructs, or writes an
existing interface. Do not use it to discover an interface absent from the
public description. Custom interfaces belong in the generated package and are
validated by the build.

### `build_ros_package`

Input:

```json
{
  "package_name": "example_package",
  "files": [
    {
      "path": "package.xml",
      "content": "<package format=\"3\">...</package>",
      "executable": false
    }
  ]
}
```

Only the complete snapshot is model-controlled. Timeout, workspace root,
build-call budget, ROS distribution, command arguments, and environment are
fixed by the server operator.

Before writing anything, the tool rejects:

- invalid package names
- absolute, non-normalized, backslash, or traversal paths
- duplicate paths and reserved top-level `.git`, `build`, `install`, or `log`
- excessive file counts or content sizes
- missing/malformed `package.xml`
- a manifest package name that differs from `package_name`

Each accepted call receives a generated build ID and a fresh
`<workspace-root>/<build-id>/src/<package-name>` directory. `colcon` runs with a
clean environment sourced only from `/opt/ros/jazzy`; current user overlays and
ambient environment secrets are not inherited. The result reports the package
snapshot hash, status, command, exit code, timeout, duration, bounded logs, and
validation errors. The tool never edits the submitted package and never
retries automatically.

## Local-Build Security Boundary

Directory isolation is not an operating-system sandbox. CMake and `setup.py`
can execute arbitrary commands during a build. The local backend is therefore
disabled unless the operator supplies `--allow-unsafe-local-build`.

Use local builds only for trusted development. Reproducible benchmark runs
should execute the same tool contract inside a pinned OCI environment with no
network, a non-root user, read-only root filesystem, only the ephemeral
workspace writable, and fixed CPU, memory, PID, output, and time limits. Do not
give the model a backend-selection option.

## Agent Boundary

The intended runtime flow is:

```text
Coder -> build result -> functional evaluator -> explicit feedback -> Coder
      -> all static checks pass -> simulation runner
```

- The current public server is for the Coder only.
- The functional evaluator will receive hidden metrics through a separate
  evaluator-scoped server and read generated package artifacts without write or
  build permissions.
- Simulation harnesses should be authored and validated offline against the
  benchmark contract/reference, then frozen before model evaluation. They must
  not adapt to an individual candidate package.
- A future Simulation Runner will receive only frozen artifacts and a restricted
  `run_simulation` tool; it will not generate or modify code.

The orchestrator fixes tool schemas, timeouts, output limits, environment,
retry budgets, and artifact transitions identically for every compared model.

## Repository Layout

```text
mcp/
├── pyproject.toml
├── src/benchmark_mcp/
│   ├── registry.py          # Immutable public case snapshots
│   ├── schemas.py           # Structured tool inputs and outputs
│   ├── services.py          # Validated ROS commands and package builds
│   └── server.py            # MCP resources, tools, and CLI
└── tests/
    ├── test_registry.py
    ├── test_server.py
    └── test_services.py
```

## Implementation Roadmap

1. Current: public description resources and the two Coder tools.
2. Add an evaluator-only server and immutable generated-package resources.
3. Connect structured functional-requirement feedback to the orchestrator.
4. Move builds into a pinned OCI runner without changing the model-visible
   schema.
5. Add frozen task-specific harnesses and the restricted `run_simulation` tool.
6. Publish an end-to-end reproducibility test and run manifest schema.
