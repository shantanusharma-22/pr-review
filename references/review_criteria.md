# Review Criteria

Work top to bottom. Each category lists what to look for and where the answer goes in `decision.json`.

## 0. Product fit  → `productReview`
- What does the user see change? (Not what the code does.)
- Is there a linked issue, maintainer comment, or roadmap item asking for this? Maintainer approval of the
  *direction* in the thread counts as an owner decision.
- Does a "bug fix" smuggle in a new option, default, schema, permission, or public API? → `needs_maintainer`.
- Does the diff change behaviour an area owner built deliberately? Check CODEOWNERS and history → `needs_maintainer`.
- Is every hunk serving the stated problem? Unrelated cleanup belongs in another PR (mention once in summary).
- A preference change (colours, wording, ordering) for one user's taste is never `yes` without an owner.

## 1. Provenance  → findings (`category: correctness`, title "Overrides … without reason")
- For each removed or altered existing line: `git log --format='%H %s' -- <file>`, then find the PR. Why was it
  written? Does the new PR acknowledge that reason?
- Blame shows the last edit, not the introduction. Say "appears to date to …", never "X broke it".

## 2. Correctness  → `findings`
Every finding = trigger + causal link + failing input + wrong result + smallest fix.
- Off-by-one, null/None/undefined, empty collections, boundary values, integer overflow, encoding.
- Error paths: what happens on network failure, timeout, bad input, partial write?
- Concurrency: shared state, races, missing locks, non-idempotent retries.
- Resource handling: files/connections closed, streams actually streaming, unbounded growth.
- **Existing capability**: does config, a helper, a CLI flag, an env var, or a plugin already do this? → P1,
  point at the existing path.
- **Symptom patch**: does a new try/catch, retry, guard, filter, or timeout hide the real cause? Name the input
  that still reaches it.
- **Clean cutover**: does the change remove the path it replaces, or leave two owners for one decision?
- **Upgrade safety**: a new default must not overwrite a user's stored value. Changes to config loading,
  migrations, persisted state, install/startup need fresh-install *and* upgrade evidence. P1 when setups can
  break, P2 when behaviour holds but proof is missing.
- **User-facing messages**: each says what happened and what to do next, in user terms.
- **Body claims**: anything the PR body asserts that the diff does not support.
- **Merge state**: claim a conflict only when `mergeable` is false / `mergeableState` is dirty.
- **CI**: attribute each failing required check to the diff (finding) or to an outside cause (with evidence).

## 3. Security  → `securityReview`
- Injection: SQL, shell, path, template, CSV formula, header, log.
- Auth/authz: new endpoints behind the right checks? Tenant scoping at the query root? Tokens scoped and expiring?
- Secrets: hard-coded keys, tokens in logs, `.env` committed, debug endpoints.
- Deserialisation of untrusted data; `eval`/`exec`; regexes vulnerable to catastrophic backtracking.
- **Supply chain / CI**: new dependencies and their sources, lockfile changes, unpinned GitHub Action refs
  (`@main` instead of `@sha`), `curl | sh`, new lifecycle hooks (`postinstall`), widened `permissions:` in
  workflows, secrets exposed to `pull_request_target`, downloaded artifacts executed.
- Generated, vendored, or minified files: do they match their claimed source?
- Data exposure: PII in logs, errors leaking internals, overly broad API responses.
Blocking concerns also become a P0/P1 finding with file and line.

## 4. Testing and proof  → `testingReview`
Proof ladder (strongest first): `shipped_entry_point` (real CLI/UI/API run: screenshot, recording, log, trace)
→ `in_process_harness` → `unit_only` → `none`. Tests *support* proof; they never replace it.
- Does the PR show the changed behaviour running after the fix, in the shipped entry point?
- Does a regression test fail on base and pass on head? If not shown, say so in `missingE2e`.
- Media proves only what it shows: a screenshot does not prove the console was clean.
- Low-value tests: assert only a status code, mirror the implementation, mock the thing under test, or catch no
  distinct failure. List them in `lowValueTests`.
- Changes to config, defaults, stored data, migrations, protocols need an upgrade run from the latest release.

## 5. Readability and maintainability  → at most one line in `summary`, or `risks` if it is a merge concern
- Names say what things are. Functions do one thing. Duplication is extracted. No dead code.
- These are not findings. Do not comment on formatting a linter would catch.

## 6. PR hygiene  → `summary` (one line) or `questions`
- Scope: one logical change. >400 changed lines: suggest splitting.
- Commits: messages explain why. Description matches the diff.
- Docs and changelog updated when the project requires it (base-branch AGENTS.md / CONTRIBUTING.md only).

## 7. Praise  → `praise`
Name specific things done well. It is information for the author about what to keep doing.
