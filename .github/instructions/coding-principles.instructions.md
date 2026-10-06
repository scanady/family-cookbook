---
description: "Scope, completion, modernization, and code-quality rules across languages and project types."
applyTo: "**/*.{ts,tsx,js,jsx,mjs,cjs,py,ipynb,java,sql}"
---

# Coding Principles

`core-principles.instructions.md` comes first — **Think Before Acting** governs everything below.

## Simplicity First

Write the minimum code that solves the problem. Nothing speculative.

- **No extra features** beyond what was asked.
- **No single-use abstractions** — code with exactly one call site stays inline.
- **No unrequested flexibility** — no configurability, hooks, or extension points nobody asked for.
- **No impossible-case handling.** Don't write error paths for states that can't occur; if unsure whether a state can occur, find out rather than defend against it.
- **Simplify long solutions.** Rewrite shorter if the result is materially longer than necessary.
- **Senior-engineer bar.** If a senior engineer would call it overcomplicated, it is.

## Surgical Changes

Touch only what the task requires. Clean up your own mess, not the neighborhood's.

- **Do not polish or refactor adjacent code** — limit edits to what the request actually needs.
- **Match local style**, even when you'd structure it differently — unless the style violates a stated invariant, in which case name the violation rather than quietly matching it.
- **Clean up your own orphans** — remove imports, variables, and functions your change made unused.
- **Leave pre-existing dead code alone.** Mention it; delete it only when asked, or when it sits inside code your change already rewrites.
- **Trace every line to the request** — every changed line should have a direct reason to exist.

## Goal-Driven Execution

Define success criteria. Loop until verified.

- **Define verifiable outcomes first**, before writing code.
- **Add validation by test** — write the test for the invalid input, then make it pass.
- **Fix bugs by reproduction.** Reproduce the bug in a failing test first; a fix with no failing test in front of it is a guess.
- **Refactor behind behavior checks.** Confirm tests pass before and after — the diff must not change behavior.
- **Plan multi-step work.** State the steps briefly, each with the check that proves it done.
- **Validate after each logical unit** — cheapest check first: targeted test, then lint or typecheck, then broader build.
- **Prefer strong success criteria.** Vague criteria force a round trip; concrete ones let the work finish.

## Don't Be A Quitter

Complete the task. Never leave code half-done.

- **No stubs or TODOs.** No `// TODO`, `// FIXME`, `NotImplementedError`, `throw new NotImplementedException()`, or commented-out blocks — every code path is fully implemented.
- **No dead ends.** Finish what you start in the same change, including every caller, test, and document it touches.
- **No partial implementations.** Every public API, endpoint, or component is fully functional when committed; incomplete work stays on a branch.
- **Report honestly.** If something was skipped or is failing, say so and show the output — never describe intent as verified behavior.

## Aggressive Modernization

No-legacy policy. Code cleanliness outranks backward compatibility.

- **Refactor atomically** — change a signature and update every caller in the same change.
- **No compatibility layering in names** — no `v2`, `new`, `legacy`, or `old` as prefix, suffix, or embedded form.
- **No deprecation markers** — no `@Deprecated`, `@deprecated`, or `DeprecationWarning`. Delete instead.
- **No behavior toggles** — no `if`/`else` switching between an old path and a new one.
- **No keeping code "just in case."** Unused private methods and helpers go.
- **Purge on update** — delete what the new requirement made obsolete before refactoring over it.
- **Delete rather than adapt.** Recovery is version control, not a directory of dead code.

## DRY

Every piece of knowledge has a single, authoritative representation.

- **Extract on the second real use** — not on the first anticipated reuse.
- **One canonical location** for constants, configuration, types, and content structures — never duplicated across files.
- **Abstract repeated interface patterns** into shared components once they actually recur.
- **No cross-boundary duplication.** Data owned by one layer is fetched from it, not re-copied as static files into another — cache for performance, never fork the source.
- **Never copy-paste.** Extract and reuse, and update all call sites in the same change.
- **Reuse before creating** — look for the owning module, type, helper, or component first.

## Naming

Prefer clear, stable names over clever ones. Use kebab-case for new file, route, and content-asset names unless a platform convention requires otherwise; language identifiers stay idiomatic for their language.

## When These Pull Against Each Other

- **Surgical vs. Aggressive Modernization** — *scope* decides. Surgical bounds which files you open; Aggressive governs how you treat code once inside the blast radius. Don't wander, but purge rather than accumulate within what you're already rewriting.
- **Simplicity vs. DRY** — *count* decides. Two real call sites is duplication worth extracting; one call site plus a hunch is a speculative abstraction.
- **Surgical vs. Don't Be A Quitter** — the *request* decides. Finishing means every caller, test, and document your change touches — not fixing what the change merely revealed.
