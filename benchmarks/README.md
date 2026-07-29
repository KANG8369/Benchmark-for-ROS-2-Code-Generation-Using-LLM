# Benchmark Cases

Each child directory contains one ROS 2 package benchmark:

```text
<package_name>/
├── description.yaml
├── metric.yaml
└── reference/
    ├── package.xml
    └── ...
```

Only `description.yaml` is given to the code-generation system. `metric.yaml` and `reference/` are reserved for benchmark authoring and evaluation.

Do not add a case until its description and metrics have been checked against the complete runtime-reachable reference package.

Metric schema `2.0` requires every reference-evidence item to declare its
`kind`, reference-relative `path`, searchable `locator`, exact contiguous
`snippet`, and behavioral `explanation`. The snippet records provenance; it is
not used to require source-code identity from a generated package.

Keep each snippet to the minimum code needed to establish its criterion; no
fixed line-count limit applies. When proof is non-contiguous, use multiple
short evidence items rather than one excerpt containing unrelated code.

Each pass criterion must represent one independently scorable behavior.
Behaviors that can pass or fail separately must use separate sequential IDs,
while multiple reference artifacts demonstrating the same behavior remain
grouped under one criterion.
