# gh api cheatsheet (read-only)

All review-time calls are REST `GET`. They work with fine-grained read tokens and in environments where
GraphQL (`gh pr view`, `gh pr list`) is blocked. Replace `O/R/N`.

```bash
# PR object (head sha, mergeable, draft, author_association)
gh api repos/O/R/pulls/N -X GET

# Changed files with per-file patch text and accurate line numbers
gh api repos/O/R/pulls/N/files -X GET --paginate

# Full diff
gh api repos/O/R/pulls/N -X GET -H 'Accept: application/vnd.github.v3.diff'

# Commits, conversation comments, inline review comments, prior reviews
gh api repos/O/R/pulls/N/commits -X GET --paginate
gh api repos/O/R/issues/N/comments -X GET --paginate
gh api repos/O/R/pulls/N/comments -X GET --paginate
gh api repos/O/R/pulls/N/reviews -X GET --paginate

# Check runs for the head sha
gh api repos/O/R/commits/SHA/check-runs -X GET

# A linked issue
gh api repos/O/R/issues/N -X GET

# Which PR introduced a commit (provenance)
gh api repos/O/R/commits/SHA/pulls -X GET

# Search for a possible duplicate / canonical PR
gh api -X GET search/issues -f q='repo:O/R is:pr "csv export"'

# Base-branch version of a file (policy files, pre-change behaviour)
gh api repos/O/R/contents/path/to/file -X GET -f ref=main --jq .content | base64 -d
```

## Local git, when the repo is checked out
```bash
git fetch origin pull/N/head:pr-N && git checkout pr-N
git diff origin/main...pr-N --stat
git log --format='%H %s' -- path/to/file          # who/why, works in shallow clones
git blame -L 40,60 origin/main -- path/to/file     # last edit, not introduction
```

## Writes - never run by hand
`post_review.py` is the only writer. For reference, it performs:
```
POST repos/O/R/pulls/N/reviews            {commit_id, comments[]}   -> PENDING review
POST repos/O/R/pulls/N/reviews/ID/events  {event, body}             -> submit
```
Inline comment fields: `path`, `line` (end line, new file), `side: RIGHT`, optional `start_line`/`start_side`
for ranges, `body` may contain a ```suggestion block that replaces `start_line..line` entirely. Use four
backticks when the suggestion itself contains triple backticks.
