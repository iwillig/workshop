import json

import pytest
from click.testing import CliRunner

from workshop.agent_benchmark.compare import compare_reports
from workshop.agent_benchmark.local import run_suite
from workshop.cli import cli


def review_run(root, submission="Found a defect"):
    return run_suite(
        "review-v1",
        {},
        "reviewer",
        root,
        local=True,
        execute=lambda *args: {
            "exit_status": "Submitted",
            "submission": submission,
        },
    )


def coding_run(root, solution=None):
    def execute(task, workspace, config):
        if solution:
            (workspace / "calculator.py").write_text(solution)
        return {
            "exit_status": "Submitted",
            "benchmark_usage": {"input": 10, "output": 2},
        }

    return run_suite(
        "coding-v1", {}, "coder", root, local=True, execute=execute
    )


def test_compare_flags_changed_outcomes(tmp_path):
    root = tmp_path / "private"
    first = coding_run(root, "def total(values):\n    return sum(values)\n")
    second = coding_run(root)
    comparison = compare_reports(root, first["run"]["id"], second["run"]["id"])
    assert comparison["suite"] == {
        "id": "coding-v1",
        "version": 1,
        "sha256": first["run"]["suite_sha256"],
    }
    assert comparison["runs"]["a"]["id"] == first["run"]["id"]
    assert comparison["runs"]["b"]["id"] == second["run"]["id"]
    case = comparison["cases"][0]
    assert case["case_id"] == "sum-values"
    assert case["changed"] is True
    assert case["outcome_a"] == "pass"
    assert case["outcome_b"] == "fail"
    assert comparison["changed_cases"] == 1


def test_same_outcomes_are_not_changed(tmp_path):
    root = tmp_path / "private"
    first = review_run(root)
    second = review_run(root)
    comparison = compare_reports(root, first["run"]["id"], second["run"]["id"])
    assert comparison["cases"][0]["changed"] is False
    assert comparison["changed_cases"] == 0


def test_compare_reports_usage_for_both_runs(tmp_path):
    root = tmp_path / "private"
    first = coding_run(root, "def total(values):\n    return sum(values)\n")
    second = coding_run(root)
    comparison = compare_reports(root, first["run"]["id"], second["run"]["id"])
    assert comparison["runs"]["a"]["input_tokens"] == 10
    assert comparison["runs"]["b"]["input_tokens"] == 10
    assert "delta" not in comparison["runs"]["a"]


def test_compare_includes_review_decisions_per_run(tmp_path):
    from workshop.agent_eval.reviews import record_review

    root = tmp_path / "private"
    first = review_run(root)
    second = review_run(root)
    record_review(
        root, first["run"]["id"], "average-empty", "pass", "ivan", "OK"
    )
    comparison = compare_reports(root, first["run"]["id"], second["run"]["id"])
    assert comparison["runs"]["a"]["review_counts"]["pass"] == 1
    assert comparison["runs"]["b"]["review_counts"]["pending"] == 1


def test_compare_rejects_different_suites(tmp_path):
    root = tmp_path / "private"
    first = coding_run(root)
    second = review_run(root)
    with pytest.raises(ValueError, match="suite"):
        compare_reports(root, first["run"]["id"], second["run"]["id"])


def test_compare_covers_cases_missing_from_one_run(tmp_path, monkeypatch):
    import workshop.agent_benchmark.compare as compare_module

    root = tmp_path / "private"
    first = coding_run(root, "def total(values):\n    return sum(values)\n")
    second = coding_run(root)
    report = compare_module.load_report(root, second["run"]["id"])
    report["run"]["results"] = report["run"]["results"][:0]
    storage_path = root / (second["run"]["id"] + ".json")
    storage_path.chmod(0o600)
    storage_path.write_text(json.dumps(report))
    comparison = compare_reports(root, first["run"]["id"], second["run"]["id"])
    case = comparison["cases"][0]
    assert case["outcome_a"] == "pass"
    assert case["outcome_b"] is None
    assert case["changed"] is True


def test_compare_cli_prints_comparison(tmp_path):
    root = tmp_path / "private"
    first = review_run(root)
    second = review_run(root)
    result = CliRunner().invoke(
        cli,
        [
            "benchmark",
            "compare",
            first["run"]["id"],
            second["run"]["id"],
            "--storage",
            str(root),
        ],
    )
    assert result.exit_code == 0, result.output
    comparison = json.loads(result.stdout)
    assert comparison["changed_cases"] == 0
    assert "verdict" not in comparison
