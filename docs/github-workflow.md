# GitHub workflow

Repository: https://github.com/codeonym-org/gsm-agent-kit

Project: https://github.com/orgs/codeonym-org/projects/2

The repository is public source with all rights reserved. Public visibility does
not grant an open-source license. Original project code is covered by LICENSE;
adapted third-party automation retains the notices listed in NOTICE.

## Changes

Create a GitHub issue before starting a feature. Add it to the linked Project,
with an Area and Priority. Status progresses through Backlog, Todo, In Progress,
In Review and Done. Use `<type>/<issue>-<slug>` branches and conventional commits.
PR titles end with the issue number, for example `feat: define capabilities (#2)`.
Link the issue in the PR body. Mark work Done when its acceptance criteria pass.

Main requires a PR, resolved review threads, linear history and the checks
`ci-ok`, `branch-name`, `commits`, and `pr-title`. Only squash merges are enabled;
merged branches are deleted. Administrators can bypass through a PR, matching
acli-py. Release tags matching `v*` are immutable.

## Automation

The workflows, conventions and templates originate from codeonym-oss/acli-py.
CI is adapted to the 13-package workspace and Python 3.13+, with Linux,
macOS and Windows package/import checks. Modem hardware is not required in CI.
Build checks validate all wheels and source distributions and their metadata.
Behavior tests cover the implemented device-inspection slice and run without
hardware. New implementations must add corresponding behavioral coverage.

Dependabot groups weekly GitHub Actions and uv updates. Issue forms and PR
templates keep real phone numbers, SMS contents, SIM identifiers and credentials
out of public reports. Secret scanning and push protection are enabled where
GitHub permits them.

Release-please is scaffolded with synchronized workspace versions, but disabled
by `ENABLE_RELEASES=false` until the maintainer chooses a first release.
Future independent package release policies can replace this initial policy.
Registry publishing is absent and `PUBLISH_TO_PYPI=false`. No publishing secrets
or trusted publishers are copied from acli-py. A future RELEASE_PLEASE_TOKEN can
enable checks on automated release PRs; the default GITHUB_TOKEN does not trigger
those checks automatically.

The Project is public and linked to this repository. Add each new issue using
`gh project item-add 2 --owner codeonym-org --url <issue-url>`. Automatic addition
of future issues requires a Project auto-add workflow; repository linkage alone
does not enable it.
