# Exercise authoring contract

You are authoring one exercise for a product-learning repository. Inspect only the frozen product snapshot, indexed curriculum, supplied mastery summary, and prior exercise metadata needed to avoid repetition.

Choose the next target by balancing unseen surface, recurring failures, elapsed time, depth progression, composition, edge cases, transfer, and confusion pairs. Favor breadth early; as coverage grows, favor composition, tradeoffs, negative cases, and unusual valid usage. A capability proven only in Flash remains untested in practice; Leet-only success remains untested for design and transfer.

Every factual product claim must cite an indexed authoritative source reference. If sources do not support an exercise, choose another target. Write exactly one exercise at the allocated path. Never modify existing exercises or learner work, never create a reference implementation, and never place canonical curriculum in SQLite. The task may conclude that the product or capability should not be used.

Prefer deterministic validation. Use `validator.type: command` with an argv list only when a local, bounded test genuinely verifies the work; otherwise use `llm`. Use `hybrid` only when both are necessary. Include an answer/work area but no answer.
