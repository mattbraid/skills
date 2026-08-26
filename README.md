# Skills Library

A personal library of AI skills created in Claude, ChatGPT, and other AI tools.

## What is a Skill?

A **skill** is a reusable prompt, workflow, or instruction set that you've crafted for a specific task. This library stores them in a consistent format so they're easy to find, copy, and reuse.

## Directory Structure

```
skills/
├── README.md               # This file
├── INDEX.md                # Full list of all skills
└── skills/
    ├── examples/           # Example skills to show the format
    │   └── summarize.md
    └── <category>/         # Your skill categories (writing, coding, research, …)
        └── <skill-name>.md
```

## Adding a Skill

1. Pick (or create) a category folder under `skills/`.
2. Create a new Markdown file named after the skill, e.g. `skills/writing/rewrite-formal.md`.
3. Fill in the template:

```markdown
# Skill Title

**Source:** Claude / ChatGPT / Gemini / …  
**Category:** writing / coding / research / …  
**Tags:** tag1, tag2

## Purpose

One-sentence description of what this skill does.

## Prompt / Instructions

\```
Paste the exact prompt or instructions here.
\```

## Example Input

> Paste a sample input here.

## Example Output

Paste the expected output here.

## Notes

Any caveats, model-specific tips, or version notes.
```

4. Add an entry to [INDEX.md](INDEX.md).

## Index

See [INDEX.md](INDEX.md) for the full list of skills.