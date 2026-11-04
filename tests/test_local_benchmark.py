import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from workshop.agent_benchmark.local import load_suite, run_suite
from workshop.agent_eval.storage import PrivateStorage
from workshop.cli import cli


def test_bundled_suites_validate():
    for name in ("coding-v1", "review-v1"):
        suite = load_suite(name)
        assert suite.suite.id == name
        assert len(suite.cases) == 1


def test_suite_fingerprints_remain_stable():
    assert load_suite("coding-v1").sha256 == (
        "1581dfca2daa6805af28cc20807fda85247c9527d72d087d85f088336850cc16"
    )
    assert load_suite("review-v1").sha256 == (
        "fb992407bff77273457fa70571f5f52a368bdf0f19a73121b223cd3ceb680de2"
    )
    assert load_suite("coding-v2").sha256 == (
        "d4c10a708fd790c7c734176e2bb040c356fb57b857f3d3bdc87a2780886a7289"
    )
    assert load_suite("review-v2").sha256 == (
        "876752d7e4b998ac3c49527307a9e59ebbbec9a194c54fe9d29c19a077068170"
    )
    assert load_suite("coding-v3").sha256 == (
        "460efc81efd975739b3fde7b8c6e25e279079da51c468b4d34bbc6ae1af4d1db"
    )
    assert load_suite("review-v3").sha256 == (
        "e278d1cb2ddfdacb8c4c7d5cb5e806f84c66e272b5f07571624900cd94450aa5"
    )


def test_v3_suite_has_six_cases_with_new_failure_modes():
    for name, role in (("coding-v3", "coding"), ("review-v3", "review")):
        suite = load_suite(name)
        assert suite.suite.id == name
        assert suite.suite.version == 3
        assert len(suite.cases) == 6
        identifiers = [entry.case.id for entry in suite.cases]
        assert len(identifiers) == len(set(identifiers))
        expected = {
            "coding": [
                "sum-values",
                "normalize-text",
                "clamp-range",
                "leap-year-rules",
                "mean-uses-total",
                "flatten-one-level",
            ],
            "review": [
                "average-empty",
                "discount-percent",
                "shared-cache",
                "input-mutation",
                "swallowed-errors",
                "page-boundary",
            ],
        }[role]
        assert identifiers == expected


def test_v3_scores_cases_independently(tmp_path):
    def execute(task, workspace, config):
        years = workspace / "years.py"
        if years.exists():
            years.write_text(
                "def is_leap_year(year):\n"
                "    return year % 4 == 0 and ("
                "year % 100 != 0 or year % 400 == 0)\n"
            )
        return {"exit_status": "Submitted"}

    result = run_suite(
        "coding-v3",
        {},
        "coder",
        tmp_path / "private",
        local=True,
        execute=execute,
    )
    outcomes = {
        case["case_id"]: case["outcome"] for case in result["run"]["results"]
    }
    assert outcomes["leap-year-rules"] == "pass"
    assert sum(value == "fail" for value in outcomes.values()) == 5


def test_v3_rejects_changed_fixture(tmp_path, monkeypatch):
    import shutil
    import workshop.agent_benchmark.local as local

    shutil.copytree(local._ROOT / "fixtures", tmp_path / "fixtures")
    shutil.copytree(local._ROOT / "checks", tmp_path / "checks")
    (tmp_path / "fixtures" / "review-pages" / "pages.py").write_text("changed")
    monkeypatch.setattr(local, "_ROOT", tmp_path)
    with pytest.raises(ValueError, match="Fixture hash mismatch"):
        load_suite("review-v3")


