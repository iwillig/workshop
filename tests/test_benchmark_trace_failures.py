"""Regression tests for trace capture on failure and opt-in behavior."""

import pytest

from workshop.agent_benchmark.local import run_suite
from workshop.agent_eval.storage import PrivateStorage
from workshop.agent_eval.trace import load_trace


def test_no_trace_does_not_serialize_agent(tmp_path, monkeypatch):
    class Agent:
        def run(self, task):
            return {"exit_status": "Submitted", "submission": "done"}

        def save(self, path):
            pytest.fail("A non-traced run must not serialize the agent")

    monkeypatch.setattr("workshop.agent_config.build_agent", lambda _: Agent())
    report = run_suite(
        "review-v1", {}, "reviewer", tmp_path / "private", local=True
    )
    assert report["run"]["results"][0]["outcome"] == "pending_human_review"
    assert report["run"]["trace"] is None


def test_failed_executor_still_saves_infrastructure_report(tmp_path):
    def fail(*args):
        raise RuntimeError("synthetic provider failure")

    root = tmp_path / "private"
    report = run_suite(
        "review-v1",
        {},
        "reviewer",
        root,
        local=True,
        capture_trace=True,
        execute=fail,
    )
    result = report["run"]["results"][0]
    assert result["outcome"] == "infrastructure_error"
    assert "synthetic provider failure" in result["diagnostic"]
    assert (
        PrivateStorage(root).read_json(report["run"]["id"] + ".json") == report
    )
    case = load_trace(root, report["run"]["id"])["cases"][0]
    assert case["case_id"] == result["case_id"]
    assert case["trajectory"] is None
    assert case["capture_status"] == "unavailable"


def test_failed_case_never_reuses_previous_case_trajectory(tmp_path):
    calls = 0

    def execute(*args):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("synthetic failure")
        return {
            "exit_status": "Submitted",
            "submission": "done",
            "benchmark_trajectory": {
                "messages": [{"content": f"case-{calls}"}]
            },
        }

    root = tmp_path / "private"
    report = run_suite(
        "review-v2",
        {},
        "reviewer",
        root,
        local=True,
        capture_trace=True,
        execute=execute,
    )
    assert [r["outcome"] for r in report["run"]["results"]] == [
        "pending_human_review",
        "infrastructure_error",
        "pending_human_review",
    ]
    cases = load_trace(root, report["run"]["id"])["cases"]
    assert [c["capture_status"] for c in cases] == [
        "captured",
        "unavailable",
        "captured",
    ]
    assert cases[1]["trajectory"] is None
    assert cases[0]["trajectory"]["messages"][0]["content"] == "case-1"
    assert cases[2]["trajectory"]["messages"][0]["content"] == "case-3"


def test_user_interruption_result_keeps_available_trajectory(tmp_path):
    root = tmp_path / "private"
    report = run_suite(
        "review-v1",
        {},
        "reviewer",
        root,
        local=True,
        capture_trace=True,
        execute=lambda *args: {
            "exit_status": "UserInterruption",
            "benchmark_trajectory": {"messages": [{"content": "partial"}]},
        },
    )
    assert report["run"]["results"][0]["outcome"] == "infrastructure_error"
    case = load_trace(root, report["run"]["id"])["cases"][0]
    assert case["capture_status"] == "captured"
    assert case["trajectory"]["messages"][0]["content"] == "partial"


def test_unserializable_trace_saves_infrastructure_error(tmp_path):
    root = tmp_path / "private"
    report = run_suite(
        "review-v1",
        {},
        "reviewer",
        root,
        local=True,
        capture_trace=True,
        execute=lambda *args: {
            "exit_status": "Submitted",
            "benchmark_trajectory": {"messages": [object()]},
        },
    )
    case_result = report["run"]["results"][0]
    assert case_result["outcome"] == "infrastructure_error"
    assert "trace" in case_result["diagnostic"].lower()
    case = load_trace(root, report["run"]["id"])["cases"][0]
    assert case["capture_status"] == "unavailable"
    assert case["trajectory"] is None


def test_keyboard_interrupt_propagates_and_cleans_workspace(tmp_path):
    workspaces = []

    def interrupt(task, workspace, config):
        workspaces.append(workspace)
        raise KeyboardInterrupt

    root = tmp_path / "private"
    with pytest.raises(KeyboardInterrupt):
        run_suite(
            "review-v1",
            {},
            "reviewer",
            root,
            local=True,
            capture_trace=True,
            execute=interrupt,
        )
    assert workspaces and not workspaces[0].exists()
    assert not list(root.glob("run-*.json"))
    assert not list(root.glob("trace-*.json"))
