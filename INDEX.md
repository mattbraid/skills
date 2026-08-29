# Skills Index

Every skill lives in a plugin under `plugins/<plugin>/skills/`. Install a plugin to get all of its skills — see [README.md](README.md#install).

| Skill | Plugin | Description |
|-------|--------|-------------|
| [sprint-status-tracker](plugins/jira/skills/sprint-status-tracker/SKILL.md) | `jira` | One-page sprint status grid built from several dated Jira XML exports, showing how each ticket moved day by day across the week |
| [defect-lifecycle-tracker](plugins/jira/skills/defect-lifecycle-tracker/SKILL.md) | `jira` | One-page defect flow view from a single Jira XML export — KPI strip, counts by lifecycle phase, deferred panel, intake heatmap |

---

_Add a row whenever you add a skill, and bump the owning plugin's `version` in both `plugins/<plugin>/.claude-plugin/plugin.json` and `.codex-plugin/plugin.json`._
