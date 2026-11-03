# Smell baseline (Standards axis)

Applies even when a repo documents nothing. Two rules bind it:

- **The repo wins.** A documented repo standard overrides any smell here; if the repo endorses a pattern,
  don't flag it.
- **Always a judgement call.** Report as "possible <smell>", severity `minor` or `nit`, never blocker.
  Flag only what the diff introduces or clearly worsens, and skip anything a linter/formatter enforces.

Names follow Fowler's *Refactoring* (ch. 3), adapted so they read sensibly in functional, procedural and
object-oriented code. Format: what it looks like → usual fix.

| Smell | What it looks like in a diff | Usual fix |
|---|---|---|
| Mysterious name | A name that doesn't say what the thing does or holds (`data2`, `handle`, `tmp`, `doIt`). | Rename; if no honest name exists, the design is unclear. |
| Duplicated logic | The same shape of logic in two hunks or files of this change. | Extract once, call from both. |
| Long function | A function the diff grows past easy reading, doing several things in sequence. | Extract the steps into named functions. |
| Long parameter list / data clump | The same 3+ values passed together repeatedly. | Bundle them into one type/record. |
| Primitive obsession | A string/number standing in for a domain concept (IDs, money, status codes) with validation scattered around. | Give the concept a small type or enum. |
| Repeated switches | The same `switch`/`if` cascade on the same value in several places. | One lookup table or polymorphic dispatch. |
| Feature envy | Code that mostly reads another module's or object's data. | Move it next to that data. |
| Shotgun surgery | One logical change forces scattered edits across many files. | Gather what changes together. |
| Divergent change | One file edited for several unrelated reasons in this PR. | Split responsibilities (or split the PR). |
| Speculative generality | Parameters, hooks, flags or abstractions no caller or spec needs yet. | Delete; inline until a real need appears. |
| Message chains | Long `a.b().c().d()` navigation that couples the caller to a structure. | Hide the walk behind one function. |
| Middle man | A wrapper that only forwards calls. | Call the real target directly. |
| Mutable shared data | Globals or shared objects mutated from several places. | Encapsulate; pass values; restrict writers. |
| Dead code | Unused functions, params, branches or commented-out code added or left behind. | Delete it. |
| Comments as deodorant | A comment explaining confusing code instead of the code being made clear. | Rename/extract so the comment isn't needed; keep comments that explain *why*. |
| Refused bequest | A subclass/implementer that ignores or overrides most of what it inherits. | Prefer composition. |
