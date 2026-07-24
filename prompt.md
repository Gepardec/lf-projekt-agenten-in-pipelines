# Daily Release Notes Report

## Task
Summarize the release notes.

## Output Requirements

Use GitHub-flavored Markdown.

Structure:
- `### Overview`
- `### Breaking Changes`
- `### New Features`
- `### Feed Summaries`
- `### References`

Rules:
- Use `###` for sections and `####` for subsections.
- Keep critical items visible and place long details in `<details><summary>...</summary>` blocks.
- In `### Breaking Changes`, include only items explicitly marked as breaking, incompatible, migration-required, or equivalent wording. If none, state that clearly.
- In `### New Features`, include net-new capabilities and enhancements.
- In `### Feed Summaries`, group by feed `name` from `inventory.json`.
- Include source links for each summarized release entry.
