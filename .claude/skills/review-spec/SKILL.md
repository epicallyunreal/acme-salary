---
name: review-spec
description: Entry point before development. Runs the eng-manager-spec-review subagent with no prior context over the planning documents and saves its report under docs/reviews/ for the owner to read and approve. Use on a fresh repo, after any spec change, or when the owner says "review the spec", "EM review" or "is the spec ready".
disable-model-invocation: true
---

# Review the spec before building

This is the owner's gate. Nothing is built and no planning document changes until the owner has read the report and approved it.

1. Do not read the planning documents yourself first, and do not summarise them to the agent. The point is a fresh pair of eyes with no inherited assumptions.
2. Launch `eng-manager-spec-review` with the Agent tool. The whole prompt is: "Review the planning documents in this repository as described in your instructions. Today is <today's date>. Report only."
3. Save the agent's report verbatim to `docs/reviews/spec-review-<YYYY-MM-DD>.md`. If that file exists, append `-2`, `-3` and so on. Do not edit, reorder or soften the report. Do not act on any finding.
4. Tell the owner three things only: the verdict line, the number of blocking issues, and the path of the report.
5. Stop. The owner reads the report and edits its `Owner decision:` line (line 3) to `approved` or `rework`. Changes the owner wants are made on the owner's instruction, one by one, never from the report automatically. `/start-step 1` refuses to run until an approved report exists.
