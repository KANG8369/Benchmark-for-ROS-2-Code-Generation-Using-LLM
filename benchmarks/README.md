# Benchmark Cases

Each direct child directory contains one ROS 2 package-generation benchmark:

```text
<package_name>/
├── description.yaml
├── metric.yaml
└── reference/          # optional authoring archive; never an Agent input
```

## Visibility

| Artifact | Coder | Evaluator |
| --- | --- | --- |
| `description.yaml` | Visible | Visible |
| `metric.yaml` | Hidden | Visible |
| `reference/` | Hidden | Hidden |

The Coder receives public intent, FRs, and an optional target environment. The
Evaluator receives the same Description plus hidden pass criteria and the
immutable generated-package artifact.

## Description Requirements

```yaml
intent:
  package_name: example_package
  summary: >-
    Describe the package purpose and primary outcome.
  scope: >-
    Describe package responsibilities and external responsibilities.

functional_requirements:
  - id: FR-1
    text: >-
      Describe one observable required behavior.

target_environment: >-
  Optionally describe the robot, sensor, or system environment.
```

Rules:

- `intent` and `functional_requirements` are required.
- `target_environment` is optional and is omitted when it adds no material
  generation context.
- `interfaces` is not part of the revised format.
- FR IDs start at `FR-1` and remain sequential.
- FR text is public to both Coder and Evaluator.
- The package name must match the case directory.

## Metric Requirements

```yaml
package_name: example_package

metrics:
  - id: FR-1
    text: >-
      Repeat the public FR-1 text exactly.
    pass_criteria:
      - id: FR-1-PC-1
        text: >-
          Describe one independently verifiable part of FR-1.
```

Rules:

- Metric FR IDs, order, and text exactly match the Description FRs.
- Every FR has at least one PC.
- PC IDs use `FR-<n>-PC-<n>` and remain sequential within their parent FR.
- A PC must be directly derivable from its public parent FR.
- A PC must not introduce a hidden behavior that the Coder was never asked to
  implement.
- PCs describe observable behavior and avoid reference-specific function names,
  callbacks, loops, helpers, source paths, and code structure.
- PC mappings contain only `id` and `text`.
- `evaluation`, `reference`, `reference_evidence`, `requirement_ids`, paths,
  anchors, snippets, and explanations are not allowed.

All current PCs are evaluated statically by framework policy. Evaluation mode
is not repeated in each PC.

## Result Aggregation

```text
all PCs under an FR pass -> FR pass
any PC under an FR fails -> FR fail
build passes + all FRs pass -> Static Gate pass
```

The Evaluator must cite candidate evidence from the generated package. Optional
reference archives are not candidate evidence and are not visible to either
Agent.

## Target Environment

Use one concise sentence when the target robot, sensor, or system context
materially affects implementation.

```yaml
target_environment: >-
  A differential-drive mobile robot equipped with a 2D lidar.
```

Do not turn this section into a topic, TF, parameter, or dependency inventory.
Platform-independent utilities may omit it.

## Optional Reference Archive

An existing case may retain `reference/` for manual provenance or historical
review. It is not required by the revised data format and must not be used by
the Evaluator to compare candidate source code. No reference evidence belongs
in `metric.yaml`.

The current registry implementation still checks for this directory and is
being migrated separately; this is a temporary loader constraint, not part of
the revised benchmark contract.

## Authoring Checklist

Before committing a case:

1. Verify the package name against the case directory.
2. Verify that Description and Metric FRs match exactly.
3. Verify sequential FR and PC IDs.
4. Verify that every PC is independently scorable whenever practical.
5. Remove implementation-specific and reference-specific wording.
6. Add a target environment only when appropriate.
7. Run the repository FR/PC validation scripts.
