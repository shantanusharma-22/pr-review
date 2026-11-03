# Contributing

Thanks for helping! Ground rules:

- **Standard library only**, Python 3.9+. No third-party packages in `scripts/`.
- **Every change has a test.** `python -m unittest discover -s tests -v` must pass; tests never hit the
  network (use the `Fake` transport in `tests/test_prr.py`).
- **Keep `SKILL.md` short.** It is loaded into the agent's context on every review. Put detail in
  `references/` and point to it.
- **Never log or persist credentials**, and keep everything fetched from a PR fenced as untrusted data.

## Adding a git host

1. Create `scripts/prr_lib/providers/<host>.py` with a `Provider` subclass implementing `fetch()` (return
   `new_bundle(...)` with `make_file(...)` records), `read_file()`, and optionally `checks()`,
   `load_patch()` and `post_review(bundle, plan)`.
2. Register it in `providers/__init__.py`, add URL parsing in `urls.py`, credentials in `auth.py`.
3. Add a provider test (fetch + post payload) and a row in `references/providers.md` and the README table.

## Reporting issues

Include the host (and version if self-hosted), the command, and the `### Error` block — with tokens and
private URLs removed.
