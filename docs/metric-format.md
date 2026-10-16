# Metric Format Specification

This document defines the hidden `metric.yaml` format for one ROS 2
package-generation benchmark case. The Metric is available to the Evaluator but
not the Coder.

The copyable template is available at
[`templates/metric.yaml`](../templates/metric.yaml). The matching public
Description format is defined in
[`docs/description-format.md`](description-format.md).

## Top-Level Structure

```yaml
package_name: <string>

metrics:
  - id: FR-1
    text: <public FR text>
    pass_criteria:
      - id: FR-1-PC-1
        text: <hidden criterion text>
```

| Field | Required | Meaning |
| --- | --- | --- |
| `package_name` | Yes | Package and benchmark case identity. |
| `metrics` | Yes | Ordered public FRs with hidden PCs. |

`reference`, `requirement_ids`, and named `M-*` wrapper objects are not part of
the revised format.

## Package Name

`package_name` must exactly match:

- the benchmark case directory name;
- Description `intent.package_name`;
- the generated package identity expected by the workflow.

If an optional authoring reference is retained, its `package.xml` name must
also match, but the reference is not an evaluation input.

## Functional-Requirement Entries

Each `metrics` item is one public Functional Requirement.

```yaml
- id: FR-1
  text: >-
    The node publishes timestamped LaserScan messages.
  pass_criteria:
    ...
```

Allowed FR keys:

```text
id
text
pass_criteria
```

No additional FR-level keys are permitted.

### Public-FR Identity

Metric FRs repeat Description FRs exactly and in the same order.

```text
metric.metrics[n].id   == description.functional_requirements[n].id
metric.metrics[n].text == description.functional_requirements[n].text
```

The Metric does not paraphrase, narrow, broaden, merge, split, or reorder public
FRs.

## Pass Criteria

Every FR has a non-empty ordered `pass_criteria` list.

```yaml
pass_criteria:
  - id: FR-1-PC-1
    text: >-
      Each published scan receives a current timestamp.
```

Allowed PC keys:

```text
id
text
```

### PC Identifier

PC identifiers combine the parent FR ID with a sequential criterion number.

```text
FR-1-PC-1
FR-1-PC-2
FR-2-PC-1
```

Numbering restarts at one for each parent FR. IDs must not be missing,
duplicated, or reordered.

### PC Authoring Rules

1. Derive every PC directly from its public parent FR.
2. Do not add a behavior that the Coder was never publicly asked to implement.
3. Prefer one independently verifiable behavior per PC.
4. Keep jointly meaningful steps together only when separating them would no
   longer represent a coherent outcome.
5. Describe candidate behavior rather than a reference implementation.
6. Do not require a callback, function, class, helper, loop, file path, source
   layout, programming language, or library unless it is explicitly public in
   the FR.
7. Do not require an exact parameter, topic, service, action, TF, plugin, or
   executable name unless that exact name is public in the FR.
8. Accept alternate implementations that provide equivalent observable
   behavior.
9. Write criteria that can be evaluated from immutable generated-package
   artifacts under the current static-evaluation policy.

### Good and Bad Criteria

Public FR:

```text
A follower warns and skips goal submission when its action server is unavailable.
```

Good PCs:

```text
The follower checks server availability before submitting a goal.
An unavailable server produces an explicit warning.
The unavailable-server path submits no goal.
```

Bad PC:

```text
The C++ callback calls wait_for_action_server(std::chrono::seconds(1)) and returns.
```

The bad criterion unnecessarily requires C++, a callback structure, a specific
API call, and a one-second timeout.

## Evaluation Policy

All PCs in the current benchmark are evaluated statically from:

- package manifests and build files;
- C++ and Python implementation files;
- launch and configuration files;
- plugin declarations and exported library metadata;
- custom interface definitions;
- installation and registration rules;
- the recorded build result.

Per-PC `evaluation` is not included in `metric.yaml`. If dynamic or simulation
evaluation is added later, it belongs to a separate frozen harness and
framework-level protocol rather than an ad hoc criterion field.

## Aggregation

The deterministic aggregation rule is:

```text
all PCs under one FR pass -> FR pass
any PC under one FR fails -> FR fail
build passes and all FRs pass -> Static Gate pass
```

The Orchestrator should verify the Evaluator's FR aggregation instead of
trusting an unsupported aggregate result.

## Evidence and Feedback

Evidence and feedback are Evaluator outputs, not Metric fields.

```json
{
  "criterion_id": "FR-1-PC-1",
  "status": "pass",
  "evidence": [
    "src/example.cpp:42 - publishes the required candidate message"
  ],
  "feedback": null
}
```

Evidence must cite the generated candidate package. Optional reference archives
are never candidate evidence and are not accessible to the Evaluator.

The framework must define whether failed-PC details are forwarded to the Coder.
Forwarding detailed PC feedback improves repair performance but reveals part of
the hidden rubric after the first evaluation. First-turn and final-turn scores
should therefore be reported separately when such feedback is enabled.

## Forbidden Fields

The following fields are not permitted anywhere in the revised Metric:

```text
evaluation
reference
reference_evidence
requirement_ids
path
anchor
snippet
explanation
```

Named `M-1`, `M-2`, and similar capability wrappers are also removed. The FR is
the Metric-level evaluation unit.

## Complete Example

```yaml
package_name: turtlebot3_follower

metrics:
  - id: FR-1
    text: >-
      The follower executable accepts a requested follower count and creates
      one follower node for each index.
    pass_criteria:
      - id: FR-1-PC-1
        text: >-
          The follower executable accepts a requested follower count.

      - id: FR-1-PC-2
        text: >-
          Exactly one follower node is created for each requested index.

  - id: FR-2
    text: >-
      A follower warns and skips goal submission whenever its FollowPath
      action server is unavailable.
    pass_criteria:
      - id: FR-2-PC-1
        text: >-
          The follower checks server availability before submitting a goal.

      - id: FR-2-PC-2
        text: >-
          An unavailable server produces an explicit warning.

      - id: FR-2-PC-3
        text: >-
          The unavailable-server path submits no goal.
```

## Author Checklist

Before accepting a Metric:

1. Confirm that `package_name` matches the case and Description.
2. Confirm that Metric and Description FR IDs, order, and text match exactly.
3. Confirm that every FR has one or more sequential PCs.
4. Confirm that each PC is directly supported by its public parent FR.
5. Confirm that PCs do not introduce hidden interfaces or implementation
   details.
6. Confirm that PC mappings contain only `id` and `text`.
7. Confirm that forbidden fields and reference evidence are absent.
8. Confirm that candidate evidence can be collected without reference-code
   access.
