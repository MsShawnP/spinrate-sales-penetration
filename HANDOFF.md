# Handoff — Spinrate Sales Penetration

## Current phase

Scaffolding complete. No code written yet.

## What exists

- `quadrant-brainstorm.md` — full brainstorm with business question, core construction, inputs/outputs, Cinderhaven angle
- Git repo initialized, .gitignore covers secrets and data files
- README follows Lailara template
- State files created (PLAN, HANDOFF, DECISIONS, FAILURES)

## What's next

1. Confirm project tier (Medium vs Heavy)
2. Run `/clarify` to nail down requirements
3. Choose tech stack — brainstorm says "interactive dashboard" so need to decide React vs Dash vs something else
4. Design data model — depends on tool #1 (doormath-sales-penetration?) outputs

## Key context

- Builds on "tool #1" which provides ACV%, door counts by item — check doormath-sales-penetration for schema
- SPPD (sales per point of distribution) is the velocity metric — brainstorm notes it's "the most commonly miscalculated metric in the building"
- Cinderhaven synthetic data needs deliberate protagonist items: one star, one hidden gem, one wide-but-dead, one question mark
- Chart conventions carry over from UCI work (palette constants, coord_cartesian, labeled medians)
