# ROS 2 Benchmark MCP Server

This directory contains the runnable MCP servers for the ROS 2 code-generation
benchmark. A server has one fixed role at launch: the Coder can read public
descriptions and build one complete package snapshot; the Evaluator can read a
hidden metric and immutable generated-package artifacts. `metric.yaml` and
`reference/` are never visible to the Coder.

## Implemented Scope

The server role is chosen by its operator with `--profile`; it is not selected
by the model, a prompt, or an MCP tool call.

| Kind | Coder profile | Evaluator profile |
| --- | --- | --- |
| Public resources | `benchmark://cases`, `benchmark://cases/{case_id}/description`, `benchmark://cases/{case_id}/description/{section}` | Same read-only public resources |
| Hidden metric | Not registered | `benchmark-internal://cases/{case_id}/metric` |
| Generated artifact | Not registered | `benchmark-run://runs/{run_id}/package` and `.../files/{file_id}` |
| `ros2_interface_show` | Registered | Registered for evidence checks when needed |
| `build_ros_package` | Registered | Not registered |

The Evaluator receives the `run_id` from the orchestrator after a real Coder
build. The Coder learns the build ID in its result but cannot read the artifact
or metric through its server surface.

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
  --profile coder \
  --workspace-root /tmp/ros2-codegen-benchmark-mcp/workspaces \
  --artifact-root /tmp/ros2-codegen-benchmark-mcp/artifacts \
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
    "--profile",
    "coder",
    "--workspace-root",
    "/tmp/ros2-codegen-benchmark-mcp/workspaces",
    "--artifact-root",
    "/tmp/ros2-codegen-benchmark-mcp/artifacts",
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

## Run the Evaluator Profile

Start this as a separate MCP process, using the exact same private
`--artifact-root` used by the Coder process:

```bash
ros2-benchmark-mcp \
  --repo-root .. \
  --profile evaluator \
  --artifact-root /tmp/ros2-codegen-benchmark-mcp/artifacts
```

The evaluator process has no package-writing or build tool. It reads the
hidden metric, manifest, and file bodies, then emits the following structured
object to the **orchestrator** (this is an output contract, not a Coder-visible
MCP resource):

```json
{
  "case_id": "dummy_sensors",
  "description_sha256": "...",
  "package_artifact_id": "the build_id returned by build_ros_package",
  "requirements": [
    {
      "requirement_id": "FR-01",
      "status": "pass",
      "evidence": ["src/example.cpp:42"],
      "feedback": null
    }
  ]
}
```

The orchestrator verifies that the description hash and package artifact ID
belong to the current run before it forwards only permitted feedback to the
Coder. It must not give the Evaluator's server connection to the Coder.

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
retries automatically. A completed local build attempt (`passed`, `failed`, or
`timed_out`) is stored atomically under the private artifact root. Its manifest
contains the snapshot hash, package file IDs, and build result; an evaluator
can read file bodies only through its own profile.

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

- The Coder server exposes two tools: interface inspection and package build.
- The Evaluator server has read-only hidden metrics and immutable package
  artifacts, plus optional interface inspection, but no write or build tool.
- `FunctionalEvaluationFeedback` is the fixed evaluator-to-orchestrator output
  contract; retry policy remains external (`--max-build-calls`), rather than a
  hard-coded Coder repair loop.
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
│   ├── artifacts.py         # Atomic evaluator-visible package artifacts
│   ├── schemas.py           # Structured tool inputs and outputs
│   ├── services.py          # Validated ROS commands and package builds
│   ├── snapshot.py          # Canonical package snapshot identity
│   └── server.py            # MCP resources, tools, and CLI
└── tests/
    ├── test_registry.py
    ├── test_server.py
    └── test_services.py
```

## Implementation Roadmap

1. Current: fixed Coder/Evaluator profiles, immutable artifacts, and structured
   evaluator feedback contract.
2. Connect the evaluator implementation and orchestrator to that feedback
   contract.
3. Move builds into a pinned OCI runner without changing the model-visible
   schema.
4. Add frozen task-specific harnesses and the restricted `run_simulation` tool.
5. Publish an end-to-end reproducibility test and run manifest schema.
