#!/usr/bin/env bash
# preflight.sh - verify the environment before any review work starts.
# Exit 0 only when gh is installed, authenticated, and python deps are present.
set -u
ok=1
if ! command -v gh >/dev/null 2>&1; then
  echo "FAIL gh CLI not installed. https://cli.github.com  (macOS: brew install gh | Windows: winget install GitHub.cli)"; ok=0
else
  echo "ok   gh $(gh --version | head -1 | awk '{print $3}')"
  if gh auth status >/dev/null 2>&1; then echo "ok   gh authenticated"; else echo "FAIL gh not authenticated. Run: gh auth login"; ok=0; fi
fi
if command -v python3 >/dev/null 2>&1; then
  echo "ok   python $(python3 -c 'import sys;print(".".join(map(str,sys.version_info[:3])))')"
  python3 -c "import jsonschema" 2>/dev/null && echo "ok   jsonschema" || echo "warn jsonschema missing (pip install jsonschema) - schema validation will be skipped"
else
  echo "FAIL python3 not found"; ok=0
fi
[ "$ok" = 1 ] && { echo "preflight passed"; exit 0; } || { echo "preflight FAILED - stop, do not review"; exit 1; }
