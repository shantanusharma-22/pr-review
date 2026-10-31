# Rating Rubric

Rate the **evidence** (`proofTier`) and the **patch** (`patchTier`) separately, then combine into `overallTier`.
Most PRs are B or C. Rating the contributor is never the point.

| Tier | Proof | Patch |
|---|---|---|
| **S** | Real media/logs of the exact changed behaviour through the shipped entry point, plus a regression test shown failing on base and passing on head. Rare. | Smallest complete fix, removes what it replaces, no findings, no low-value tests, upgrade story proven. Rare. |
| **A** | Shipped-entry-point proof of the changed scenario. | Correct, no open finding, no low-value tests, `worthIt: yes`. |
| **B** | Harness or well-targeted tests that exercise the real production owner. | Worth merging, correct, one or two P3s or minor risks. |
| **C** | Unit-only, or proof of a neighbouring scenario rather than the changed one. | Useful but limited confidence: P2 findings, thin upgrade story, or product fit unclear. |
| **D** | Claims without evidence; tests that would pass with the bug present. | Thin implementation signal: P1 findings, or `needs_maintainer` on the core direction. |
| **F** | No proof where proof is required. | Not ready: P0, serious correctness/safety defect, or `worthIt: no`. |
| **NA** | Docs-only or non-code change. | — |

Rules
- Harness-only or unit-only proof rarely rates above C.
- `overallTier` can be at most one step above the lower of proof/patch (validator gate G5).
- An open P0/P1 caps `overallTier` at C or below.
- `worthIt: needs_maintainer` or `no` caps `overallTier` at C.
- Workflow state (draft, labels, pending CI) never lowers a tier. Missing proof does.
- Low-value tests weigh a patch down without blocking merge.

Verdict mapping is in SKILL.md; the validator enforces that any P0/P1, blocking security concern, or missing
required proof produces `REQUEST_CHANGES`.
