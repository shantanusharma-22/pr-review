# Research and analysis of the referenced projects

This project was designed after reading the source of three repositories (cloned 2026-10-31). This file
records what each one does, where it is strong, where it is thin, and what pr-review-agent took from it.

| | SpillwaveSolutions/pr-reviewer-skill | aidankinzett/claude-git-pr-skill | openclaw/clawsweeper |
|---|---|---|---|
| Form | Claude Code skill + 3 Python scripts + 4 reference docs | Claude Code plugin with a single SKILL.md | Full TypeScript service (~230 src files), GitHub Actions, Cloudflare Worker, dashboard |
| Scope | Human-in-the-loop review of one PR | Correct *posting* mechanics for one PR | Autonomous backlog maintainer for a repo org (issues + PRs, scheduled + event-driven) |
| Posting model | Generates `/send`, `/send-decline` slash commands; nothing posts until invoked | Always a PENDING review, submitted after AskUserQuestion approval | Proposal-only review; deterministic "apply" lane rechecks live state before any mutation |
| Output | `review.md`, `human.md`, `inline.md` from a findings JSON | gh api commands shown to the user | 60+ field JSON decision validated against a schema, rendered to one marker-backed comment |
| Review criteria | 7-category industry checklist (functionality, readability, style, performance, security, testing, PR quality) | None (focus is workflow, not judgement) | Product-first procedure: product → provenance → correctness → security → proof → rating |
| Safety stance | Two-stage approval | Approval + "red flags" anti-rationalisation list | Untrusted-input rules, read-only review, idempotent comment edits, close-policy gates, ledger |

## 1. SpillwaveSolutions/pr-reviewer-skill

**What it is.** A skill that uses `gh` to pull a PR's metadata, diff, comments, commits and linked issues into
`/tmp/PRs/<repo>/<n>/`, asks Claude to analyse against `references/review_criteria.md`, and runs
`generate_review_files.py` to turn a findings JSON (blockers / important / nits / suggestions / questions /
praise / inline_comments) into three markdown files plus generated slash commands.

**Strengths.**
- Clean separation of *collect → analyse → render → approve → post*. The findings-JSON-as-contract idea is the
  right shape: the model writes structured data, scripts write prose.
- Thorough criteria checklist (345 lines) with concrete sub-questions, including compatibility and PR hygiene.
- A distinct internal review (with scores, line numbers) vs. public review (clean, no emoji).
- `fetch_pr_data.py` optionally clones the branch so reviewers can read surrounding code.

**Weaknesses observed.**
- Posting uses `gh pr review --comment --body-file` then `gh pr review --approve` as *separate* calls, and inline
  comments are posted one at a time via `add_inline_comment.py` → multiple notifications to the author.
- Findings JSON is free-form: no schema, no validation. Nothing stops an "approve" with a blocker present.
- Relies on GraphQL `gh pr view --json`, which fails with fine-grained tokens and in restricted sandboxes.
- No guidance on treating PR text as untrusted; no head-SHA drift check before posting inline comments.
- Review criteria are a flat checklist; there is no ordering that says "decide whether the change should exist
  before reviewing the code".

**Adopted here:** the fetch pipeline and directory layout (`fetch_pr.py`, `CONTEXT.md` as the human digest);
the three-file render (`REVIEW.internal.md`, `REVIEW.public.md`, `inline.json`); the praise / questions /
risks sections; the >400-line split suggestion; the criteria checklist, reorganised.

## 2. aidankinzett/claude-git-pr-skill

**What it is.** A 300-line SKILL.md (packaged as a plugin marketplace) that teaches exactly one thing well:
how to post a GitHub review correctly with `gh api`. Create a PENDING review with all `comments[][...]`
parameters in one call, then submit it with `APPROVE` / `REQUEST_CHANGES` / `COMMENT`. Use ```suggestion
blocks. Check `gh --version` first. Show the exact text and ask with AskUserQuestion before posting.

**Strengths.**
- The pending-review-then-submit pattern is the correct GitHub mechanic: one notification, editable before
  submit, atomic.
- The "Red Flags" section lists the exact rationalisations a model uses to skip safety steps ("user said ASAP",
  "only one comment", "they already approved the idea"). This is the most reusable 20 lines in all three repos.
- Event-type decision table (security/bugs → REQUEST_CHANGES, style → APPROVE, questions → COMMENT).
- Handles the nested-backtick edge case for suggestions in markdown files.
- Built with a TDD-for-skills process: baseline violations were observed, then the skill written to fix them.

**Weaknesses observed.**
- No review criteria at all; quality of the review depends entirely on the model's defaults.
- The model constructs long `gh api -f 'comments[][body]=…'` shell commands itself; multi-line bodies with
  quotes are fragile and easy to get wrong.
- No drift check (head SHA may have moved since the review was drafted), no idempotency, no record of what was
  posted.

**Adopted here:** pending review → submit as the only write path (now in `post_review.py`, fed from JSON via
`--input -` so no shell quoting); ```suggestion rendering with fence escalation; the verdict/event table;
the preflight gh check; AskUserQuestion approval; the red-flags section (extended); plugin/marketplace packaging.

