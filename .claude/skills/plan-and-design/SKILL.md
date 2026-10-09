---
name: plan-and-design
description: After the spec review is approved, write docs/PLAN.md (what gets built, in what order, with estimates and acceptance per step) and docs/DESIGN.md (how it is built: modules, function contracts, data flow, API details, UI structure, visual direction) for the owner to review before step 1. Use when the owner says "write the plan", "plan and design", or right after they approve the spec review.
disable-model-invocation: true
---

# Plan and design, before any code

Gate: the latest `spec-review-*.md` in `docs/reviews/` (by name, which carries its date) must carry an `Owner decision:` line that begins `approved`. If not, stop and say so.

Read `docs/SPEC.md`, `docs/REQUIREMENTS.md`, `docs/DECISIONS.md` and the approved review in full first. Then check your own skill and tool lists against the plugins CLAUDE.md names and use the ones present for design work to set the visual direction. Record in DESIGN.md which were used and what they contributed.

## docs/PLAN.md, the what

First line `Owner decision: pending`. Then:

1. A Mermaid dependency graph of build steps 1 to 9 from SPEC section 15, showing what each step needs from the previous ones.
2. One section per step: goal in one sentence, files to create or change, tests to write, the 2 to 6 planned commits with their subjects, an hours estimate, the SPEC acceptance criteria the step closes (quoted by section and line), risks specific to that step, and the plugin skills or connectors that step will use.
3. A total hours line, the submission target from DECISIONS D19 and D23 (the morning of 8 Oct 2026 IST, full scope, the owner decides at the end on any overrun), and the order in which steps shrink if time runs short (7 and 8 first).
4. A short list of everything the owner must do by hand: host account, DNS, env secrets, demo recording, the approval lines on the planning documents.

## docs/DESIGN.md, the how

First line `Owner decision: pending`. Then, in this order:

1. Backend module design, one section per app in SPEC section 3. For each: models with fields (reference SPEC section 5, do not restate it), service and query functions as signatures with one-line contracts and the exceptions they raise, validators as a list of function names mapped to SPEC section 7 rows, serializers and views mapped to SPEC section 8 rows.
2. Import pipeline as a Mermaid sequence diagram: upload, parse, validate, stage, review actions, approve inside `transaction.atomic`, audit writes.
3. Compensation revision flow and totals computation, with the exact formulas and the Decimal quantisation rule.
4. FX design: rate lookup by date, routing through USD, `set_exchange_rate` closing the previous row, where conversion happens in the directory annotation and in the insight aggregations.
5. Seed design: structure of `seed/profiles.py`, the random stream, how determinism is guaranteed, batch sizes.
6. Frontend design: route table, component tree per page, TanStack Query key scheme, the DataGrid server-model adapter, how FilterBar state lives in URL params, formatters, error and empty states.
7. Visual direction: palette, type scale, spacing, density, chart style, with the plugin skill that produced it named. One paragraph plus a token list, no mockups.
8. Text wireframe for each of the seven pages, a dozen lines each, showing what sits where.
9. Testing design: factories, fixtures, MSW handlers, the 30-row insight fixture and its hand-computed expected values.
10. Deployment design: Dockerfile stages, entrypoint sequence, environment variables, volume path, custom domain and TLS steps for the chosen host.

Both documents describe, they do not decide. Anything the spec leaves open goes under a `Questions for the owner` heading at the end of the relevant document, not into a choice made silently. Stop after writing both and wait for the owner. `/start-step 1` refuses to run until both carry `Owner decision: approved`.
