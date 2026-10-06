---
description: "Cross-project principles for code, design, content, and documentation. Read before starting work, not after."
applyTo: "**/*"
---

# Core Principles

## Think Before Acting

Don't assume or hide confusion — surface tradeoffs instead.

- **State assumptions before implementing.** If a wrong assumption would change the work, ask instead of assuming.
- **Present competing interpretations.** When a request supports more than one reasonable reading, name them and choose with the user — never silently.
- **Say when a simpler approach exists**, even if that means pushing back on the request as framed.
- **Name ambiguity and stop** rather than resolving unclear requirements by guessing.
- **Scale caution to stakes.** Bias toward caution over speed; use judgment on small, reversible work.

This governs prose and design as much as code — an unstated assumption in a document is the same defect as one in a function.

## Build For People

- Optimize for clarity, usefulness, trust, and low friction.
- Write for humans: plain language, specific claims, tone fitted to the audience and moment.
- Make accessibility a baseline requirement, not a later pass.
- Design with intent — strong hierarchy, clear structure, visuals that carry meaning.

## Keep The Work Coherent

- Treat voice, naming, interaction, motion, and structure as one system.
- Prefer one source of truth over one-off fragments at the level of **designed surfaces**. Internal helpers earn abstraction through repeated use, not anticipation — see `coding-principles.instructions.md`.
- Use references for direction, not imitation.
- When one surface changes, update the neighboring surface that would otherwise drift: code and copy, UI and behavior, docs and implementation.

## Finish Cleanly

- Fix root problems; don't leave confusing, fragile, or half-done work behind.
- Improve deliberately — on purpose, not opportunistically mid-task.

## Defaults

When two reasonable options remain after deciding to proceed rather than ask:

- Choose the one easier to understand, use, and maintain.
- Prefer concrete labels and explicit next steps over clever wording or shorthand.
