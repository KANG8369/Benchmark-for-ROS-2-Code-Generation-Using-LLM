# Description Format Specification

This document defines the benchmark-facing `description.yaml` format. The
description is the only benchmark artifact given to the ROS 2 package
generator. It must therefore preserve the reference package's observable
behavior and verified interoperability contract without exposing source code or
requiring incidental implementation details.

The copyable format is available in
[`templates/description.yaml`](../templates/description.yaml).

## Top-Level Structure

```yaml
intent:
  package_name: <string>
  summary: <string>
  scope: <string>

functional_requirements:
  - id: FR-1
    text: <string>

interfaces:
  nodes: [...]
  launch_arguments: [...]
  external_nodes: [...]
  environment_variables: [...]
```

| Field | Required | Meaning |
| --- | --- | --- |
| `intent` | Yes | Package identity, purpose, and responsibility boundary. |
| `functional_requirements` | Yes | Non-empty list of observable package behaviors. |
| `interfaces` | No | Verified ROS 2 runtime and configuration contract. |

`interfaces` may be omitted for a package that has observable utility behavior
but no applicable ROS graph, launch, external-node, or environment-variable
contract.

## Intent

### `intent.package_name`

- **Required**
- Must match the `<name>` value in the reference package's `package.xml`.
- Must use a valid ROS 2 package-style name: lowercase letters, digits, and
  underscores, beginning with a lowercase letter.

### `intent.summary`

- **Required**
- Concisely states the package's primary purpose and externally meaningful
  outcome.
- Describes the package rather than its implementation files.

### `intent.scope`

- **Optional**
- States what the package implements and what must be provided by external
  packages, hardware, simulators, or users.
- Use it when the package boundary would otherwise be ambiguous.

## Functional Requirements

`functional_requirements` is a non-empty ordered list.

| Field | Required | Meaning |
| --- | --- | --- |
| `id` | Yes | Sequential identifier beginning with `FR-1`. |
| `text` | Yes | One observable and independently verifiable outcome. |

Requirements must follow these rules:

1. Use sequential IDs: `FR-1`, `FR-2`, `FR-3`, and so on.
2. Write one sentence describing one observable result.
3. Cover every distinct, functionally relevant behavior supported by reachable
   reference-package evidence.
4. Include meaningful failure handling, lifecycle behavior, dynamic
   multiplicity, data processing, and launch orchestration when applicable.
5. Generalize incidental details such as an internal algorithm or exact timer
   period unless that detail is part of the public contract.
6. Do not create one requirement for every source function, parameter, or
   tuning constant.

For packages exporting a reusable library, requirements must cover each
distinct public facility with observable behavior, not only installed example
executables.

## Interfaces

`interfaces` is optional. When present, it may contain the following non-empty
categories:

| Category | Meaning |
| --- | --- |
| `nodes` | Runtime nodes implemented by the target package. |
| `launch_arguments` | Public settings accepted by reachable launch files. |
| `external_nodes` | Nodes from other packages explicitly launched or loaded by the target package. |
| `environment_variables` | Environment variables directly used by reachable package code or launch logic. |

Omit a category when it does not apply. Empty lists are not valid.

## Package-Implemented Nodes

Each `interfaces.nodes` entry has the following structure:

```yaml
- name: <runtime node name or verified dynamic pattern>
  responsibility: <node responsibility>
  topics: [...]
  services: [...]
  actions: [...]
  tf: [...]
  parameters: [...]
```

`name` and `responsibility` are required. The five resource categories are
optional and must be omitted when empty.

Only nodes implemented by the target package belong in `nodes`. A node from
another package belongs in `external_nodes` when the target package explicitly
launches or loads it.

When launch code overrides an implemented node's name, record the effective
runtime name. A dynamic name may use an evidence-backed pattern such as
`/robot_<index>/controller`.

### Topics

```yaml
- name: /example_topic
  type: example_msgs/msg/Example
  direction: publish
  purpose: Carries example data to downstream consumers.
```

| Field | Allowed value |
| --- | --- |
| `name` | Effective topic name or verified dynamic pattern. |
| `type` | Canonical `package/msg/Type` syntax. |
| `direction` | `publish` or `subscribe`, from the containing node's perspective. |
| `purpose` | Why the node uses the endpoint. |

### Services

```yaml
- name: /reset
  type: std_srvs/srv/Trigger
  role: server
  purpose: Resets package state.
```

`role` must be `server` or `client`, from the containing node's perspective.
Service types must use canonical `package/srv/Type` syntax.

### Actions

