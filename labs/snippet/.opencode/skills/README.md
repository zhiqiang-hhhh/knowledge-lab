# Local Skills

This directory stores project-local skill documents for repeatable editing styles.

## Available Skills

### `annotation-style`

Path: `.opencode/skills/annotation-style/SKILL.md`

Use it when you want to add explanatory comments to algorithmic code such as:
- matrix/tensor slicing and indexing
- PQ / IVF / residual PQ
- k-means or clustering code
- distance/score matrices, assignments, codes, and reconstruction steps
- numeric pipelines where array shape/axis meaning is easy to lose

## What This Skill Enforces

- one consistent running example across related functions
- comments that always explain both `shape` and semantic meaning
- explicit explanation for array axes when relevant
- explicit explanation for slicing code like `X[:, l:r]`
- comments that follow the algorithm in order instead of isolated local notes
- consistent naming for `X`, `Xi`, `C`, `d2`, `assign`, `codes`, `Xhat`, `residual`

## Recommended Invocation

Use prompts like:

```text
使用 Annotation Style skill，给这个文件补充 shape、轴语义、数组变换过程注释。
```

or

```text
使用 Annotation Style skill，给 `ivf_pq_residual_demo/ivf_pq_experiment.py` 补一套带 shape、数组语义、统一 4 维例子的连贯注释。
```

or

```text
按 `Annotation Style` 的 PQ 部分规范，补充 `kmeans`、编码、重建、residual 流程的教学型注释。
```

## Scope

These files are project conventions. Even if the runtime does not auto-discover them,
they can still be referenced manually in future editing requests.

## Included Styles

- General array algorithm style: for broader array and matrix algorithms.
- PQ style: for PQ / IVF / residual-PQ teaching comments.
