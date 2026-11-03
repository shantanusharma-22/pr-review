# Correctness & risk triggers

A trigger list, not a form. Raise an item only when the diff gives you a concrete reason. Generic advice
("consider adding more tests") is noise; name the input, the failure and the fix.

## Logic and errors
- Off-by-one, inverted conditions, wrong operator precedence, integer overflow/division, float equality.
- Null/None/undefined, empty collections, zero, negative, very large, unicode, timezone/DST boundaries.
- Errors swallowed, logged-and-continued, or turned into success; missing cleanup on the error path
  (files, locks, transactions, sockets); `finally`/`defer` ordering.
- Changed function behaviour with callers outside the diff — fetch one caller with `snippet` before
  claiming breakage.

## Security
- Injection: SQL/NoSQL/LDAP built by string concatenation, shell commands from input, template injection,
  `eval`/dynamic import, unsafe deserialization (pickle, YAML load, Java serialization).
- Web: XSS (unescaped output, `dangerouslySetInnerHTML`, `v-html`), CSRF on state-changing routes,
  open redirects, SSRF (server fetches a user-supplied URL), path traversal in file access, CORS `*` with
  credentials.
- AuthN/AuthZ: new route or handler without the existing auth check, object access without an ownership
  check (IDOR), role checks on the client only, tokens in URLs or logs, non-constant-time secret compares.
- Secrets or credentials committed; PII written to logs or analytics; weak crypto (MD5/SHA1 for passwords,
  ECB, static IVs, `Math.random` for tokens).

## Concurrency and state
- Check-then-act races, shared mutable state across requests/threads, missing locks or locks held across
  I/O, `async` functions not awaited, blocking calls on an event loop.
- Retries without idempotency (double charges, duplicate emails); caches without invalidation.

## Data, APIs and dependencies
- Migrations: irreversible or locking operations on large tables, NOT NULL without default/backfill,
  dropping or renaming columns still read by the running version (deploy order).
- Public contract changes: removed/renamed fields, changed defaults, status codes, event schemas, CLI
  flags, config keys — without versioning or a migration note.
- New dependencies: necessary? maintained? licence compatible? name typo-squat? Version pinned the way the
  repo pins others? Lockfile updated consistently with the manifest?
- Performance on hot paths: N+1 queries, unbounded loops or loads, missing pagination, large allocations,
  synchronous I/O in request paths.

## Tests and docs
- New or changed logic with no test that would fail without it; tests deleted or weakened (assertions
  removed, `skip`, broadened mocks).
- Tests that pass trivially (asserting on the mock, no assertion, sleeping instead of waiting).
- User-visible behaviour, config or API changes without README/changelog/migration notes.

## Agent / LLM orchestration code
Only when the diff touches agents, tool calling, planners, queues of model calls, or memory.
- Every loop or retry has a hard bound (iterations, time or budget); "until good enough" is unbounded.
- One owner per task and per piece of state; workers return results, one place writes canonical state.
  Parallel workers must not share a writable checkout, file or JSON blob.
- Joins say what they wait for (all, quorum, first *valid* — not first finished) and what happens to late,
  duplicate or failed branches; cancellation reaches child tasks.
- Side effects (emails, payments, writes) use idempotency keys so a retry can't repeat them.
- Model output is validated (schema + sanity) before it changes state or triggers effects; tool inputs
  built from model output are treated as untrusted (injection, path traversal, SSRF).
- Prompts and tool results that include user or web content are marked as data; secrets never enter
  prompts or logs.
- Correctness state is not stored only in a model-written summary or a vector store.
