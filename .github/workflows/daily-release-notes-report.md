---
emoji: "📰"
description: Daily release notes digest from feeds listed in inventory.json
on:
  # schedule:
  #   - cron: "15 6 * * *"
  workflow_dispatch:
permissions:
  contents: read
  issues: read
  pull-requests: read
imports:
  - shared/send-google-chat.md
engine:
  id: copilot
  model: gpt-4
tools:
  github:
    mode: gh-proxy
    toolsets: [default]
network:
  allowed:
    - defaults
    - github
safe-outputs:
  mentions: false
  allowed-github-references: []
  max-bot-mentions: 1
  create-issue:
    title-prefix: "Daily Release Notes:"
    labels: [report, release-notes]
    close-older-issues: true
    expires: 30
---

# Daily Release Notes Report

## Task

Create one daily issue summarizing release notes from all feeds listed in `inventory.json`. Consider also version bumps, breaking changes, and new features. Post a summary to Google Chat with a link to the issue.

Use this report window:
- last two weeks ending at workflow start (UTC)

Process:
1. Read `inventory.json` from repository root.
2. For each item, fetch `feed_url` (RSS or Atom) and parse entries.
3. Keep only entries published in the report window.
4. Build one consolidated report issue.
5. Post a well formatted message to Google Chat with a link to the issue and a summary of the release notes, grouped by the technology.

If no entries are found in the window across all feeds, call:
- `noop("No release updates in the last two weeks (<window_start_utc> to <window_end_utc>)")`

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
- Include run reference links in this format: `[§<run_id>](https://github.com/<owner>/<repo>/actions/runs/<run_id>)`.

## Safe Outputs

- Publish the report using configured `create-issue` safe output.
- After creating the issue, call `google_chat_notify` with a required `message` input containing a concise Google Chat-ready summary and the issue URL.
- Use `noop` when there are no updates in the window.