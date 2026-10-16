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

## Wayfinding operations

Wayfinder maps and decision tickets use native GitHub sub-issues and blocking
relationships. Their only labels are `wayfinder:map` on maps and one of
`wayfinder:grilling`, `wayfinder:research`, `wayfinder:prototype`, or
`wayfinder:task` on decisions. The existing roadmap issues remain separate
implementation handoff items.

The current map is
[Chart the first-release GSM Agent Kit architecture](https://github.com/codeonym-org/gsm-agent-kit/issues/11).

- Attach children: `gh issue edit <map> --repo codeonym-org/gsm-agent-kit --add-sub-issue <child>,<child>`.
- Add dependencies: `gh issue edit <child> --repo codeonym-org/gsm-agent-kit --add-blocked-by <blocker>,<blocker>`.
- Inspect relationships: `gh issue view <issue> --repo codeonym-org/gsm-agent-kit --json title,body,labels,assignees,parent,subIssues,blockedBy`.
- Claim before work: `gh issue edit <child> --repo codeonym-org/gsm-agent-kit --add-assignee @me`.
- Resolve: post the answer with `gh issue comment ... --body-file <file>`, close
  the decision, then append its linked title and one-line gist to the map's
  Decisions so far. Fetch the latest map body before editing it.

For the frontier, query the map's children with `gh api graphql`, requesting
`state`, `assignees.totalCount` and `blockedBy.nodes.state`. A child is takeable
when open, unassigned, and every blocker is closed. Preserve native child
ordering when choosing the first takeable decision. Follow both child and
blocker pagination; an incomplete result cannot establish that a ticket is
unblocked.

```graphql
query($owner: String!, $repo: String!, $map: Int!, $cursor: String) {
  repository(owner: $owner, name: $repo) {
    issue(number: $map) {
      subIssues(first: 100, after: $cursor) {
        pageInfo { hasNextPage endCursor }
        nodes {
          number title url state
          assignees(first: 1) { totalCount }
          blockedBy(first: 100) {
            pageInfo { hasNextPage endCursor }
            nodes { number title state }
          }
        }
      }
    }
  }
}
```

Map bodies index resolved decisions; open decisions are queried through native
children. Assign research tickets before dispatching their agents. Research
findings live on throwaway `research/<name>` branches and are linked from
resolution comments; those branches have no PR and are never merged. Charting
creates the map and launches research. Human decision tickets remain open for
their own sessions.

## Pull requests as a triage surface

PRs as a request surface: no.
