# pr-review-agent

Evidence-first GitHub pull request review for Claude Code. The model judges; deterministic scripts
validate, render, and post. Nothing reaches GitHub until a human has seen the exact text and said yes.

```
 fetch_pr.py ──► model review ──► decision.json ──► validate_findings.py ──► render_review.py ──► PREVIEW.md
  (read-only)      (read-only)      (schema)          (6 policy gates)         (public/internal/inline)   │
                                                                                                          ▼
                                                                                             human approves
                                                                                                          │
                                                                                                          ▼
                                                                                  post_review.py  (the ONLY writer)
                                                                        re-validate → drift check → idempotency check
                                                                        → one PENDING review → submit with event
```

Built after studying three projects — see [ANALYSIS.md](ANALYSIS.md) for the comparison and what was taken
from each:

- **SpillwaveSolutions/pr-reviewer-skill** — collect → analyse → render → approve pipeline, criteria checklist
- **aidankinzett/claude-git-pr-skill** — pending-review batching, ```suggestion blocks, approval gate, red flags
- **openclaw/clawsweeper** — product-first procedure, untrusted-input rules, schema-validated decisions,
  proof gate, S–F rating, marker-backed idempotent comments, "abundant intelligence, scarce trust"

## What a review looks like

The model fills `decision.json` ([schema](schema/review-decision.schema.json), [worked example](tests/fixtures/sample_decision.json)):

| Field | Decided |
|---|---|
| `productReview` | Should this change exist? `yes` / `no` / `needs_maintainer` — decided **before** reading code |
| `findings[]` | Discrete defects only: trigger → failing input → wrong result → fix. P0–P3. Optional `suggestion` code |
| `securityReview` | Dedicated pass: injection, auth, secrets, supply chain, CI workflows |
| `testingReview` | Proof ladder: shipped entry point › harness › unit-only › none. Tests support proof, never replace it |
| `rating` | Proof tier / patch tier / overall tier, S–F. Rates evidence and patch, never the person |
| `verdict` | `APPROVE` / `REQUEST_CHANGES` / `COMMENT` — the validator forces REQUEST_CHANGES on any P0/P1 |

The renderer produces a public review body (hidden marker, no scores, no emoji), an internal review (with
confidence scores), and the exact `comments[]` payload. See the sample output in
[`tests/fixtures`](tests/fixtures/) by running the quick start below.

## Install

Requirements: Python 3.10+, [GitHub CLI](https://cli.github.com) authenticated (`gh auth login`), `pip install jsonschema`.

**As a Claude Code plugin**
```
/plugin marketplace add <your-org>/pr-review-agent
/plugin install pr-review-agent
```

**Manually**
```bash
git clone <this repo> ~/.claude/skills/pr-review-agent
# or project-local:  git clone <this repo> .claude/skills/pr-review-agent
```

## Use

In Claude Code:
```
/review-pr https://github.com/owner/repo/pull/123      # fetch, review, validate, show PREVIEW.md
/send-review .pr-review/owner__repo/123                # asks once more, then posts one batched review
```
or just say "review PR #123" — the skill triggers on PR URLs and review requests.

From the shell, without Claude:
```bash
bash scripts/preflight.sh
DIR=$(python scripts/fetch_pr.py owner/repo#123)
# ... write $DIR/decision.json (by hand, or with any model + prompts/review-pr.md) ...
python scripts/validate_findings.py $DIR/decision.json --files $DIR/files.json
python scripts/render_review.py $DIR/decision.json
cat $DIR/review/PREVIEW.md
python scripts/post_review.py $DIR/decision.json              # type "yes" to post
python scripts/post_review.py $DIR/decision.json --event COMMENT   # soften the verdict at post time
```

Quick start on the fixture (no network):
```bash
pip install -r requirements.txt
python -m pytest tests/ -q
python scripts/render_review.py tests/fixtures/sample_decision.json --out /tmp/demo && cat /tmp/demo/PREVIEW.md
```

## Safety properties

| Property | Enforced by |
|---|---|
| Review is read-only | SKILL.md ground rules; subagent has no write tools; prompt forbids writes |
| PR text cannot steer the review | Untrusted-input banner in `CONTEXT.md`; prompt rules; `process` finding for steering attempts |
| No APPROVE with a blocker | `validate_findings.py` gate G1 (also: blocking security concern, missing proof, `worthIt: no`) |
| Line numbers point into the diff | gate G3 (`--files`) |
| Human sees exactly what is posted | `PREVIEW.md` + AskUserQuestion + typed `yes` in `post_review.py` |
| One notification, not N | single PENDING review with all `comments[]`, then one submit |
| No stale inline comments | `post_review.py` aborts if head SHA moved since review |
| No duplicate reviews | hidden `<!-- pr-review-agent item=N head=SHA -->` marker checked before posting |
| Auditable | `posted.json` receipt; the write path is one ~130-line script |

## Layout

```
.claude-plugin/        plugin.json, marketplace.json
skills/pr-review-agent/SKILL.md          the procedure Claude follows
  references/          review_criteria.md, rating_rubric.md, gh_api_cheatsheet.md
commands/              /review-pr, /send-review
agents/pr-reviewer.md  read-only subagent for large diffs
prompts/review-pr.md   long-form model prompt (subagent / CI / other models)
schema/                review-decision.schema.json
scripts/               preflight.sh, fetch_pr.py, validate_findings.py, render_review.py, post_review.py
tests/                 pytest suite + sample_decision.json fixture
.github/workflows/     proposal-only CI lane with a human-gated post job
ANALYSIS.md            research on the three source projects
```

## CI

`.github/workflows/pr-review.yml` runs fetch → validate → render on every PR with read-only permissions and
uploads `PREVIEW.md` as an artifact. The model step is a placeholder for your runner. Posting is a separate
manual job behind a protected environment. Pin action refs to SHAs before enabling.

## Roadmap

- Re-review mode: diff the new decision against the prior marker-backed review, resolve fixed threads.
- GitLab / Bitbucket posters behind the same `inline.json` contract.
- Repository profiles (`.pr-review-agent.yml`) for per-repo proof requirements and protected paths.

MIT licensed. See [ANALYSIS.md](ANALYSIS.md) for attribution of ideas to the three source projects.
