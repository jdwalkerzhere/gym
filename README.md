# gym

`gym` is the center for kids who can't read good and who wanna learn to do other stuff good too.

```bash
gym flash
$EDITOR exercises/flash/0001-exercise.md
gym check
```

Codex authors one source-grounded exercise. You edit normal files. `gym check` validates every incomplete exercise in global creation order, records the evidence, and stops at the first failure. Later exercises receive the resulting mastery and failure history.

```text
Flash       learn the pieces
Leet        use the pieces
Spec        solve complete requirements
Engagement  discover and solve the problem
```

A Flash is normally one Markdown file. Leet, Spec, and Engagement are one directory each and may contain real code, tests, fixtures, mock services, datasets, incumbents, rubrics, facilitator material, and learner work. Each command still creates exactly one exercise root:

```bash
gym flash
gym leet
gym spec
gym engagement
gym check
gym status
```

## Start a product gym

```bash
git clone <gym-template> company-gym
cd company-gym
uv sync
uv run gym init "Product name"
```

Then give Codex the authoritative documentation, SDKs, specifications, examples, or repositories and ask it to initialize the pack using `AGENTS.md`. It freezes source files or pinned repository trees locally, registers stable source IDs in `product/snapshot/manifest.yaml`, and grounds every concept, capability, and exercise back to that registry. Ordinary generation uses the frozen local snapshot; it does not silently refresh from the web.

The filesystem owns the product pack, exercise definitions, fixtures, graders, and learner work. `.gym/mastery.sqlite` owns attempts, completion, classified failures, and evidence by capability, learning dimension, difficulty, and weight. Deleting SQLite loses learner history, not the curriculum.

Command validators can run any exercise-owned tool with a working directory, timeout, and declared environment-variable requirements. LLM validators cover semantic artifacts; ordered validators combine both. The engine has no product-, language-, SDK-, API-, or runtime-specific logic.

V1 intentionally has no web/TUI, accounts, sync, crawler, reference solutions, scheduler, graph/vector database, or plugin system.
