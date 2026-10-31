# Copilot Code Review Skill: `code-review` + `references`

An evidence-first GitHub Copilot skill and workflow designed to automate and elevate Pull Request reviews.

It replaces superficial AI feedback with rigorous multi-phase inspection: **Product Fit → Provenance → Correctness → Security → Proof → Rating**.

---

## Repository Structure

```
├── .github/
│   ├── copilot-instructions.md            # Native GitHub Copilot instruction prompt for PR reviews
│   └── skills/
│       └── code-review/
│           ├── SKILL.md                   # Agent Skill definition for GitHub Copilot
│           └── references/                # Modular review rubrics & criteria
│               ├── gh_api_cheatsheet.md
│               ├── rating_rubric.md
│               └── review_criteria.md
├── code-review/
│   ├── SKILL.md                           # Skill entry point
│   └── references/                        # Skill references
│       ├── gh_api_cheatsheet.md
│       ├── rating_rubric.md
│       └── review_criteria.md
├── references/                            # Top-level review documentation & rubrics
│   ├── gh_api_cheatsheet.md               # GitHub CLI & REST API inspection commands
│   ├── rating_rubric.md                   # S-to-F rating scale and proof ladder
│   └── review_criteria.md                 # 5-axis detailed review checklist
├── SKILL.md                               # Root skill definition
└── README.md
```

---

## Key Features

1. **Evidence-First Judging**: The review evaluates the actual patch and verifiable proof, treating PR titles and descriptions as claims to verify.
2. **Deterministic Severities**:
   - `P0`: Outages, data corruption, severe vulnerabilities (blocks merge).
   - `P1`: Logic flaws, broken error handling, regressions (blocks merge).
   - `P2`: Performance defects, missing edge case tests (requires resolution/discussion).
   - `P3`: Minor cleanups and non-blocking notes.
3. **Proof Ladder**: Scores verification quality from Level 1 (shipped entry-point logs/media + regression tests) down to Level 4 (no proof).
4. **Single-Notification Reviews**: Feedback is grouped atomically to eliminate comment fatigue.

---

## How to Use

### 1. In GitHub Repositories (GitHub Copilot PR Reviews)
- Copy `.github/copilot-instructions.md` and `.github/skills/code-review` into your target repository.
- GitHub Copilot will automatically apply the review criteria and rating rubric to pull requests.

### 2. In GitHub Copilot Chat & Agents
In Copilot Chat or any agent environment supporting Agent Skills:
```
@copilot review this pull request diff using the code-review skill
```

---

## References

- [`references/review_criteria.md`](references/review_criteria.md): Full 5-axis review checklist.
- [`references/rating_rubric.md`](references/rating_rubric.md): Tiering system (S, A, B, C, D, F) and proof ladder.
- [`references/gh_api_cheatsheet.md`](references/gh_api_cheatsheet.md): Read-only GitHub API commands for inspecting diffs, checks, and provenance.
