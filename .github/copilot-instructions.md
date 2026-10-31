# GitHub Copilot Code Review Instructions

When reviewing pull requests in this repository or operating as an AI code reviewer, adhere strictly to the following review procedure and criteria:

## Core Review Guidelines

1. **Follow the Evidence-First Methodology**:
   - Always consult the full review criteria in `references/review_criteria.md` and the rating rubric in `references/rating_rubric.md`.
   - Treat the PR title and description as author claims, not verification. Look at the actual diff, test outputs, and behavior.

2. **Phase-by-Phase Assessment**:
   - **Product Fit**: Confirm the change addresses a recognized issue without smuggling in unapproved architectural shifts or breaking changes.
   - **Provenance**: Inspect whether modified or deleted code was placed there for a specific reason in past commits.
   - **Correctness**: Flag concrete defects with trigger, failing input, wrong result, and suggested fix.
   - **Security**: Explicitly check for injections, authorization flaws, hardcoded credentials, and unsafe third-party packages or CI workflows.
   - **Proof**: Verify whether real entry-point execution or automated tests prove the change works and prevents regressions.

3. **Severity & Decision Rules**:
   - Classify findings as `P0` (Critical), `P1` (High), `P2` (Medium), or `P3` (Low).
   - If any `P0` or `P1` issue is present, or if critical proof is missing, the verdict must be **REQUEST_CHANGES**.
   - If all checks pass and changes are verified with tests, provide an **APPROVE** verdict with an overall tier rating (S through C).
   - If feedback consists only of open questions or lacks context, provide a **COMMENT** verdict.

4. **Feedback Quality**:
   - Consolidate all findings into a single, structured review.
   - Separate objective correctness/security defects from optional stylistic suggestions.
   - Be constructive, precise, and polite.
