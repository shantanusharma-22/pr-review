# Contributing to `pr-review`

Thank you for your interest in contributing to `pr-review`! We welcome contributions to enhance review heuristics, add domain-specific security checks, refine rating rubrics, and expand compatibility across AI coding agents.

---

## Code of Conduct

This project is governed by the [Contributor Covenant Code of Conduct](CODE_OF_CONDUCT.md). By participating, you are expected to uphold this code.

---

## How Can I Contribute?

### 1. Expanding Review Rubrics
Our review philosophy separates **judging** from **publishing**. If you have domain-specific expertise (e.g., distributed systems, iOS/Android memory safety, database migrations, cryptographic hygiene):
- Propose additions to [`references/review_criteria.md`](references/review_criteria.md).
- Ensure each criterion specifies:
  - What to look for in the patch/diff.
  - Concrete failure triggers and inputs.
  - Severity classification (P0, P1, P2, P3).

### 2. Improving Agent Compatibility
Help test and adapt the skills for:
- GitHub Copilot (`.github/skills/code-review`)
- Google Antigravity & Codex (`.agents/skills/code-review`)
- Claude Code (`.claude/skills/code-review`)
- Cursor, OpenCode, and other AI IDEs

### 3. Reporting Issues & Requesting Features
- Search existing issues before creating a new one.
- Use our [Issue Templates](.github/ISSUE_TEMPLATE/) to provide complete context.

---

## Development & Testing Workflow

1. **Fork & Clone** the repository:
   ```bash
   git clone https://github.com/shantanusharma-22/pr-review.git
   cd pr-review
   ```
2. **Create a branch** for your feature or fix:
   ```bash
   git checkout -b feature/awesome-review-rule
   ```
3. **Make your edits** to `SKILL.md` or files under `references/`.
4. **Practice What We Preach (Evidence-First PRs)**:
   When opening a Pull Request:
   - Provide concrete proof of the improvement (e.g., sample reviews demonstrating how the new rule catches a defect that was previously missed).
   - Follow the [Proof Ladder](references/rating_rubric.md): claims without verifiable diffs or outputs will be scrutinized!
5. **Commit & Push**:
   ```bash
   git commit -m "feat(rubric): add concurrency race checks for async streams"
   git push origin feature/awesome-review-rule
   ```
6. **Open a Pull Request** against `main`.

---

## Ground Rules for Contributions

- **Findings are defects, not taste**: We do not add subjective aesthetic rules or naming preferences. Rules must target correctness, security, provenance, or verifiable performance flaws.
- **Progressive Disclosure**: Keep core `SKILL.md` files concise and focused on instructions and flow. Deep reference material belongs in `references/`.
- **Maintain Multi-Agent Parity**: Changes made to root skills should be reflected across agent directories (`.github/`, `.agents/`, `code-review/`).

Thank you for helping build the future of rigorous, evidence-first code reviews!
