---
description: Review a GitHub pull request end to end (fetch → analyse → validate → preview). Posts nothing.
argument-hint: <pr_url | owner/repo#N>
allowed-tools: Bash, Read, Write, Edit, Grep, Glob, AskUserQuestion
---

Review the pull request `$ARGUMENTS` using the pr-review-agent skill.

1. Run `bash scripts/preflight.sh`; stop and relay instructions if it fails.
2. Run `python scripts/fetch_pr.py $ARGUMENTS` and note the review directory it prints.
3. Perform the review following `skills/pr-review-agent/SKILL.md` (product → provenance → correctness →
   security → proof → rating). If the diff is large (>400 changed lines or >15 files), delegate the analysis
   to the `pr-reviewer` subagent and wait for the decision.json path.
4. Validate: `python scripts/validate_findings.py <dir>/decision.json --files <dir>/files.json`.
5. Render: `python scripts/render_review.py <dir>/decision.json`.
6. Show the user the full contents of `<dir>/review/PREVIEW.md` and ask whether to post, change the event
   type, edit, or stop. Do NOT post in this command; posting happens via `/send-review`.
