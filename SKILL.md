---
name: mattbraid-skills
description: Use this only to choose between the bundled Jira reporting skills in this library. It routes to either the sprint status grid skill or the defect lifecycle flow skill, and is not itself the right tool for generating a report directly.
---

# Skills library entrypoint

This plugin bundles two Jira reporting skills:

- `sprint-status-tracker` — use for a day-by-day sprint status grid built from
  several Jira XML/RSS export snapshots.
- `defect-lifecycle-tracker` — use for a single-export defect flow page showing
  lifecycle phase counts, priorities, deferred items and intake trend.

## Routing

1. If the request is about **how tickets moved across a sprint week**, load
   `sprint-status-tracker`.
2. If the request is about **where defects currently sit in the delivery
   lifecycle**, load `defect-lifecycle-tracker`.
3. If the request is not about one of those Jira report types, do not use this
   skill.
