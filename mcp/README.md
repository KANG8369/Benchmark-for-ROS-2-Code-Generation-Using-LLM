# Benchmark MCP Design

This directory will contain an MCP server for running the ROS 2 code-generation
benchmark with reproducible, role-scoped access to benchmark artifacts and ROS
tools. This document is a design proposal; no executable server is included yet.

## Goals

- Expose long generator-facing descriptions as addressable MCP resources.
- Give every evaluated model the same tool schemas, limits, and ROS environment.
- Keep generated packages isolated in a run-scoped workspace.
- Separate code generation, static evaluation, and simulation permissions.
- Prevent the coder from reading hidden metrics, reference implementations, or
  evaluator feedback before it is explicitly returned by the orchestrator.

## Proposed Components

```text
mcp/
├── server.py                       # MCP server entry point and capability setup
├── schemas.py                      # Shared request and response models
├── resources/
│   ├── benchmark_catalog.py        # Available case metadata
│   └── description.py              # Full or section-level public descriptions
├── tools/
│   ├── ros2_interface_show.py      # Installed ROS interface definitions
│   └── build_ros_package.py        # Isolated colcon build and structured log
├── policies/
│   └── agent_permissions.yaml      # Per-agent resource and tool allowlists
└── tests/
    ├── test_resource_visibility.py
    ├── test_workspace_isolation.py
    └── test_tool_contracts.py
```

Simulation support should be added after the generation and static-evaluation
path is stable. It is expected to add task-specific harness resources plus a
restricted `run_simulation` tool; simulation assets must remain invisible to
the coder when they disclose hidden evaluation details.

## Resources

Resources are read-only benchmark inputs. Proposed URIs are:

| URI | Consumer | Contents |
| --- | --- | --- |
| `benchmark://cases` | Orchestrator | Public case catalog and description metadata |
| `benchmark://cases/{case}/description` | Coder, evaluators | Complete `description.yaml` |
| `benchmark://cases/{case}/description/{section}` | Coder, evaluators | One long-description section such as `functional_requirements` or `interfaces` |
| `benchmark-internal://cases/{case}/metric` | Evaluators only | Hidden `metric.yaml` |
| `benchmark-internal://cases/{case}/reference/{path}` | Benchmark maintainers only | Reference-package evidence |

Section resources reduce context pressure without changing the generator input:
the complete description remains the authoritative specification, and all
sections presented to a model must come from the same immutable snapshot.

## Initial Tools

### `ros2_interface_show`

Returns the installed definition of one canonical ROS interface, for example
`sensor_msgs/msg/LaserScan`. It is read-only and must report the ROS distribution
and command result so runs remain auditable.

### `build_ros_package`

Builds the submitted package in its run-scoped ROS 2 workspace and returns a
structured result containing the exit code, stdout, stderr, duration, and build
artifacts. The tool must not automatically edit code or retry the build.

Package file reading and writing belong to the run workspace API supplied by
the agent host. They do not need to be duplicated as benchmark-specific MCP
tools unless a client has no secure filesystem abstraction.

## Agent Contracts

| Agent | Inputs | Allowed MCP capabilities | Output |
| --- | --- | --- | --- |
| Coder | Immutable description snapshot; optional prior package and explicit evaluator feedback | Public description resources, `ros2_interface_show`, `build_ros_package` | One complete ROS 2 package: package name and every file path with its full contents |
| Functional-requirement evaluator | Description, hidden metric, and generated package | Public description and hidden metric resources; read-only package inspection | Structured result for every requirement and pass criterion, with evidence and actionable feedback |
| Simulation-harness author | Description, hidden metric, generated package, and simulation contract | Evaluator-only artifacts and a restricted harness workspace | Task-specific launch, fixtures, assertions, and environment configuration |
| Simulation runner | Frozen generated package and approved harness | `build_ros_package` and future `run_simulation` | Structured execution result, logs, artifacts, and observed pass/fail evidence |

The orchestrator, not an agent, advances artifacts between these stages:

```text
Coder -> build result -> functional evaluator -> explicit feedback -> Coder
      -> all static checks pass -> simulation harness -> simulation runner
```

## Reproducibility and Safety Rules

1. The coder can read `description.yaml` but never `metric.yaml`, `reference/`,
   hidden thresholds, or simulation assertions.
2. Tool names, JSON schemas, timeouts, output limits, container image, ROS 2
   distribution, and retry budget are fixed for all compared models.
3. Every run receives a new workspace identified by an opaque run ID; paths
   outside that workspace are inaccessible to execution tools.
4. Build and simulation tools return observations only. They never repair the
   generated package or trigger an implicit regeneration loop.
5. Tool calls, resource versions, model output, feedback, and environment
   metadata are recorded in a machine-readable run manifest.
6. Hidden evaluator data is exposed through a separate authorization scope,
   not merely omitted from the prompt.

## Implementation Order

1. Define resource/tool schemas and the per-agent authorization policy.
2. Implement description resources with snapshot hashes and visibility tests.
3. Implement `ros2_interface_show` with an allowlisted command contract.
4. Implement isolated one-shot builds and structured build results.
5. Connect the functional-requirement evaluator and feedback protocol.
6. Add task-specific simulation harnesses and a restricted simulation runner.
7. Pin the environment and publish an end-to-end reproducibility test.
