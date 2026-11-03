import json

import pytest
from click.testing import CliRunner

from workshop.agent_benchmark.local import run_suite
from workshop.agent_eval.reviews import load_report, record_review
from workshop.agent_eval.storage import PrivateStorage
from workshop.cli import cli


def review_run(root):
    return run_suite(
        "review-v1",
        {},
        "reviewer",
        root,
        local=True,
        execute=lambda *args: {
            "exit_status": "Submitted",
            "submission": "bug",
        },
    )


def test_reviews_are_attributable_and_preserve_run(tmp_path):
    root = tmp_path / "private"
    report = review_run(root)
    run_id = report["run"]["id"]
    first = record_review(
        root, run_id, "average-empty", "fail", "Alice", "Missed bug"
    )
    second = record_review(
        root, run_id, "average-empty", "pass", "Bob", "Found bug"
    )
    assert first["id"] != second["id"]
    assert first["suite_sha256"] == report["run"]["suite_sha256"]
    assert PrivateStorage(root).read_json(run_id + ".json") == report
    enriched = load_report(root, run_id)
    assert len(enriched["reviews"]) == 2
    assert enriched["review_counts"]["pass"] == 1
    assert enriched["review_counts"]["pending"] == 0
    assert enriched["run"]["results"][0]["outcome"] == "pending_human_review"


def test_pending_and_inconclusive_are_not_passes(tmp_path):
    root = tmp_path / "private"
    run_id = review_run(root)["run"]["id"]
    assert load_report(root, run_id)["review_counts"]["pending"] == 1
    record_review(root, run_id, "average-empty", "inconclusive", "A", "Unsure")
    counts = load_report(root, run_id)["review_counts"]
    assert counts["inconclusive"] == 1 and counts["pass"] == 0


def test_reject_invalid_review_before_writing(tmp_path):
    root = tmp_path / "private"
    run_id = review_run(root)["run"]["id"]
    for case, decision, reviewer, rationale in [
        ("missing", "pass", "A", "OK"),
        ("average-empty", "maybe", "A", "OK"),
        ("average-empty", "pass", " ", "OK"),
        ("average-empty", "pass", "A", " "),
    ]:
        with pytest.raises(ValueError):
            record_review(root, run_id, case, decision, reviewer, rationale)
    assert len(list(root.glob("review-*.json"))) == 0


def test_review_command_and_report(tmp_path):
    root = tmp_path / "private"
    run_id = review_run(root)["run"]["id"]
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "benchmark",
            "review",
            run_id,
            "--case",
            "average-empty",
            "--decision",
            "pass",
            "--reviewer",
            "A",
            "--rationale",
            "Found it",
            "--storage",
            str(root),
        ],
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["decision"] == "pass"
    result = runner.invoke(
        cli, ["benchmark", "report", run_id, "--storage", str(root)]
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["review_counts"]["pass"] == 1
