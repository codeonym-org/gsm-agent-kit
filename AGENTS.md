# Repository context

GitHub CLI (`gh`) is installed. The user's organizations are `codeonym-oss`
for open-source projects and `codeonym-org` for personal/organization projects.
This repository belongs to `codeonym-org/gsm-agent-kit`; it is public source
with all rights reserved, not an open-source release. See LICENSE and NOTICE.

The original draft is archived in `.v0`. Use it for reference while implementing
the new workspace. Keep local secrets, device data and environments out of commits.

For GitHub changes, releases and issue tracking, read
[docs/github-workflow.md](docs/github-workflow.md). Repository automation derives
from `codeonym-oss/acli-py` and is adapted to the monorepo.

## Agent skills

### Issue tracker

Use GitHub Issues. Before ticket operations, read `docs/agents/issue-tracker.md`.

### Triage labels

Before triage, read the role mapping in `docs/agents/triage-labels.md`.

### Domain docs

Single-context layout. Before exploring domain concepts or decisions, read
`docs/agents/domain.md`.