def test_v2_suite_has_three_independent_multifile_cases(tmp_path):
    for name in ("coding-v2", "review-v2"):
        suite = load_suite(name)
        assert len(suite.cases) == 3
        seen = []

        def execute(task, workspace, config):
            seen.append(
                (task, workspace, sorted(p.name for p in workspace.iterdir()))
            )
            return {"exit_status": "Submitted", "submission": "review"}

        report = run_suite(
            name, {}, "agent", tmp_path / name, local=True, execute=execute
        )
        assert len(report["run"]["results"]) == 3
        assert len({str(workspace) for _, workspace, _ in seen}) == 3
        assert all(not workspace.exists() for _, workspace, _ in seen)
        assert any(len(names) > 1 for _, _, names in seen)
        expected = "fail" if name == "coding-v2" else "pending_human_review"
        assert report["counts"][expected] == 3


def test_v2_scores_each_coding_case_independently(tmp_path):
    def execute(task, workspace, config):
        if (workspace / "calculator.py").exists():
            (workspace / "calculator.py").write_text(
                "def total(values):\n    return sum(values)\n"
            )
        elif (workspace / "text.py").exists():
            (workspace / "text.py").write_text(
                "def normalize(value):\n    return value.strip().lower()\n"
            )
        return {"exit_status": "Submitted"}

    result = run_suite(
        "coding-v2",
        {},
        "coder",
        tmp_path / "private",
        local=True,
        execute=execute,
    )
    assert [case["outcome"] for case in result["run"]["results"]] == [
        "pass",
        "pass",
        "fail",
    ]


def test_v2_rejects_changed_scorer(tmp_path, monkeypatch):
    import shutil
    import workshop.agent_benchmark.local as local

    shutil.copytree(local._ROOT / "fixtures", tmp_path / "fixtures")
    shutil.copytree(local._ROOT / "checks", tmp_path / "checks")
    (tmp_path / "checks" / "coding-normalize.py").write_text("changed")
    monkeypatch.setattr(local, "_ROOT", tmp_path)
    with pytest.raises(ValueError, match="Scoring hash mismatch"):
        load_suite("coding-v2")


def test_coding_run_uses_copy_and_stores_result(tmp_path):
    original = load_suite("coding-v1").cases[0].fixture / "calculator.py"
    before = original.read_text()

    def execute(task, workspace, config):
        assert "total" in task
        (workspace / "calculator.py").write_text(
            "def total(values):\n    return sum(values)\n"
        )
        return {"exit_status": "Submitted", "submission": "Done"}

    result = run_suite(
        "coding-v1",
        {},
        "coder",
        tmp_path / "records",
        local=True,
        execute=execute,
    )
    assert result["run"]["results"][0]["outcome"] == "pass"
    assert result["counts"]["pass"] == 1
    assert original.read_text() == before
    assert (
        PrivateStorage(tmp_path / "records").read_json(
            result["run"]["id"] + ".json"
        )
        == result
    )


def test_review_run_is_pending_and_keeps_findings(tmp_path):
    result = run_suite(
        "review-v1",
        {},
        "reviewer",
        tmp_path / "records",
        local=True,
        execute=lambda *args: {
            "exit_status": "Submitted",
            "submission": "Found a defect",
        },
    )
    assert result["run"]["results"][0]["outcome"] == "pending_human_review"
    assert result["details"][0]["findings"] == "Found a defect"


def test_failures_are_not_passes(tmp_path):
    failed = run_suite(
        "coding-v1",
        {},
        "coder",
        tmp_path / "records",
        local=True,
        execute=lambda *args: {"exit_status": "Submitted"},
    )
    assert failed["run"]["results"][0]["outcome"] == "fail"
    broken = run_suite(
        "coding-v1",
        {},
        "coder",
        tmp_path / "records",
        local=True,
        execute=lambda *args: {"exit_status": "Error"},
    )
    assert broken["run"]["results"][0]["outcome"] == "infrastructure_error"


def test_cleanup_warning_is_infrastructure_error(tmp_path):
    report = run_suite(
        "coding-v1",
        {},
        "coder",
        tmp_path / "records",
        local=True,
        execute=lambda *args: {
            "exit_status": "Submitted",
            "cleanup_warning": "cleanup failed",
        },
    )
    assert report["run"]["results"][0]["outcome"] == "infrastructure_error"


