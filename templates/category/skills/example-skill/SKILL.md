---
name: example-skill
description: Say what this does and, more importantly, WHEN to reach for it — front-load the phrasings that should trigger it, and name the near-misses it should not handle. This text is all the model sees when deciding whether to load the skill, so keep it under ~700 characters or it risks truncation in the skills list.
---

# Example skill

One paragraph on what this produces and who it is for. Lead with the shape of
the output, since that is what distinguishes this skill from its neighbours.

## Workflow

1. **Do the first thing.** Keep each step an instruction, not an explanation.

2. **Run a bundled script.** Address it from the plugin root — once installed,
   the working directory is the user's project, so a relative path resolves to
   nothing:
   ```bash
   python "${CLAUDE_PLUGIN_ROOT}/skills/example-skill/scripts/do_thing.py" input.json out.html
   ```

3. **Verify, and be honest when you cannot.** If verification depends on tools
   that may be absent, preflight them and say plainly when a check did not run
   rather than implying it passed.

## Notes

- Long reference material belongs in `references/`, loaded only when needed —
  keep this file short enough to read on every invocation.
- Executable code belongs in `scripts/`.
- The `name` above must match this directory's name, or the invocation name
  changes.
