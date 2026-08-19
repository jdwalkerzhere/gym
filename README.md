# gym

`gym` is a very thin, file-based technical-product training loop:

```bash
gym flash
$EDITOR exercises/flash/0001-exercise.md
gym check
```

Codex authors one source-grounded exercise. You edit an ordinary file. `gym check` validates open exercises in creation order, records what happened, and stops at the first failure. Later exercises receive that mastery and failure context.

## Four depths

```text
Flash       learn the pieces
Leet        use the pieces
Spec        solve complete requirements
Engagement  discover and solve the problem
```

The same capability can progress from recall through usage, composition, design, edge cases, tradeoffs, and ambiguous transfer. Correct repetition at one level is not treated as higher-level mastery.

## Start a product gym

```bash
git clone <gym-template> company-gym
cd company-gym
uv sync
uv run gym init "Product name"
```

Then give Codex the authoritative docs, SDKs, specifications, examples, or repositories to freeze and ask it to initialize the product by following `AGENTS.md`. Sources are copied into an inspectable snapshot; curriculum YAML points back to them. Nothing refreshes automatically.

```bash
uv run gym status
uv run gym flash
uv run gym leet
uv run gym spec
uv run gym engagement
uv run gym check
```

Each generation command creates exactly one exercise. Multiple exercises may be open; checking always uses their global creation order. Completed files stay where they are.

## Ownership

The repository files are the product pack and workspace: frozen sources, concepts, capabilities, provenance, exercises, fixtures, rubrics, and answers. SQLite at `.gym/mastery.sqlite` holds attempts, scores, classified failures, recency, depth, compositions, and edge observations. Deleting it loses learning history, not the curriculum.

Codex invocation defaults to `codex exec` and can be changed with `GYM_CODEX_COMMAND`. Long authoring and judging instructions live in `prompts/`, not Python. Automated tests inject a fake adapter and never call Codex.

V1 intentionally has no web/TUI, accounts, sync, crawler, reference solutions, scheduler, graph/vector database, or plugin system.