def test_local_acknowledgement_is_required(tmp_path):
    with pytest.raises(ValueError, match="local"):
        run_suite("coding-v1", {}, "coder", tmp_path / "records")
    assert not (tmp_path / "records").exists()


def test_cli_runs_configured_agent_with_fixture_workspace(
    tmp_path, monkeypatch
):
    config = tmp_path / "agents.yaml"
    config.write_text(
        "agents:\n  coder:\n    model:\n      model_name: fake-model\n"
    )
    captured = {}

    class Agent:
        progress_sink = None

        def run(self, task):
            self.progress_sink("Working")
            workspace = captured["config"]["environment"]["cwd"]
            Path(workspace, "calculator.py").write_text(
                "def total(values):\n    return sum(values)\n"
            )
            return {"exit_status": "Submitted"}

    def build(config):
        captured["config"] = config
        return Agent()

    monkeypatch.setattr("workshop.agent_config.build_agent", build)
    result = CliRunner().invoke(
        cli,
        [
            "benchmark",
            "run",
            "--suite",
            "coding-v1",
            "--config",
            str(config),
            "--agent",
            "coder",
            "--storage",
            str(tmp_path / "private"),
            "--local",
        ],
    )
    assert result.exit_code == 0, result.output
    report = json.loads(result.stdout)
    assert report["run"]["results"][0]["outcome"] == "pass"
    assert report["model"] == "fake-model"
    assert "not isolated" in result.stderr
    assert "Working" in result.stderr
    assert captured["config"]["agent"]["step_limit"] == 20
    assert not Path(captured["config"]["environment"]["cwd"]).exists()


def test_report_cli_reads_private_record(tmp_path):
    root = tmp_path / "records"
    report = run_suite(
        "review-v1",
        {},
        "reviewer",
        root,
        local=True,
        execute=lambda *args: {"exit_status": "Submitted"},
    )
    result = CliRunner().invoke(
        cli,
        ["benchmark", "report", report["run"]["id"], "--storage", str(root)],
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["run"] == report["run"]


def test_invalid_agent_id_is_rejected_before_execution(tmp_path):
    def execute(*args):
        pytest.fail("agent must not execute")

    with pytest.raises(ValueError):
        run_suite(
            "coding-v1",
            {},
            "bad/id",
            tmp_path / "records",
            local=True,
            execute=execute,
        )


def test_executor_exception_is_infrastructure_error(tmp_path):
    def execute(*args):
        raise TimeoutError("model timed out")

    report = run_suite(
        "coding-v1",
        {},
        "coder",
        tmp_path / "records",
        local=True,
        execute=execute,
    )
    case = report["run"]["results"][0]
    assert case["outcome"] == "infrastructure_error"
    assert "TimeoutError" in case["diagnostic"]


def test_modified_fixture_fails_validation(tmp_path, monkeypatch):
    import shutil

    import workshop.agent_benchmark.local as local

    shutil.copytree(local._ROOT / "fixtures", tmp_path / "fixtures")
    shutil.copytree(local._ROOT / "checks", tmp_path / "checks")
    (tmp_path / "fixtures" / "coding" / "calculator.py").write_text("changed")
    monkeypatch.setattr(local, "_ROOT", tmp_path)
    with pytest.raises(ValueError, match="Fixture hash mismatch"):
        load_suite("coding-v1")


def test_scoring_timeout_is_infrastructure_error(tmp_path, monkeypatch):
    import subprocess

    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired("check", 30)

    monkeypatch.setattr(
        "workshop.agent_benchmark.local.subprocess.run", timeout
    )
    result = run_suite(
        "coding-v1",
        {},
        "coder",
        tmp_path / "private",
        local=True,
        execute=lambda *args: {"exit_status": "Submitted"},
    )
    assert result["run"]["results"][0]["outcome"] == "infrastructure_error"


def test_unknown_suite_is_rejected():
    with pytest.raises(ValueError, match="suite"):
        load_suite("not-a-suite")
