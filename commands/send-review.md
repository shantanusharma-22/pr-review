---
description: Post the previously previewed review to GitHub after explicit approval. The only command that writes.
argument-hint: <review_dir> [APPROVE|REQUEST_CHANGES|COMMENT]
allowed-tools: Bash, Read, AskUserQuestion
---

Post the review in `$ARGUMENTS`.

1. Confirm `<review_dir>/review/PREVIEW.md` exists and the user has seen it in this conversation. If not,
   show it now.
2. Ask with AskUserQuestion: "Post this review to <owner/repo#N> as <EVENT> with <k> inline comments?"
   Options: "Yes, post it" / "No, don't post". Anything other than an explicit yes → stop, post nothing.
3. Run `python scripts/post_review.py <review_dir>/decision.json --yes` (add `--event <EVENT>` if the user
   chose an override). The script re-validates, checks for head drift, refuses closed or already-reviewed
   heads, then creates one pending review and submits it.
4. Relay the review URL from the script output, or the exact abort reason if it refused.

Never call `gh api -X POST` or `gh pr review` directly as a shortcut.
