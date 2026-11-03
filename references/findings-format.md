# findings.json

One JSON object. `prr.py validate` checks it; `render` and `post` consume it.

| field | type | required | notes |
|---|---|---|---|
| `decision` | `"approve"` \| `"comment"` \| `"request_changes"` | yes | `approve` is refused if any blocker exists. |
| `decision_reason` | string | no | One sentence shown next to the decision. |
| `summary` | string (markdown) | yes | ≤ 6 bullets describing what the patches actually do. |
| `discrepancies` | string[] | no | PR description / commit claims the patches don't support. |
| `spec_status` | `"ok"` \| `"no_spec"` | no | `no_spec` prints "Skipped: no spec" under Spec. |
| `findings` | object[] | yes (may be empty) | See below. |
| `tests` | string | no | Missing or weak tests; name files to add/update. |
| `risk` | string | no | Breaking changes, migrations, deps, config, rollout. |
| `unverified` | string[] | no | What you could not check (CI, runtime behaviour, files not reviewed). |

Each finding:

| field | type | required | notes |
|---|---|---|---|
| `axis` | `"correctness"` \| `"standards"` \| `"spec"` | yes | Never mix axes in one finding. |
| `severity` | `"blocker"` \| `"major"` \| `"minor"` \| `"nit"` \| `"question"` | yes | |
| `title` | string | yes | One line: the problem, not the fix. |
| `body` | string (markdown) | no | Failure scenario → smallest fix. For spec, quote the requirement. |
| `path` | string | no | Path in the PR's new version. Omit for PR-wide findings. |
| `line` | integer | no | New-file line number (left column of annotated patches). |
| `start_line` | integer | no | First line of a multi-line range (≤ `line`, all inside the same hunk). |
| `suggestion` | string | no | Exact replacement text for `start_line..line` (or `line`). Rendered as a suggestion block where the host supports it. |
| `rule` | string | standards: yes for blocker/major | `"CONTRIBUTING.md: use parameterized queries"`. |
| `evidence` | `"patch"` \| `"snippet"` \| `"inferred"` | recommended | Inferred findings can't be blockers. |

Findings whose `path`/`line` isn't a commentable line of the diff are kept in the summary instead of
inline — nothing is lost. A finding whose title already appears in an existing comment within two lines
of the same spot is skipped as a duplicate.

## Example

```json
{
  "decision": "request_changes",
  "decision_reason": "SQL injection on the login path.",
  "summary": "- Replaces `db.check` with a hand-built SQL query in `login()`\n- Deletes `tests/test_login.py`",
  "discrepancies": ["Commit says it only fixes login; it also deletes the login tests."],
  "spec_status": "ok",
  "findings": [
    {
      "axis": "correctness", "severity": "blocker", "evidence": "patch",
      "path": "src/auth/login.py", "line": 2,
      "title": "SQL injection: username concatenated into query",
      "body": "`user = \"' OR 1=1 --\"` matches every row. Bind the value instead.",
      "suggestion": "    row = db.execute(\"SELECT * FROM users WHERE name = ?\", (user,))"
    },
    {
      "axis": "standards", "severity": "major", "evidence": "patch",
      "path": "src/auth/login.py", "line": 1,
      "title": "New function signature has no type hints",
      "rule": "CONTRIBUTING.md: Functions must have type hints"
    },
    {
      "axis": "spec", "severity": "major", "evidence": "patch",
      "title": "Lockout after 5 failed attempts is not implemented",
      "body": "Issue #7: \"Lock the account after 5 consecutive failures.\" No counter or lockout in the diff."
    }
  ],
  "tests": "Restore tests/test_login.py and add cases for wrong password and an injection string.",
  "risk": "Auth path; exploitable before any lockout exists.",
  "unverified": ["CI status (not checked)"]
}
```
