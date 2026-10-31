"""Offline tests: validation gates and rendering. Run with `python -m pytest tests/`."""
import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "sample_decision.json").read_text())

sys.path.insert(0, str(SCRIPTS))
import render_review as rr  # noqa: E402
import validate_findings as vf  # noqa: E402


def run_validate(decision: dict, tmp_path: Path, *extra: str) -> subprocess.CompletedProcess:
    p = tmp_path / "decision.json"
    p.write_text(json.dumps(decision))
    return subprocess.run([sys.executable, str(SCRIPTS / "validate_findings.py"), str(p), *extra], capture_output=True, text=True)


def test_fixture_is_valid(tmp_path):
    r = run_validate(FIXTURE, tmp_path)
    assert r.returncode == 0, r.stderr
    assert "verdict=REQUEST_CHANGES" in r.stdout


def test_schema_rejects_unknown_field(tmp_path):
    d = copy.deepcopy(FIXTURE)
    d["extra"] = 1
    r = run_validate(d, tmp_path)
    assert r.returncode == 1 and "schema" in r.stderr


def test_g1_p0_forbids_approve(tmp_path):
    d = copy.deepcopy(FIXTURE)
    d["verdict"] = "APPROVE"
    r = run_validate(d, tmp_path)
    assert r.returncode == 1 and "G1" in r.stderr


def test_g1_fix_downgrades_verdict(tmp_path):
    d = copy.deepcopy(FIXTURE)
    d["verdict"] = "APPROVE"
    r = run_validate(d, tmp_path, "--fix")
    assert r.returncode == 0, r.stderr
    assert "REQUEST_CHANGES" in r.stderr  # fixed: line
    assert json.loads((tmp_path / "decision.json").read_text())["verdict"] == "REQUEST_CHANGES"


def test_g1_needs_maintainer_blocks_approve(tmp_path):
    d = copy.deepcopy(FIXTURE)
    d["findings"] = []
    d["securityReview"] = {"status": "cleared", "summary": "", "concerns": []}
    d["testingReview"]["proofStatus"] = "sufficient"
    d["rating"] = {"proofTier": "B", "patchTier": "B", "overallTier": "B", "rationale": "x"}
    d["productReview"]["worthIt"] = "needs_maintainer"
    d["inlineComments"] = []
    d["verdict"] = "APPROVE"
    r = run_validate(d, tmp_path)
    assert r.returncode == 1 and "worthIt" in r.stderr


def test_g3_file_not_in_diff(tmp_path):
    files = tmp_path / "files.json"
    files.write_text(json.dumps([{"filename": "README.md"}]))
    r = run_validate(FIXTURE, tmp_path, "--files", str(files))
    assert r.returncode == 1 and "G3" in r.stderr


def test_g4_duplicate_inline_anchor(tmp_path):
    d = copy.deepcopy(FIXTURE)
    d["inlineComments"].append({"file": "app/invoices/export.py", "line": 42, "body": "dup"})
    r = run_validate(d, tmp_path)
    assert r.returncode == 1 and "G4" in r.stderr


def test_g5_tier_sanity(tmp_path):
    d = copy.deepcopy(FIXTURE)
    d["rating"]["overallTier"] = "A"
    r = run_validate(d, tmp_path)
    assert r.returncode == 1 and "G5" in r.stderr


def test_render_public_has_marker_and_no_scores():
    body = rr.render_public(FIXTURE)
    assert body.startswith("<!-- pr-review-agent item=482 head=9f3c2a1b7e4d v=1 -->")
    assert "confidence 0." not in body  # internal-only
    assert "### Blockers" in body and "SQL built by concatenating" in body
    assert "Requesting changes" in body


def test_render_inline_payload_shape():
    payload = rr.render_inline_payload(FIXTURE)
    assert len(payload) == 4  # 3 findings + 1 extra inline
    f1 = payload[0]
    assert f1["path"] == "app/invoices/export.py" and f1["line"] == 42 and f1["start_line"] == 41
    assert "```suggestion" in f1["body"]
    assert "suggestion" not in payload[1]["body"].split("```")[0] or "```suggestion" not in payload[1]["body"]  # F2 has null suggestion


def test_suggestion_fence_escalates_for_nested_backticks():
    s = rr.fence_suggestion("```js\nx\n```")
    assert s.startswith("````suggestion")


def test_render_cli_writes_four_files(tmp_path):
    p = tmp_path / "decision.json"
    p.write_text(json.dumps(FIXTURE))
    r = subprocess.run([sys.executable, str(SCRIPTS / "render_review.py"), str(p)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    for name in ("REVIEW.public.md", "REVIEW.internal.md", "inline.json", "PREVIEW.md"):
        assert (tmp_path / "review" / name).exists()
    assert "nothing has been posted" in (tmp_path / "review" / "PREVIEW.md").read_text()


def test_fetch_parse_ref():
    sys.path.insert(0, str(SCRIPTS))
    import fetch_pr
    assert fetch_pr.parse_ref("https://github.com/a/b/pull/12") == ("a", "b", 12)
    assert fetch_pr.parse_ref("https://github.com/a/b.git/pull/12") == ("a", "b", 12)
    assert fetch_pr.parse_ref("a/b#7") == ("a", "b", 7)
    with pytest.raises(SystemExit):
        fetch_pr.parse_ref("nope")
