# Skills Index

Skills are grouped into categories, and each category is a separately installable plugin. Install one with `/plugin install <category>@skills-library` — see [README.md](README.md#install).

## jira

One-page, client-facing Jira reports built from XML/RSS exports.

| Skill | Description |
|-------|-------------|
| [sprint-status-tracker](plugins/jira/skills/sprint-status-tracker/SKILL.md) | One-page sprint status grid built from several dated Jira XML exports, showing how each ticket moved day by day across the week |
| [defect-lifecycle-tracker](plugins/jira/skills/defect-lifecycle-tracker/SKILL.md) | One-page defect flow view from a single Jira XML export — KPI strip, counts by lifecycle phase, deferred panel, intake heatmap |

---

_Adding a skill: add its row under the right category and bump that category's `version` in both its `plugin.json` and its `marketplace.json` entry. Adding a category: give it its own `##` section here — see [Adding a Category](README.md#adding-a-category)._
