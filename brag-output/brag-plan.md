# Brag Plan: pr-review (code-review)

## What is this app?
An evidence-first, multi-agent code review skill for GitHub Copilot, Google Antigravity, Claude Code, and Cursor that systematically judges pull requests across Product Fit, Provenance, Correctness, Security, and Proof.

## The angle
Tired of superficial AI reviewers that shower PRs with sycophantic "LGTM! 🚀" comments while missing critical auth vulnerabilities and race conditions. `pr-review` acts like a battle-hardened Staff Engineer: claims in PR descriptions mean nothing without proof, findings must prove causality, and all feedback is delivered in a single, structured notification.

## Hook (first 2-3 seconds)
The uncomfortable truth every engineer recognizes: a rubber-stamped AI comment ("LGTM! 🚀") hovering over an obvious production catastrophe.

## Key moments (the middle)
- **The Defect Causal Chain**: Showing how findings are strictly structured (`Trigger + Failing Input + Wrong Result + Concrete Fix`).
- **The 5-Axis Checklist**: Step-by-step audit through Product Fit, Historical Provenance, Correctness, Security, and Verification.
- **The Proof Ladder**: Level 1 (Shipped entry-point logs + regression test) down to Level 4 (Unverified claims).

## Outro / punchline
"Stop rubber-stamping PRs. Start reviewing with proof." Supported natively in GitHub Copilot, Google Antigravity, and Claude Code. Open Source.

## User flow worth showing
1. Reviewer parses candidate pull request diff & checks provenance history (`git blame` / previous PR intent).
2. Audits against the 5-axis criteria, flagging concrete P0/P1 defects with executable fix suggestions.
3. Rates proof quality on the Proof Ladder and delivers an atomic, single-notification review verdict.

## Tone
- Preset: `cinematic` / `polished`
- Creative direction: Sleek developer-first technical film with dark obsidian aesthetic, crisp neon accents, and zero fluff.
- Interpretation: Fast, rhythmic cuts aligned to audio cues; high contrast, clean typography, readable holds.

## Format: landscape — 1920x1080
## Duration: 20.0 seconds (600 frames @ 30fps)

## Visual identity (from the project)
- Background: `#0B0F19` (Deep obsidian / slate)
- Card Surface: `#161F30` / `#1E293B`
- Primary Accent: `#6366F1` (Indigo electric)
- Success / Verified Accent: `#10B981` (Emerald green)
- Blocker / Danger Accent: `#EF4444` (Crimson red)
- Warning Accent: `#F59E0B` (Amber)
- Text Primary: `#F8FAFC`
- Text Secondary: `#94A3B8`
- Strongest visual elements: 5-Axis Checklist, Defect Finding Card, Proof Ladder staircase, Verdict Badge.

## Share copy (draft)
Most AI code reviews are polite fluff that miss critical bugs. pr-review brings cold, hard proof to GitHub Copilot, Antigravity, and Claude Code. Stop rubber-stamping: https://github.com/shantanusharma-22/pr-review

## Audio direction
- Role: Rhythmic technical electronic bed with crisp interface accents.
- Music: `happy-beats-business-moves-vol-11-by-ende-dot-app.mp3` (114.84 BPM).
- Music treatment: Starts at 0.0s, strong beat drop at 1.60s and 3.70s, continuous drive through 19.5s, clean fade out at 20.0s.
- Music cue guidance:
  - 1.60s: Hook text punch
  - 3.70s: Strong beat transition to Scene 2 (The Reveal)
  - 5.80s: Badge sequence
  - 7.91s: Transition to Scene 3 (The 5-Axis Engine)
  - 12.65s: Strong beat transition to Scene 4 (Proof Ladder)
  - 16.86s: Outro transition to Scene 5 (Verdict & Call-to-action)
- SFX posture: Subtle, tasteful UI click and whoosh sounds matched to card transitions.
- Restraint rule: No overbearing sirens, no comic sound effects; keep it high-tech, crisp, and professional.

---

## Storyboard

