---
name: Feature / Rule Proposal
about: Suggest an idea or new review criterion for this project
title: '[FEAT] '
labels: enhancement
assignees: ''
---

## Proposal Summary
A clear and concise description of the review rule, agent platform adapter, or criterion you are proposing.

## Problem Statement
What common defect, security hole, or architectural trap does this new rule prevent?

## Proposed Severity Classification
- [ ] `P0 - Critical` (Security vulnerability, data loss, remote code execution)
- [ ] `P1 - High` (Logical correctness bug on valid input, broken recovery)
- [ ] `P2 - Medium` (Performance defect, missing edge test, mild regression)
- [ ] `P3 - Low` (Non-blocking cleanup or minor risk)

## Example Scenario
**Failing Input / Trigger Code:**
```ts
// code snippet illustrating the defect
```

**Proposed Agent Finding Output:**
> **Trigger**: ...
> **Failing Input**: ...
> **Wrong Result**: ...
> **Proposed Fix**: ...

