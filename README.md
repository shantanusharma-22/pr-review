# pr-review

An open-source agent skill for reviewing pull requests on **any git host** with **any coding agent** that
supports the `SKILL.md` format — and as a plain CLI for everything else.

It reviews a change on three separate axes, anchors every finding to a line it actually saw, and never
posts anything until you say yes.

```
You:   review https://gitlab.com/acme/api/-/merge_requests/482
Agent: collects the MR → reviews correctness, standards, spec → shows findings + decision
You:   post it
Agent: posts one batched review with inline comments and suggestions
```

## Why another review skill?

Most review prompts either dump a generic checklist on the model (lots of tokens, vague comments) or only
work with one host. This one combines the parts that work best:

- **Three axes, kept apart** — *correctness & risk*, the repo's *own standards*, and the *spec*/linked
  issue. Optional parallel sub-agents, each with a fresh context, so one axis can't mask another.
- **Evidence over opinion** — the review is built from the patches; claims in the PR description are
  checked against the code and mismatches are reported. Patches are printed with new-file line numbers,
  so inline comments land on the right line.
- **Token-disciplined** — one call collects everything; big PRs are triaged by a risk score (auth,
  migrations, CI, dependencies, public API…) and only the riskiest files are fetched. Lockfiles, generated
  and binary files are listed, not dumped.
- **Safe by default** — PR text, comments and code are treated as untrusted data (prompt-injection aware);
  standards files are read from the merge base so a PR can't rewrite its own rules; posting is a dry run
  until `--confirm`; `--no-approve` for CI; approval with a blocker is refused.
- **Plays well with humans** — reads existing discussion and skips points already raised, batches
  comments into one review, and supports incremental re-reviews via a hidden marker.
- **Zero dependencies** — Python 3.9+ standard library and git. Nothing to `pip install`.

## Supported git hosts

| Host | Collect | Linked spec | Post inline | Suggestions | Approve / request changes |
|---|---|---|---|---|---|
| GitHub.com & Enterprise Server | ✅ | issues (`#N`, URLs) | ✅ one batched review | ✅ | ✅ / ✅ |
| GitLab.com & self-managed | ✅ | closing issues + `#N` | ✅ batched draft notes | ✅ | ✅ / comment |
| Bitbucket Cloud | ✅ | Jira keys listed | ✅ | code block | ✅ / ✅ |
| Azure DevOps (incl. visualstudio.com) | ✅ | linked work items | ✅ | ✅ | vote 10 / −5 |
| Gitea, Forgejo, Codeberg | ✅ | issues (`#N`) | ✅ one batched review | code block | ✅ / ✅ |
| Any other host (Gerrit, Bitbucket DC, …), local branches, uncommitted work | ✅ local mode | `--spec` files | render only | — | — |

Setup and token scopes per host: [references/providers.md](references/providers.md).

## Supported agents

The skill follows the open [Agent Skills](https://agentskills.io) format (`SKILL.md` + `scripts/` +
`references/`) and uses no agent-specific features: sub-agents are optional, there are no slash commands,
and all tooling is a single Python CLI.

- **Claude Code** — copy or clone into `~/.claude/skills/pr-review` (all projects) or
  `.claude/skills/pr-review` (one repo).
- **Claude apps** — zip the folder and upload it as a custom skill in settings (posting and private
  repos need the sandbox to reach your git host).
- **Codex, Gemini CLI, Cursor, GitHub Copilot, OpenCode, Pi and other skill-aware agents** — install with
  the cross-agent installer `npx skills add shantanusharma-22/pr-review`, or copy the folder into that agent's
  skills directory (see its docs).
- **Agents without skill support** — reference `SKILL.md` from your `AGENTS.md`/rules file, or paste it as
  instructions; the CLI works the same.

## Quick start

```sh
git clone https://github.com/shantanusharma-22/pr-review ~/.claude/skills/pr-review   # or your agent's dir
export GH_TOKEN=...            # or GITLAB_TOKEN, AZURE_DEVOPS_PAT, BITBUCKET_API_TOKEN, GITEA_TOKEN
```

Then ask your agent: *"review https://github.com/acme/api/pull/42"*, *"review my branch against main"*,
or *"is MR !17 ready to merge?"*.

### Using the CLI directly

```sh
S=~/.claude/skills/pr-review/scripts/prr.py
python $S collect https://github.com/acme/api/pull/42      # prints digest, writes workspace
python $S collect 42                                        # infer host from `origin`
python $S collect --local --base main --head WORKTREE       # local + uncommitted changes
python $S patch    -w <ws> src/auth/login.py                # annotated patch for chosen files
python $S snippet  -w <ws> src/auth/login.py:40-90          # context lines (add --at base for old)
python $S checks   -w <ws>                                  # CI status of the head commit
python $S validate -w <ws> findings.json                    # schema + decision rules + anchoring
python $S render   -w <ws> findings.json                    # markdown review (no network)
python $S post     -w <ws> findings.json                    # dry run
python $S post     -w <ws> findings.json --confirm          # actually post
```

Exit codes: `0` ok · `2` usage · `3` auth/network/preflight · `4` invalid findings.
Budget knobs: `--max-files` / `--max-lines` or `PR_REVIEW_MAX_FILES` / `PR_REVIEW_MAX_LINES`
(defaults 25 / 1000).

### Repo-specific review rules

Put review guidance for your project in `.pr-review.md` (or `.github/pr-review.md`, `REVIEW.md`). It is
picked up with `CONTRIBUTING.md`, `AGENTS.md`, `CLAUDE.md`, `.cursor/rules`, ADRs and similar files, and
used by the Standards axis. Linter and formatter configs are detected so the review skips what tooling
already enforces.

### Running in CI

Any agent that can run headless can use the skill in a pipeline. Recommended guard rails: a read-mostly
token, `PR_REVIEW_NO_APPROVE=1`, and posting only as a comment.

## Security model

- Tokens come from environment variables or the host's CLI, are sent only to that host, and are dropped on
  cross-host redirects. They are never written to the workspace or printed.
- Everything fetched from the PR is data, not instructions; the digest fences it in `UNTRUSTED` markers.
- The skill never checks out and runs PR code.
- Writes happen only through `post --confirm`.

## Development

```sh
python -m unittest discover -s tests -v
```

Tests use a fake HTTP transport for every provider plus an end-to-end local-git test; no network needed.
See [CONTRIBUTING.md](CONTRIBUTING.md) for adding a provider.

## Credits

Design informed by prior open-source review skills.

## License

[MIT](LICENSE)