```yaml
- name: /follow_path
  type: nav2_msgs/action/FollowPath
  role: client
  purpose: Sends a generated path to a controller.
```

`role` must be `server` or `client`. Action types must use canonical
`package/action/Type` syntax.

### TF Relationships

```yaml
- source_frame: leader/base_link
  target_frame: follower/base_link
  purpose: Looks up the leader pose in the follower frame.
```

- For a broadcast, `source_frame` is the parent and `target_frame` is the child.
- For `lookupTransform(target, source)`, `source_frame` is the source argument
  and `target_frame` is the target argument.
- A frame is a TF resource, not a node or topic.

### Parameters

```yaml
- name: update_rate
  type: double
  purpose: Configures the output update frequency.
```

- Include every verified user-configurable parameter declared or read by the
  node.
- Use the actual finite parameter key whenever it is known.
- A pattern such as `topics.<source>.priority` is allowed only when code accepts
  an arbitrary key at that exact segment.
- Environment variables are not ROS parameters.

## Launch Arguments

```yaml
- name: use_sim_time
  purpose: Selects simulated ROS time for launched nodes.
```

Include every public launch argument and every externally settable launch
configuration used by reachable launch control flow. Internal local variables
are not launch arguments.

## External Nodes

An external node is implemented by another ROS package but explicitly launched
or loaded by the target package.

For a launched process:

```yaml
- name: /controller_server
  package: nav2_controller
  executable: controller_server
  purpose: Provides path-following control.
```

For a composable node:

```yaml
- name: /container/detector
  package: detector_package
  plugin: detector_package::Detector
  purpose: Provides composable detection.
```

Each entry requires `name`, `package`, `purpose`, and exactly one of
`executable` or `plugin`.

An external node may additionally contain `topics`, `services`, `actions`, `tf`,
and `parameters`. These resources use the same field definitions as
package-implemented node resources and are interpreted from the external node's
perspective.

For example:

```yaml
- name: /controller_server
  package: nav2_controller
  executable: controller_server
  purpose: Provides path-following control.
  services:
    - name: /controller_server/get_state
      type: lifecycle_msgs/srv/GetState
      role: server
      purpose: Reports the controller lifecycle state.
  tf:
    - source_frame: odom
      target_frame: base_link
      purpose: Provides the robot pose relationship used for control.
```

Service roles and TF frame ordering use the external node's perspective in the
same way as for a package-implemented node.

Only include resources supported by the target package's reachable launch,
remapping, or configuration evidence. Do not infer unspecified interfaces from
ROS conventions.

## Environment Variables

```yaml
- name: ROBOT_MODEL
  purpose: Selects the robot-specific runtime configuration.
  required: true
```

| Field | Required | Meaning |
| --- | --- | --- |
| `name` | Yes | Exact environment variable name. |
| `purpose` | Yes | How the variable affects startup or runtime behavior. |
| `required` | Yes | `true` when normal execution cannot continue without it. |

## Resource Ownership

1. Place each topic, service, action, TF relationship, and parameter under the
   node that uses it.
2. Repeat a shared resource under each represented participating node with that
   node's direction or role.
3. Do not treat a topic, frame, namespace, file, device, or parameter as a node.
4. Keep resources of launched foreign nodes under `external_nodes`.
5. Record effective launch remappings rather than only source-code default
   names.
6. Use one verified dynamic pattern for repeated equivalent instances rather
   than duplicating the same node contract.

## Omission and Validation Rules

- Omit optional fields and categories that do not apply.
- Do not emit empty lists, empty strings, or null values.
- Do not use placeholders such as `none`, `N/A`, `unknown`, or `not
  applicable`.
- Do not add fields outside this specification.
- Every item must be supported by reachable reference-package evidence.
- Tests, unused configuration files, and documentation-only examples do not
  create production runtime contracts.
- The description must remain sufficient for evaluation without requiring the
  generator to inspect `metric.yaml` or the reference package.

## Author Checklist

Before adding a benchmark case, verify that:

1. `intent.package_name` matches `package.xml`.
2. Functional requirement IDs are sequential and each requirement describes one
   observable outcome.
3. Every represented node is assigned to the correct package boundary.
4. Topic, service, and action types use canonical ROS 2 syntax.
5. Resource directions and roles are written from the containing node's
   perspective.
6. Launch arguments, effective remappings, external nodes, parameters, TF
   relationships, and environment variables have been reconciled with reachable
   source and launch control flow.
7. No empty categories, placeholder values, unsupported fields, or hidden
   metric-only requirements remain.
