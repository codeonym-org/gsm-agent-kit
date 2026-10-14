# Issue tracker: GitHub

Issues and specs live in codeonym-org/gsm-agent-kit. Use the gh CLI.
Follow docs/github-workflow.md for branches, pull requests and Project tracking.

## Operations

- Create: gh issue create --repo codeonym-org/gsm-agent-kit --title "..." --body-file <file>
- Read: gh issue view <number> --repo codeonym-org/gsm-agent-kit --json number,title,body,labels,comments
- List: gh issue list --repo codeonym-org/gsm-agent-kit --state open --json number,title,body,labels
- Comment: gh issue comment <number> --repo codeonym-org/gsm-agent-kit --body-file <file>
- Label: gh issue edit <number> --repo codeonym-org/gsm-agent-kit --add-label "..."
- Remove label: use the same edit command with --remove-label.
- Close: gh issue close <number> --repo codeonym-org/gsm-agent-kit
- Track: gh project item-add 2 --owner codeonym-org --url <issue-url>

Write multiline bodies to a temporary file and pass --body-file.

When a skill says "publish to the issue tracker", create a GitHub issue.
When it says "fetch the relevant ticket", read that issue and its comments.

## Related work

Use native GitHub sub-issues and issue dependencies when supported.
Otherwise, record "Part of #<parent>" and "Blocked by: #<number>" in the
child body and maintain a task list in the parent.

## Pull requests as a triage surface

PRs as a request surface: no.