### Scene 1 — The Rubber-Stamp Trap — 3.7s (0.0s – 3.7s)
- **Visual**: Dark screen with dim warning grid. A glowing comment box appears:
  `"🤖 AI Reviewer: LGTM! Beautiful code! 🚀"`
  Suddenly, red warning flashes underneath:
  `"⚠️ 2 Critical Auth Leaks Merged"`
- **Sequential**: Comment box drops in (0.0 - 0.8s), settles (0.8 - 2.0s), red warning slams in (2.0 - 3.7s).
- **Audio intent**: Tension & contrast; soft synth swell leading to beat drop at 1.60s / 3.70s.
- **Transition**: Glitch wipe on beat 3.70s → Scene 2.

### Scene 2 — The Reveal: pr-review — 4.2s (3.7s – 7.9s)
- **Visual**: Glowing shield emblem `🛡️` with `pr-review`.
  Headline: `"Evidence-First Code Review for Autonomous Agents"`
  Three pill badges slide in:
  `[ 🔍 Zero Fluff ]` • `[ 🪜 Proof Ladder ]` • `[ 🎯 Single Notification ]`
- **Sequential**: Emblem & title slam in (3.7 - 4.5s), badges pop sequentially on beats 5.2s, 5.8s, 6.3s.
- **Audio intent**: Driving groove kicks in.
- **Transition**: Smooth horizontal pan at 7.91s → Scene 3.

### Scene 3 — The 5-Axis Defect Engine — 4.7s (7.9s – 12.6s)
- **Visual**: Left panel displays the 5-Axis review pipeline:
  `1. Product Fit` ➔ `2. Provenance` ➔ `3. Correctness` ➔ `4. Security` ➔ `5. Proof`
  Right panel displays the Defect Causal Chain:
  `[P0 - CRITICAL DEFECT]`
  `• Trigger: Reconnect during token swap`
  `• Wrong Result: Auth bypass & process crash`
  `• Concrete Fix: + if (isConnecting) return pending;`
- **Sequential**: Pipeline steps light up (7.9 - 9.5s), defect card expands with diff (9.5 - 12.6s).
- **Audio intent**: High-focus rhythm, subtle UI tick on each step.
- **Transition**: Snap cut on strong cue 12.65s → Scene 4.

### Scene 4 — The Proof Ladder — 4.2s (12.6s – 16.8s)
- **Visual**: The Proof Ladder hierarchy visual:
  `Level 1: Shipped Entry-Point Logs + Regression Test [TIER S / A]` (Glows Emerald)
  `Level 2: Integration Harness [TIER B]`
  `Level 3: Isolated Unit Test [TIER C]`
  `Level 4: Claims Without Proof [TIER F - BLOCKED]` (Dim Crimson)
  Punchy quote: *"PR text is a claim. Diffs and logs are proof."*
- **Sequential**: Ladder steps illuminate from bottom to top (12.6 - 15.0s), quote settles (15.0 - 16.8s).
- **Audio intent**: Uplifting harmonic progression.
- **Transition**: Fast whip wipe on beat 16.86s → Scene 5.

### Scene 5 — Verdict & Multi-Agent Launch — 3.2s (16.8s – 20.0s)
- **Visual**: Big verdict badge:
  `VERDICT: REQUEST_CHANGES ➔ FIXED ➔ APPROVED ✅`
  Headline: `"Turn AI Into Your Most Rigorous Staff Engineer"`
  Supported platform badges:
  `GitHub Copilot` • `Google Antigravity` • `Claude Code` • `Cursor`
  Repository URL: `github.com/shantanusharma-22/pr-review`
- **Sequential**: Verdict stamp lands (16.8 - 17.5s), agent logos appear (17.5 - 18.5s), hero hold & fade (18.5 - 20.0s).
- **Audio intent**: Grand resolve and clean musical tail.

**Music mood for this video:** High-energy modern electronic groove, clean and authoritative.
**Audio summary:** Starts with ironic tension, explodes into a punchy technical beat at 3.7s, drives relentlessly through evidence-first features, and finishes on an impactful open-source call to action.

