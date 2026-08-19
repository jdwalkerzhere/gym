# Operating `gym`

`gym` is a product-agnostic, file-based training coordinator. Preserve the learner loop `generate → edit → check → learn → generate better` and the seven-command CLI. The filesystem owns frozen sources, curriculum, exercise definitions, graders, fixtures, and learner work. `.gym/mastery.sqlite` owns attempts, completion, and derived learner evidence.

## Initialize one product

1. Use only authoritative materials selected by the user: official docs/specifications, SDKs, examples, repositories, and local technical material. Do not create exercises unless asked.
2. Freeze the selected revision under `product/snapshot/`. Never silently refresh it during exercise generation.
3. Create `product/snapshot/manifest.yaml`. Its `snapshot.id` must equal `product/product.yaml:snapshot.id`. Each source needs a stable `id`, `kind`, local file-or-directory path relative to the snapshot directory, and origin/provenance; record revision and SHA-256 for files when available. Frozen SDK/repository trees may be directory entries pinned by revision.
4. Build `product/knowledge/concepts.yaml`, `capabilities.yaml`, and `terminology.yaml`. Concepts are mental models; capabilities are things a learner can do. Every concept/capability needs a stable ID and at least one manifest source ID. Add meaningful descriptions, importance, difficulty, prerequisites, and related IDs.
5. Validate unique IDs, resolvable source IDs, existing local source paths/hashes, and valid prerequisites/relationships. Cover limitations, negative cases, product boundaries, and terminology. Unsupported claims are gaps to report, never facts to invent.
6. Run `gym status`. Generation refuses an invalid pack.

Large snapshots are expected. Do not synthesize or inject the whole corpus into prompts. The engine supplies the manifest, curriculum, coverage, and learner evidence; inspect only locally frozen files named by relevant source refs.

## Exercise Root Contract

One generation invocation creates exactly one allocated root and changes nothing else.

- Flash defaults to one Markdown file with YAML frontmatter.
- A standalone non-Markdown file uses an adjacent `<filename>.exercise.yaml` sidecar.
- Leet, Spec, and Engagement default to one directory whose canonical metadata is `exercise.yaml`.
- A directory may contain any exercise-local tree: work, grader/tests, fixtures, datasets, mock services, incumbent, evals, client, or facilitator.
- `facilitator/` is conventionally material the normal learner workflow need not open; it is not access-controlled.
- Never modify existing exercises, learner answers, product files, prompts, application source, or `.gym/`. Never create a second root.
- Never supply `solution.py`, a reference implementation, golden answer, or ideal design. Assertions, expected outputs, thresholds, and rubrics are allowed when they validate behavior without exposing the target implementation.

Use a single file for Flash unless complexity genuinely requires otherwise. Build runnable bundles for Leet. Spec may own a complete requirement/evaluation environment. Engagement may own incomplete customer context, independent client/incumbent systems, hidden facilitator facts, discovery/final-readout rubrics, and a work area. Target-product use, partial use, further evaluation, incumbent retention, and rejection must all be allowable conclusions when technically justified.

## Metadata Contract

Schema-v2 canonical metadata is under `gym`:

```yaml
gym:
  schema_version: 2
  id: leet-0012
  type: leet
  created_at: 2026-08-18T21:00:00Z
  order: 42
  snapshot: snapshot-id
  capabilities:
    - id: resource.patch
      weight: 0.6
      demonstrates:
        usage: 1.0
        composition: 0.7
        edge: 0.4
  concepts:
    - id: mutation-semantics
  difficulty: 4
  selection:
    reason: confusion_pair
    detail: repeated patch/replace confusion at composition depth
  source_refs: [docs-resource-update, sdk-client]
  validators:
    - type: command
      cwd: .
      command: [uv, run, pytest, -q, grader]
      timeout_seconds: 120
      requires_env: [PRODUCT_API_KEY]
    - type: llm
      targets: [work/recommendation.md]
      rubric: grader/recommendation-rubric.md
```

IDs and global `order` are unique. Snapshot must be active. Capability/concept IDs and source IDs must resolve. Difficulty is positive. Each capability declares its relative exercise weight and what a successful completion demonstrates. Supported dimensions are recognition, recall, basic, usage, composition, selection, transfer, tradeoff, and edge.

V1 frontmatter with singular `validator` remains readable. New exercises must use schema 2 and `validators`. Completion is SQLite learner state; do not write `status: completed` into learner files. Legacy completed metadata remains honored.

## Validator Contract

Validators run in order and stop on hard failure. The exercise passes only when all required validators pass.

- `command` is an argv list, never a shell string. `cwd` is relative to the exercise root and cannot escape it. Default timeout is 120 seconds. `requires_env` lists names only; `gym` checks presence and never prints values. The exercise may invoke pytest, Cargo, npm, Go, Docker Compose, a local script, or a live API—`gym` has no knowledge of those systems.
- Live integration owns temporary resource cleanup in teardown/finally. Do not store credentials.
- `llm` declares text `targets` relative to the root and an optional rubric. The judge sees only those learner artifacts, metadata, and frozen grounding needed for judgment.
- Deterministic success emits the exercise's declared mastery evidence without an LLM call.
- Deterministic failure captures bounded diagnostics. Optional Codex classification may add stable failure/confusion evidence but must not reveal solution code. If unavailable, generic `deterministic_check_failed` evidence is recorded and checking continues normally.
- Mixed command/LLM observations merge. Generation infrastructure self-tests never count as learner attempts.

Before finishing a large generated environment, validate its infrastructure without solving the learner task: fixtures parse, tests collect, mock/incumbent systems start where practical, and the untouched learner scaffold fails for the expected reason rather than a broken grader.

## Mastery Evidence Contract

SQLite stores append-only attempt observations: exercise/capability IDs, exercise type, result/score, dimension, difficulty, evidence weight, failure mode, related/confused capability, edge case, and timestamp. Deterministic successes derive observations from `demonstrates`; semantic judges emit structured observations. Do not collapse evidence into one authoritative score.

Generation should inspect unseen/lightly exposed capabilities, weak dimensions, recurring errors/confusion pairs, recent activity, highest successful/attempted difficulty, successful/failed compositions, encountered edge cases, and untested dimensions. Favor rapid breadth early, then remediation, composition, distinctions, edge behavior, and transfer. Do not hammer one weak target indefinitely. Flash recall never implies Leet usage; Leet usage never implies Spec selection or Engagement transfer.

Advanced exercises vary scenario/domain, combine capabilities naturally, test neighboring concepts, invalid and unusual supported usage, limits, tradeoffs, and negative fit so memorized surface patterns are insufficient.

## Source Reference Contract

The inspectable chain is `manifest source ID → grounded concept/capability → exercise source_refs → attempt evidence`. Product claims come only from the active local frozen snapshot. Normal generation does not browse for updated product facts. If relevant frozen evidence is missing, choose another target or report the source gap.

When changing the engine, preserve one-root append-only generation, global creation-order checking, SQLite completion, bounded diagnostics, deterministic-first validation, and the filesystem/learner-state boundary. PyYAML remains the only runtime dependency.
