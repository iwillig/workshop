import hashlib
import json

import pytest
from click.testing import CliRunner

from workshop.agent_benchmark.local import run_suite
from workshop.agent_eval.trace import load_trace
from workshop.cli import cli


class SavingAgent:
    progress_sink = None

    def __init__(self):
        self.messages = []

    def run(self, task):
        self.messages = [
            {"role": "user", "content": task},
        ]
        return {"exit_status": "Submitted", "submission": "done"}

    def save(self, path, *extra):
        return {"messages": self.messages}


def build_saving_agent(config):
    return SavingAgent()


def run(root, suite="review-v1", capture=False, execute=None):
    return run_suite(
        suite,
        {},
        "reviewer",
        root,
        local=True,
        capture_trace=capture,
        execute=execute,
    )


def test_capture_is_opt_in(tmp_path):
    root = tmp_path / "private"
    report = run(root, execute=lambda *args: {"exit_status": "Submitted"})
    assert report["run"]["trace"] is None
    assert not list(root.glob("trace-*.json"))


def test_capture_stores_hash_linked_trajectory(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "workshop.agent_config.build_agent", build_saving_agent
    )
    root = tmp_path / "private"
    report = run(root, capture=True)
    reference = report["run"]["trace"]
    assert reference["format"] == "workshop-benchmark-trace-1"
    assert reference["redacted"] is False
    record = load_trace(root, report["run"]["id"])
    case = record["cases"][0]
    assert case["case_id"] == "average-empty"
    assert case["trajectory"] == {
        "messages": [
            {
                "role": "user",
                "content": (
                    "Review calculator.py for bugs. "
                    "Report findings with locations."
                ),
            }
        ]
    }
    payload = json.dumps(
        record,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode()
    assert reference["sha256"] == hashlib.sha256(payload).hexdigest()
    assert reference["storage_key"].endswith(".json")


def test_capture_stores_every_case_of_a_multicase_suite(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "workshop.agent_config.build_agent", build_saving_agent
    )
    root = tmp_path / "private"
    report = run(root, suite="review-v2", capture=True)
    record = load_trace(root, report["run"]["id"])
    assert [case["case_id"] for case in record["cases"]] == [
        "average-empty",
        "discount-percent",
        "shared-cache",
    ]


def test_uncaptured_runs_have_no_trace_reference(tmp_path):
    root = tmp_path / "private"
    report = run(root, execute=lambda *args: {"exit_status": "Submitted"})
    with pytest.raises(ValueError, match="no stored trace"):
        load_trace(root, report["run"]["id"])


def test_tampered_trace_is_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "workshop.agent_config.build_agent", build_saving_agent
    )
    root = tmp_path / "private"
    report = run(root, capture=True)
    reference = report["run"]["trace"]
    path = root / reference["storage_key"]
    path.chmod(0o600)
    path.write_text(json.dumps({"schema_version": 1, "cases": []}))
    with pytest.raises(ValueError, match="hash"):
        load_trace(root, report["run"]["id"])


def test_cli_captures_and_displays_trace(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "workshop.agent_config.build_agent", build_saving_agent
    )
    root = tmp_path / "private"
    result = CliRunner().invoke(
        cli,
        [
            "benchmark",
            "run",
            "--suite",
            "review-v1",
            "--config",
            str(_write_config(tmp_path)),
            "--agent",
            "reviewer",
            "--storage",
            str(root),
            "--local",
            "--trace",
        ],
    )
    assert result.exit_code == 0, result.output
    report = json.loads(result.stdout)
    shown = CliRunner().invoke(
        cli,
        ["benchmark", "trace", report["run"]["id"], "--storage", str(root)],
    )
    assert shown.exit_code == 0, shown.output
    record = json.loads(shown.stdout)
    assert record["format"] == "workshop-benchmark-trace-1"
    assert "calculator.py" in json.dumps(record)


def test_cli_trace_requires_captured_run(tmp_path):
    root = tmp_path / "private"
    report = run(root, execute=lambda *args: {"exit_status": "Submitted"})
    result = CliRunner().invoke(
        cli,
        ["benchmark", "trace", report["run"]["id"], "--storage", str(root)],
    )
    assert result.exit_code != 0


def _write_config(tmp_path):
    config = tmp_path / "agents.yaml"
    config.write_text("agents:\n  reviewer: {}\n")
    return config