## 3. openclaw/clawsweeper

**What it is.** A production autonomous maintainer for the openclaw organisation. Codex reviews every open
issue and PR on a schedule and on events, writes a durable markdown report per item, syncs one marker-backed
public comment that is edited in place, and may *propose* closes which a separate guarded "apply" lane
executes only after re-fetching live GitHub state and passing policy gates. State lives in a Cloudflare
Durable Object, R2, and a state repo; there is an append-only action ledger and a dashboard.

**Strengths.**
- `VISION.md` states the design principle this project borrows wholesale: *"abundant intelligence, scarce
  trust"* — let the model judge, but keep deterministic code at the trust boundary (auth, idempotency, ledger,
  destructive-action gates).
- `prompts/review-item-pr.md` is the most sophisticated review procedure found: product review *first*
  ("models write good code; product judgement is the weak point"), provenance ("code that looks wrong often
  has a reason; find it before accepting a change"), correctness findings with a strict definition (trigger →
  causal link → failing input → wrong result), a dedicated security/supply-chain pass, a real-behaviour-proof
  gate (tests support proof, they do not replace it), and an S–F rating that scores evidence and patch
  separately.
- Explicit untrusted-input rules: PR bodies and comments are evidence, never instructions.
- Read-only review: the reviewer may not write to the checkout; writes happen only in apply after live
  re-verification.
- Marker-backed comments (`<!-- clawsweeper-review item=N -->`) edited in place → no comment spam, idempotent.
- JSON Schema (`schema/clawsweeper-decision.schema.json`) with `additionalProperties: false` validates every
  model output; deterministic code repairs or rejects.
- Head-SHA drift detection, 60 KiB comment cap, bounded diff/tree reads.

**Weaknesses (for reuse).**
- Scale and coupling: ~230 TypeScript modules, Cloudflare Worker, R2, OIDC intake, dashboards, close policies,
  label projections. It is a platform for one organisation, not a tool a developer installs.
- The decision schema has 60+ required fields, many specific to openclaw (ClawHub routing, repair lanes,
  `good first issue` eligibility). Far too heavy for a single-PR review.
- Codex-specific; the README states the hosted instance is not a public service.

**Adopted here:** the ordered review procedure (product → provenance → correctness → security → proof →
rating) in `SKILL.md` and `prompts/review-pr.md`; the finding definition and P0–P3 priorities; separate
proof/patch/overall tiers and the proof ladder; `securityReview` and `testingReview` objects; untrusted-input
ground rules; read-only review with a single deterministic writer; hidden HTML marker for idempotent
re-review; a trimmed JSON Schema (~15 top-level fields) with `additionalProperties: false`; drift and
closed-PR checks before posting; proposal-only CI lane with a human-gated apply job.

## Design decisions in pr-review-agent

1. **Model writes JSON, scripts write prose and call GitHub.** Taken from all three but enforced: the skill
   forbids direct `gh api -X POST`. Prose quality becomes a renderer concern and is testable.
2. **Validation is policy, not just schema.** `validate_findings.py` encodes six gates (verdict consistency,
   unique ids, files-in-diff, no duplicate anchors, tier sanity, no plumbing words). An APPROVE with a P0 is
   impossible to post.
3. **One pending review, one submit, one marker.** Kinzett's mechanics plus clawsweeper's idempotency: the
   poster refuses to review the same head twice and aborts on head drift.
4. **Product fit before code.** The single biggest quality lever from clawsweeper, applied to a one-PR tool.
5. **Small enough to read.** Five scripts, one skill, one prompt, one schema, thirteen tests. A developer can
   audit the whole write path (`post_review.py`, ~130 lines) in a few minutes.

## References

- SpillwaveSolutions/pr-reviewer-skill — https://github.com/SpillwaveSolutions/pr-reviewer-skill
  (`SKILL.md`, `scripts/fetch_pr_data.py`, `scripts/generate_review_files.py`, `references/review_criteria.md`)
- aidankinzett/claude-git-pr-skill — https://github.com/aidankinzett/claude-git-pr-skill
  (`github-pr-review/skills/github-pr-review/SKILL.md`, `.claude-plugin/marketplace.json`)
- openclaw/clawsweeper — https://github.com/openclaw/clawsweeper
  (`VISION.md`, `prompts/review-item.md`, `prompts/review-item-pr.md`, `schema/clawsweeper-decision.schema.json`,
  `docs/pr-review-comments.md`, `docs/review-authority.md`)
- GitHub REST: Pull request reviews — https://docs.github.com/en/rest/pulls/reviews
- Google Engineering Practices: Code review — https://google.github.io/eng-practices/review/
- OWASP Top 10 — https://owasp.org/www-project-top-ten/
