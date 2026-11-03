# Providers

Tokens are read from environment variables (or the host's own CLI login) and sent only to that host's
API. Public repositories can usually be reviewed without a token; posting always needs one.

| Host | URL forms | Credentials (first found wins) | Read scope | Post scope |
|---|---|---|---|---|
| GitHub.com | `github.com/o/r/pull/N`, `o/r#N` | `GH_TOKEN`, `GITHUB_TOKEN`, `gh auth login` | Pull requests: read, Contents: read | Pull requests: write |
| GitHub Enterprise Server | `ghe.corp/o/r/pull/N` | `GH_ENTERPRISE_TOKEN`, `GITHUB_ENTERPRISE_TOKEN`, then the above, `gh auth login --hostname` | same | same |
| GitLab.com / self-managed | `host/group[/sub]/proj/-/merge_requests/N`, `group/proj!N --provider gitlab` | `GITLAB_TOKEN`, `GL_TOKEN`, `glab auth login`, `CI_JOB_TOKEN` (limited) | `read_api` | `api` |
| Bitbucket Cloud | `bitbucket.org/ws/repo/pull-requests/N` | `BITBUCKET_ACCESS_TOKEN` (bearer), or `BITBUCKET_EMAIL` + `BITBUCKET_API_TOKEN` (app passwords: `BITBUCKET_USERNAME` + `BITBUCKET_APP_PASSWORD`) | Pull requests: read, Repositories: read | Pull requests: write |
| Azure DevOps Services | `dev.azure.com/org/proj/_git/repo/pullrequest/N`, `org.visualstudio.com/…` | `AZURE_DEVOPS_PAT`, `AZURE_DEVOPS_EXT_PAT`, `SYSTEM_ACCESSTOKEN` (Pipelines) | Code: Read, Work Items: Read | Code: Read & write |
| Gitea / Forgejo / Codeberg | `host/o/r/pulls/N` | `GITEA_TOKEN`, `FORGEJO_TOKEN`, `CODEBERG_TOKEN` | repository: read, issue: read | repository: write |
| Anything else | local checkout | none (uses your git remote auth) | — | — (render only) |

Overrides: `--provider` when a self-hosted host name doesn't reveal the product; `--api-url` for unusual
API locations or proxies (e.g. `--api-url https://git.corp/gitlab/api/v4`); `--host` for `o/r#N` on
GitHub Enterprise.

## How each host is handled

**GitHub** — files, review comments, issue comments, reviews, commits, and same-repo issues referenced as
`#N`, `fixes #N` or full issue URLs. Merge base comes from the compare API. Posting creates one review
(single notification) with inline comments and suggestion blocks; multi-line comments use
`start_line`. If you try to approve or request changes on your own PR, it falls back to a comment.

**GitLab** — diffs (paginated `/diffs`, falling back to `/changes` on old versions), discussions incl.
resolved state, commits, issues the MR closes plus `#N` references. Posting uses draft notes published in
one batch, falling back to individual discussions on versions without draft notes. Inline positions carry
the MR's `diff_refs`; context lines include `old_line`. `request_changes` is posted as a comment headed
"Changes requested" (GitLab has no universal API for that state); `approve` calls the approve endpoint.

**Bitbucket Cloud** — the unified diff, comments (inline and general), commits. Jira keys in title and
commits are listed for you to fetch with a Jira tool. Posting creates inline comments, a summary comment,
then approve or request-changes. Suggestions render as plain code blocks.

**Azure DevOps** — Azure has no unified-diff API, so the tool reads the latest iteration's changes and
builds diffs from file contents at the iteration's common (merge-base) commit and the source commit. For
PRs over 60 files those diffs are deferred and fetched on demand by `patch`. Linked work items
(description and acceptance criteria) become spec sources. Posting creates one thread per inline comment
plus a summary thread, and sets your vote: approve = 10, request changes = −5 ("waiting for author"), comment = no vote.

**Gitea / Forgejo** — the `.diff` endpoint, issue comments, reviews and review comments, commits, `#N`
issues. Posting creates one review (APPROVED / REQUEST_CHANGES / COMMENT) with inline comments.

## Local mode (any host, forks, uncommitted work)

```sh
prr.py collect --local --base main                    # branch vs main (merge base)
prr.py collect --local --base main --head WORKTREE    # include uncommitted tracked changes
prr.py collect --local --base origin/main --fetch-ref <ref>
```

Useful `--fetch-ref` values for reviewing someone else's PR from your clone:

| Host | ref |
|---|---|
| GitHub, Gitea/Forgejo | `refs/pull/<N>/head` |
| GitLab | `refs/merge-requests/<N>/head` |
| Bitbucket Data Center / Server | `refs/pull-requests/<N>/from` |
| Azure DevOps | `refs/pull/<N>/merge` (then diff against the target branch) |
| Gerrit | `refs/changes/<last-2-digits>/<change>/<patchset>` |

Local mode has no PR description, discussion or linked issues; pass `--spec path.md` (repeatable) when a
spec exists. It cannot post — use `render` and paste the result.

## Troubleshooting

- Exit code 3 with HTTP 401/403 → token missing, expired, or lacking scope; HTTP 404 on a private repo
  usually means the same thing.
- `patch` shows "[no textual patch]" → binary, too large for the host's API, or a pure rename.
- Inline comment rejected by the host → the line isn't part of the diff; `validate` normally catches this
  and moves the finding into the summary.
- Corporate proxy → standard `HTTPS_PROXY` / `NO_PROXY` environment variables are honoured.
