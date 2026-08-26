# Description Format Specification

This document defines the public `description.yaml` format for one ROS 2
package-generation benchmark case. The Description is supplied to both the
Coder and Evaluator. It contains the complete public functional specification
but no hidden pass criteria.

The copyable template is available at
[`templates/description.yaml`](../templates/description.yaml). The matching
hidden Metric format is defined in
[`docs/metric-format.md`](metric-format.md).

## Top-Level Structure

```yaml
intent:
  package_name: <string>
  summary: <string>
  scope: <string>

functional_requirements:
  - id: FR-1
    text: <string>

target_environment: <optional string>
```

| Field | Required | Meaning |
| --- | --- | --- |
| `intent` | Yes | Package identity, purpose, and responsibility boundary. |
| `functional_requirements` | Yes | Ordered public behaviors supplied to Coder and Evaluator. |
| `target_environment` | No | Concise robot, sensor, or system context when it materially constrains implementation. |

No other top-level fields are part of the revised format. In particular,
`interfaces` is not a Description section.

## Intent

### `intent.package_name`

- **Required.**
- Must match the benchmark case directory name.
- Must match `metric.yaml` `package_name`.
- Must use lowercase letters, digits, and underscores, beginning with a
  lowercase letter.
- If an optional reference archive is retained, its `package.xml` name must
  also match.

### `intent.summary`

- **Required.**
- Concisely states the package's primary purpose and externally meaningful
  outcome.
- Describes the package rather than its implementation files.
- Provides enough context to interpret the public FRs without repeating every
  criterion.

### `intent.scope`

- **Optional but recommended when the package boundary could be ambiguous.**
- States what the generated package implements.
- States what external packages, hardware, simulators, users, or data sources
  must provide.
- Does not enumerate dependency-internal implementation details.

## Functional Requirements

`functional_requirements` is a non-empty ordered list visible to both Agents.

```yaml
functional_requirements:
  - id: FR-1
    text: >-
      Describe one public observable package behavior.
```

| Field | Required | Meaning |
| --- | --- | --- |
| `id` | Yes | Sequential identifier beginning with `FR-1`. |
| `text` | Yes | Public required behavior evaluated by one or more hidden PCs. |

### FR Identity Rule

The ordered `(id, text)` pairs in Description `functional_requirements` must
exactly match Metric `metrics`.

```text
description.functional_requirements[n].id   == metric.metrics[n].id
description.functional_requirements[n].text == metric.metrics[n].text
```

Whitespace folding in YAML may differ, but the parsed string values must be
identical.

### FR Authoring Rules

1. Use sequential IDs: `FR-1`, `FR-2`, `FR-3`, and so on.
2. Do not omit, duplicate, or reorder IDs.
3. Describe observable required behavior, not a source function or file.
4. Include meaningful failure handling, lifecycle behavior, dynamic
   multiplicity, data processing, launch orchestration, and exported library
   behavior when they are part of the package contract.
5. Generalize incidental implementation details such as a callback name,
   helper class, loop structure, timer period, or internal algorithm unless
   the detail is itself a public requirement.
6. Include exact topic, service, action, TF, parameter, environment-variable,
   or launch names in the FR text only when exact interoperability is required.
7. For reusable libraries, cover distinct public facilities as well as
   executables and launch behavior.
8. Do not rely on hidden PCs to introduce behavior absent from the FR.

An FR may contain a coherent compound outcome when its parts are jointly
meaningful. Hidden PCs split that outcome into independently verifiable parts
whenever practical.

## Target Environment

`target_environment` is an optional natural-language string.

```yaml
target_environment: >-
  A differential-drive mobile robot equipped with a 2D lidar.
```

Use it when the target platform or sensor context materially affects generation,
for example:

- a TurtleBot3 application;
- a Nav2-enabled mobile robot;
- a calibrated RGB-D or stereo-camera system;
- a camera-and-lidar sensor-fusion system;
- a robot equipped with multiple 2D laser scanners;
- a named demonstration robot model.

### Target-Environment Rules

1. Keep the value to one concise statement.
2. Identify the robot, sensor, or system class rather than listing ROS graph
   resources.
3. Do not repeat topics, TF frames, parameters, dependencies, or every FR.
4. Do not claim compatibility beyond what the public FRs and package scope
   support.
5. Omit the field for platform-independent utilities when it adds no material
   context.

Examples of intentional omission include a generic synthetic map publisher or
an image utility that supports both local camera input and synthetic images
without a fixed target platform.

## Where Interface Requirements Belong

The revised Description does not contain an `interfaces` inventory. When an
exact ROS interface is functionally required, state it in the relevant FR.

```yaml
functional_requirements:
  - id: FR-1
    text: >-
      The node publishes sensor_msgs/msg/LaserScan messages on scan with the
      configured frame identifier.
```

Do not list every implementation-selected topic, parameter, TF frame, or
dependency. The Coder may choose unspecified interfaces and verify installed
ROS APIs with its allowed tools.

## Omission and Validation Rules

- Omit optional fields that do not apply.
- Do not emit empty lists, empty strings, or null values.
- Do not use placeholders such as `none`, `N/A`, `unknown`, or `not
  applicable`.
- Do not add fields outside this specification.
- The Description must be sufficient for the Coder to understand every public
  FR without reading `metric.yaml` or an optional reference archive.
- A candidate must not be penalized for an interface or implementation detail
  absent from the public Description.

## Complete Example

```yaml
intent:
  package_name: turtlebot3_follower
  summary: >-
    Coordinates a chain of TurtleBot3 followers through Nav2 FollowPath.
  scope: >-
    Provides follower logic and launch orchestration; robot drivers,
    localization, and actuation are external.

functional_requirements:
  - id: FR-1
    text: >-
      The follower executable accepts a requested follower count and creates
      one follower node for each index.

  - id: FR-2
    text: >-
      Each follower submits a two-pose path to its follower-specific
      FollowPath action server.

target_environment: >-
  A multi-robot system using TurtleBot3 mobile robots.
```

## Author Checklist

Before accepting a Description:

1. Confirm that `intent.package_name` matches the case directory and Metric.
2. Confirm that FR IDs start at `FR-1` and remain sequential.
3. Confirm that every FR describes public required behavior.
4. Confirm that Description and Metric FR IDs, order, and parsed text match
   exactly.
5. Confirm that no hidden PC adds a behavior absent from its public FR.
6. Confirm that `interfaces` and unsupported top-level fields are absent.
7. Confirm that `target_environment` is concise, accurate, and useful, or
   intentionally omitted.
8. Confirm that the Description is sufficient without Metric or reference-code
   access.
