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
