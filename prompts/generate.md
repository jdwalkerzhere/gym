# Exercise authoring contract

Create exactly the allocated exercise root. It is either one standalone file or one directory. You may create any files needed below a directory root, but must not create or modify anything outside the allocated root—including existing exercises, product files, prompts, source, and `.gym/` learner state.

Use only the active frozen local snapshot and product knowledge files for product-specific facts. Do not browse for current product behavior during ordinary generation. Start from the curriculum and learner evidence, select relevant capability/source IDs, then inspect their paths in `product/snapshot/manifest.yaml` and read only those frozen files. If the snapshot cannot support a claim, choose another target.

Select the next exercise by balancing unseen/lightly exposed surface, weak dimensions, recurring failures and confusion pairs, recency, highest demonstrated difficulty, missing depth, composition, edge evidence, and transfer. Favor broad exposure early; later favor composition, difficult distinctions, limitations, unusual supported usage, negative fit, and scenario variation. Never drill one weak item indefinitely. Flash evidence does not imply Leet usage; Leet usage does not imply Spec selection or Engagement transfer.

Metadata must use real capability, concept, and manifest source IDs. For each capability, declare `weight` and the `demonstrates` dimensions a successful check proves. Assign meaningful difficulty. Use the smallest ordered validator list that proves the acceptance criteria. Prefer deterministic commands; add an LLM rubric only for semantic work. Never create a reference implementation or supplied answer.

For a directory exercise, build whatever local environment the task actually needs: learner workspace, tests/grader, fixtures, datasets, mock services, incumbents, evaluation scripts, rubrics, or facilitator material. The exercise owns its technologies and cleanup, including external resources in `finally`/teardown. Declare required credentials by environment-variable name; never store secrets.

Before finishing a large exercise, validate its infrastructure without solving the learner task: parse fixtures/specs, collect tests, validate service/config startup where practical, and distinguish an expected failure from untouched learner work from a broken grader. Generation/self-tests never update mastery.
