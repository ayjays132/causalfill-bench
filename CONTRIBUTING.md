# Contributing an original task

Implement the evaluator-side `Task` interface with a typed public contract, tool costs, immutable file observations or explicit state transitions, an independent `evaluate(fill)` and a constructive reference. Accept behaviorally equivalent completions. Keep candidate execution inside a constrained interpreter or a separately isolated sandbox.

Document the missing dependency, evidence path, bounds, ambiguity conditions, structural split and one-variable twin. Include tests that a plausible wrong answer fails, an alternative valid answer passes, invalid tools do not mutate state, and the public output does not reveal the answer. Use an evidence-only reference callback when possible and exercise it through `Session`, not direct hidden-state calls.

Do not silently increase budget to make a reference pass. Version changes to tasks, reference implementations and graders. Explain whether earlier results can be regraded. Label third-party material, source revision and license; retain license notices. Original code is preferred for these small generators.

Run `python -m unittest discover -s tests -v` and a small paired suite. For novel failure claims, save the exact task configuration, public trace, candidate completion and trusted grade. Remove credentials and private data from issues. A self-consistent hash chain is not authenticated unless its final hash is independently anchored.

Contributions should state whether prompts and reference solutions are human-authored or AI-assisted. This project's contribution policy is independent of SkillsBench's policy; do not claim compatibility with its submission requirements by association.

## Result semantics and release completeness

When a task executes irreversible actions, keep actual outcome diagnostics independent of final certificate parsing. Override `Task.failure_verdict(details)` when a failed submission, abstention or termination must preserve already-executed state. Strict success must still require every task obligation. Document any task-specific meaning of `safety`.

A change to measurement semantics requires explicit scoring-version handling; never relabel old records as current runs. Equivalent mechanisms must share a structural identity even when their seeds, labels or split names differ.

For a release, use fresh evidence directories, run the complete unit suite and paired controls, check the versioned release manifest, then regenerate the complete inventory. Frozen historical logs and source files must remain tracked. See [release instructions](docs/releasing-v052.md) and [migration notes](docs/migration-v052.md).
