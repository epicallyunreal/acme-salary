---
name: log-decision
description: Append an ADR-style entry to docs/DECISIONS.md. Use whenever a non-obvious choice is made, a dependency is added, the human answers a question about the spec, or the user says "log this decision" or "note why we did that".
argument-hint: <one-line title>
---

# Log a decision

Append to `docs/DECISIONS.md`, after the last `D<n>` entry and before the Open questions table. Number it `D<n+1>`. Keep it under ten lines.

```
## D<n>. <title: $ARGUMENTS>

Context: what forced the choice, in one or two sentences. Name the alternative that was on the table.

Decision: what was chosen, concretely (table, module, library, parameter).

Consequences: what gets easier, what gets harder, what to revisit and when.
```

Rules.

- Write it the moment the choice is made, in the same commit as the code.
- A new runtime dependency is always a decision. Say what it does and why the standard library or an existing dependency was not enough.
- An answer from the human to a spec question is a decision. Quote the question, record the answer, and say which spec section it affects. Do not edit the spec yourself.
- If the decision changes something an earlier entry decided, add a line to the earlier entry: `Superseded by D<n>`.
- No em dashes, no semicolons. Plain sentences.
