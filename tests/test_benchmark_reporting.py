import json

import pytest
from click.testing import CliRunner

from workshop.agent_benchmark.local import execute_agent, run_suite
from workshop.agent_eval.storage import PrivateStorage
from workshop.cli import cli


@pytest.mark.parametrize(
    ("messages", "calls", "expected"),
    [
        (
            [
                {"extra": {"usage": {"input": 10, "output": 3}}},
                {"extra": {"usage": {"input": 5, "output": 4}}},
            ],
            2,
            {"input": 15, "output": 7},
        ),
        (
            [{"extra": {"usage": {"input": 0, "output": 2}}}],
            1,
            {"input": 0, "output": 2},
        ),
        (
            [
                {"extra": {"usage": {"input": 10, "output": 3}}},
                {"extra": {"usage": {"input": None, "output": 4}}},
            ],
            2,
            {"input": None, "output": 7},
        ),
        (
            [{"extra": {"usage": {"input": 10, "output": 3}}}],
            2,
            {"input": None, "output": None},
        ),
        (
            [{"extra": {"usage": {"input": True, "output": -1}}}],
            1,
            {"input": None, "output": None},
        ),
        ([], 0, {"input": None, "output": None}),
    ],
)
def test_adapter_collects_only_complete_reported_usage(
    tmp_path, monkeypatch, messages, calls, expected
):
    class Agent:
        n_calls = calls

        def __init__(self):
            self.messages = messages

        def run(self, task):
            return {"exit_status": "Submitted", "submission": "done"}

    monkeypatch.setattr(
        "workshop.agent_config.build_agent", lambda config: Agent()
    )
    result = execute_agent("task", tmp_path, {})
    assert result["benchmark_usage"] == expected


def test_real_agent_adapter_collects_multiturn_provider_usage(
    tmp_path, monkeypatch
):
    import llm

    class Response:
        def __init__(self, first):
            self.first = first

        def text(self):
            return "" if self.first else "Found the defect"

        def tool_calls(self):
            return (
                [
                    llm.ToolCall(
                        name="read",
                        arguments={"path": "calculator.py"},
                        tool_call_id="read-1",
                    )
                ]
                if self.first
                else []
            )

        def usage(self):
            return type("Usage", (), {"input": 11, "output": 4})()

    class Conversation:
        def __init__(self):
            self.responses = []

        def prompt(self, prompt, **kwargs):
            response = Response(not self.responses)
            self.responses.append(response)
            return response

    class Backend:
        def conversation(self):
            return Conversation()

    monkeypatch.setattr(
        "workshop.agent.models.llm.get_model", lambda _: Backend()
    )
    report = run_suite(
        "review-v1",
        {
            "agent": {"agent_class": "default"},
            "model": {"protocol": "native", "retry_attempts": 1},
        },
        "reviewer",
        tmp_path / "private",
        local=True,
    )
    assert report["run"]["results"][0]["outcome"] == "pending_human_review"
    assert report["run"]["input_tokens"] == 22
    assert report["run"]["output_tokens"] == 8
    assert report["run"]["cost"] is None


def test_suite_saves_usage_totals_and_leaves_cost_unknown(tmp_path):
    uses = iter(
        [
            {"input": 10, "output": 3},
            {"input": 20, "output": 4},
            {"input": 0, "output": 5},
        ]
    )
    report = run_suite(
        "review-v2",
        {},
        "reviewer",
        tmp_path / "private",
        local=True,
        execute=lambda *args: {
            "exit_status": "Submitted",
            "benchmark_usage": next(uses),
        },
    )
    assert report["run"]["input_tokens"] == 30
    assert report["run"]["output_tokens"] == 12
    assert report["run"]["cost"] is None
    assert (
        PrivateStorage(tmp_path / "private").read_json(
            report["run"]["id"] + ".json"
        )
        == report
    )


def test_suite_missing_case_usage_does_not_claim_complete_total(tmp_path):
    uses = iter(
        [
            {"input": 10, "output": 2},
            {"input": None, "output": 4},
            {"input": 5, "output": 6},
        ]
    )
    report = run_suite(
        "review-v2",
        {},
        "reviewer",
        tmp_path / "private",
        local=True,
        execute=lambda *args: {
            "exit_status": "Submitted",
            "benchmark_usage": next(uses),
        },
    )
    assert report["run"]["input_tokens"] is None
    assert report["run"]["output_tokens"] == 12


def test_cli_infrastructure_error_saves_report_and_exits_nonzero(
    tmp_path, monkeypatch
):
    config = tmp_path / "agents.yaml"
    config.write_text("agents:\n  coder: {}\n")

    def fail(*args):
        raise RuntimeError("provider unavailable")

    monkeypatch.setattr("workshop.agent_benchmark.local.execute_agent", fail)
    storage = tmp_path / "private"
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
            str(storage),
            "--local",
        ],
    )
    assert result.exit_code != 0
    report = json.loads(result.stdout)
    assert report["counts"]["infrastructure_error"] == 1
    assert "infrastructure" in result.stderr.lower()
    assert (
        PrivateStorage(storage).read_json(report["run"]["id"] + ".json")
        == report
    )


@pytest.mark.parametrize(
    "suite, expected",
    [("coding-v1", "fail"), ("review-v1", "pending_human_review")],
)
def test_cli_quality_outcomes_are_not_gates(
    tmp_path, monkeypatch, suite, expected
):
    config = tmp_path / "agents.yaml"
    config.write_text("agents:\n  agent: {}\n")
    monkeypatch.setattr(
        "workshop.agent_benchmark.local.execute_agent",
        lambda *args: {"exit_status": "Submitted", "submission": "done"},
    )
    result = CliRunner().invoke(
        cli,
        [
            "benchmark",
            "run",
            "--suite",
            suite,
            "--config",
            str(config),
            "--agent",
            "agent",
            "--storage",
            str(tmp_path / "private"),
            "--local",
        ],
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["counts"][expected] == 1
