# Operating `gym`

This repository is a file-based technical-product gym. The filesystem owns sources, curriculum, exercises, rubrics, fixtures, and learner work. `.gym/mastery.sqlite` owns only attempts and derived learner observations. The core is product-agnostic. Keep the user loop `generate → edit → check` and keep paths stable.

## Initialize one product

1. Accept only authoritative materials chosen by the user: official documentation, specifications, SDKs, examples, repositories, and local documents. Record URLs plus immutable revisions/commits where available.
2. Freeze materials under `product/snapshot/`; do not build a live crawler. Preserve source-relative paths or an obvious manifest so citations remain inspectable. Never silently refresh.
3. Fill `product/product.yaml` with product name, snapshot ID, capture time, and source provenance. A snapshot ID should be a revision or digest meaningful to a human.
4. Build `product/knowledge/concepts.yaml`, `capabilities.yaml`, and `terminology.yaml`. Each list entry needs a stable generic ID, name, description, importance, difficulty, prerequisites/related IDs where useful, and precise `source_refs`. Capabilities describe things a learner can do; concepts describe mental models. Add `relationships.yaml` only if prerequisites/related fields cannot express a real need.
5. Validate every claim against the frozen material, every reference resolves, IDs are unique, relationships point to existing IDs, and the surface includes limitations, negative cases, and product boundaries. Missing evidence is a gap to report, not permission to invent.

Do not ask the learner to populate SQLite. Run `gym status` after initialization; the database is created automatically.

## Generate an exercise

The CLI composes `prompts/generate.md`, the type prompt, an exact path/metadata contract, curriculum files, open-exercise metadata, and the mastery/failure summary. Follow all of it.

- Write exactly one new file at the allocated path. Do not edit existing exercises, learner answers, `.gym/`, or product knowledge.
- Select from new surface, weakness remediation, spaced review, composition, edge cases, transfer, confusion pairs, and depth progression. Favor breadth early. Do not hammer one weak capability indefinitely.
- Match level: Flash is tiny recall/recognition; Leet is bounded execution; Spec gives complete requirements; Engagement withholds requirements and tests discovery/transfer.
- Higher mastery requires evidence at higher levels. Repeated Flash success is not composition, design, edge mastery, or transfer.
- Cite snapshot source locations for important product behavior. Choose another target if evidence is insufficient.
- Include stable ID, type, time/order, snapshot, open status, weighted capabilities, difficulty, selection reason/detail, provenance, and validator metadata.
- Prefer one deterministic command when it proves the acceptance criteria. Otherwise use semantic judging. Tests and fixtures may define behavior but may not contain a reference technical implementation.
- Never create `solution.py`, `answer.py` as a supplied answer, `golden/`, or equivalent. A file named `answer.*` is allowed only as empty learner work.

Advanced exercises should naturally combine previously isolated capabilities, target failed compositions and confusable neighbors, introduce sourced limits/edge parameters, require tradeoff reasoning, and sometimes make non-use or partial use the correct conclusion.

## Judge and record

`gym check` owns orchestration. It discovers every open exercise across all types by global `order`, validates each, records the attempt, marks passes completed in place, and stops on the first failure.

Use deterministic validation first. A semantic judge receives the learner file, criteria/rubric, targets, and sources, then returns structured JSON: pass, numeric score, concise feedback, per-capability observations, and stable failure modes. Distinguish recall, usage, composition, transfer, tradeoff, and edge evidence. Record confusion via `related_capability` and unusual cases via `edge_case`. Do not store chain-of-thought and do not write the learner's answer.

When changing the engine, preserve append-only generation, global checking order, stable completed paths, source grounding, and the filesystem/SQLite boundary. Use the standard library before adding dependencies; PyYAML is the sole runtime dependency because YAML is the repository format.
